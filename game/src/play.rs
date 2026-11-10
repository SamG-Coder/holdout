//! The mission in play: carrying out what it asks, the things in the level the player can use
//! and pick up, grenades, and what the interface is told.

use crate::ai::{Noise, Team};
use crate::mission::{Do, Facts, State};
use crate::npc::Zone;
use crate::physics::Loose;
use crate::{Game, View};
use glam::{Mat4, Quat, Vec3};
use solstice_render::{Renderer, Weather};
use std::collections::HashMap;
use std::fmt::Write as _;

/// A grenade in the air or on the ground, counting down.
pub struct Grenade {
    pub body: Loose,
    pub fuse: f32,
    pub group: Option<usize>,
    pub team: Team,
}

/// Where the player was when the mission last said to remember it.
#[derive(Clone, Copy, Debug)]
pub struct Saved {
    pub feet: Vec3,
    pub yaw: f32,
    pub rounds: u32,
    pub reserve: u32,
    pub grenades: u32,
}

fn escape(text: &str) -> String {
    text.replace('\\', "\\\\").replace('"', "\\\"")
}

impl Game {
    /// An explosion: what it looks and sounds like, and what it does to whoever is near.
    pub(crate) fn explosion(&mut self, at: Vec3, team: Team) {
        self.fx.explode(at, self.player.eye());
        self.audio.at("explosion", at, 1.0);
        self.noises.push(Noise {
            position: at,
            reach: 90.0,
            team,
        });
        const RADIUS: f32 = 7.5;
        let centre = at + Vec3::Y * 0.5;
        for index in 0..self.npcs.len() {
            let npc = &self.npcs[index];
            if !npc.active || !npc.alive {
                continue;
            }
            let chest = npc.chest();
            let distance = chest.distance(centre);
            if distance > RADIUS || !self.physics.clear_line(centre, chest) {
                continue;
            }
            let damage = 260.0 * (1.0 - distance / RADIUS).powf(0.7);
            let rig = &self.rigs[npc.rig];
            let away = (chest - centre).normalize_or(Vec3::Y);
            let npc = &mut self.npcs[index];
            npc.brain.hit(at);
            npc.hurt(damage, away, Zone::Torso, rig);
        }
        let chest = self.player.chest();
        let distance = chest.distance(centre);
        if distance < RADIUS && self.physics.clear_line(centre, chest) {
            let damage = 130.0 * (1.0 - distance / RADIUS).powf(0.8);
            self.since_hurt = 0.0;
            self.hurt_flash = 1.0;
            self.hurt_from = at;
            self.player.hurt(damage);
        }
    }

    /// Runs the mission and what belongs to it for a frame.
    pub(crate) fn update_mission(&mut self, renderer: &mut Renderer, dt: f32, use_held: bool, throw: bool) {
        // Who is left of each group.
        let mut alive: HashMap<String, u32> = HashMap::new();
        for (group, members) in &self.groups {
            let count = members
                .iter()
                .filter(|&&index| self.npcs[index].active && self.npcs[index].alive)
                .count() as u32;
            alive.insert(group.clone(), count);
        }
        let facts = Facts {
            player: self.player.feet,
            player_alive: self.player.alive,
            alive: &alive,
            used: &self.used,
        };
        let commands = self.mission.update(&facts, dt);
        for command in commands {
            match command {
                Do::Spawn(group) => self.spawn_group(renderer, group),
                Do::Alert(group) => {
                    let at = self.player.chest();
                    for &index in self.groups.get(group).map_or(&[][..], Vec::as_slice) {
                        self.npcs[index].brain.alert(at, true);
                    }
                }
                Do::Sound(name) => self.audio.own(name, 1.0),
                Do::Explode(goal) => {
                    if let Some(at) = self.mission.goal_named(goal) {
                        self.explosion(at, Team::Resistance);
                        // A charge that kills a lorry is not one bang: what it carried goes
                        // up after it, over the next second.
                        for (delay, offset) in [
                            (0.14, Vec3::new(1.7, 0.9, -0.7)),
                            (0.32, Vec3::new(-1.9, 1.6, 0.8)),
                            (0.55, Vec3::new(0.4, 2.6, 0.3)),
                            (0.8, Vec3::new(-0.8, 0.7, -1.4)),
                            (1.15, Vec3::new(2.3, 1.9, 1.1)),
                        ] {
                            self.blasts.push((delay, at + offset));
                        }
                    }
                    self.wreck(renderer, goal, true);
                }
                Do::Burn(goal) => {
                    if let Some(at) = self.mission.goal_named(goal) {
                        self.fx.smoulder(renderer, at + Vec3::Y * 1.0, 1.6);
                        self.fx.smoulder(renderer, at + Vec3::new(-3.2, 0.8, -1.2), 1.2);
                        self.fx.fire(renderer, at + Vec3::new(-1.0, 0.4, -1.6), 2.4);
                        self.fx.fire(renderer, at + Vec3::new(-4.6, 0.9, -1.4), 1.8);
                    }
                }
                Do::Weather(name, seconds) => {
                    if let Some(weather) = Weather::by_name(name) {
                        renderer.set_weather(weather, seconds);
                    }
                }
                Do::Checkpoint | Do::Say(..) | Do::Complete => {}
            }
        }
        // The explosions still to come.
        let mut due = Vec::new();
        self.blasts.retain_mut(|(delay, at)| {
            *delay -= dt;
            if *delay <= 0.0 {
                due.push(*at);
            }
            *delay > 0.0
        });
        for at in due {
            self.fx.explode(at, self.player.eye());
            self.audio.at("explosion", at, 0.85);
        }
        if self.mission.checkpoint != self.saved_stage {
            self.saved_stage = self.mission.checkpoint;
            let gun = self.arsenal.gun();
            self.saved = Some(Saved {
                feet: self.player.feet,
                yaw: self.player.yaw,
                rounds: gun.rounds,
                reserve: gun.reserve,
                grenades: self.grenades_left,
            });
        }

        // Things to use: stand by one, look at it, and hold the key.
        self.prompt = None;
        let eye = self.player.eye();
        let looking = self.player.forward();
        let mut using: Option<(String, f32)> = None;
        for marker in self.level.markers_of("use") {
            if self.used.contains(&marker.name) {
                continue;
            }
            // Only what the mission's stage is about can be used.
            let wanted = self.mission.goal_named(&marker.name).is_some()
                && self.mission.goal() == self.mission.goal_named(&marker.name);
            if !wanted {
                continue;
            }
            let to = marker.position + Vec3::Y * 1.0 - eye;
            let reach = marker.number("radius", 2.2);
            if to.length() < reach && looking.dot(to.normalize_or(looking)) > 0.5 {
                let text = marker.option("prompt").unwrap_or("Use").replace('_', " ");
                self.prompt = Some(text);
                using = Some((marker.name.clone(), marker.number("hold", 1.5)));
            }
        }
        match using {
            Some((name, hold)) if use_held => {
                if self.use_progress == 0.0 {
                    self.audio.own("use_start", 0.8);
                }
                self.use_progress += dt / hold.max(0.1);
                if self.use_progress >= 1.0 {
                    self.use_progress = 0.0;
                    self.used.insert(name);
                    self.audio.own("use_done", 1.0);
                }
            }
            _ => self.use_progress = 0.0,
        }

        // What the dead carried: walk over a fallen rifle for what was left in it.
        let mut found = 0;
        for npc in &mut self.npcs {
            if !npc.active || npc.looted || npc.brain.team != Team::Directorate {
                continue;
            }
            if let Some(at) = npc.fallen_weapon() {
                let apart = at - self.player.feet;
                if apart.x.hypot(apart.z) < 1.25 && apart.y.abs() < 1.6 {
                    let taken = self.arsenal.add_rounds(12 + (npc.position.x.abs() * 7.0) as u32 % 13);
                    if taken > 0 {
                        npc.looted = true;
                        found += taken;
                    }
                }
            }
        }
        if found > 0 {
            self.audio.own("pickup", 0.8);
            self.picked_up = Some((found, 2.5));
        }
        if let Some((_, left)) = &mut self.picked_up {
            *left -= dt;
            if *left <= 0.0 {
                self.picked_up = None;
            }
        }

        // Things to pick up: walk over them.
        for index in 0..self.pickups.len() {
            let (at, taken, rounds) = self.pickups[index];
            if taken || at.distance(self.player.feet + Vec3::Y * 0.5) > 1.3 {
                continue;
            }
            if self.arsenal.add_rounds(rounds) > 0 {
                self.pickups[index].1 = true;
                self.grenades_left = (self.grenades_left + 1).min(4);
                self.audio.own("pickup", 1.0);
                if let Some(group) = self.pickup_groups.get_mut(index) {
                    group.set_hidden(renderer, true);
                }
            }
        }

        // Grenades: thrown along the view, a little upward.
        if throw && self.grenades_left > 0 && self.player.alive {
            self.grenades_left -= 1;
            let forward = self.player.forward();
            let from = eye + forward * 0.5 + self.player.right() * 0.15;
            let velocity = (forward + Vec3::Y * 0.28).normalize() * 15.0 + self.player.velocity;
            let body = self.physics.add_loose_ball(from, velocity, Vec3::new(6.0, 2.0, 9.0), 0.045, 0.4, 0.35);
            let group = (0..self.grenade_pool.len()).find(|index| {
                !self.grenades.iter().any(|grenade| grenade.group == Some(*index))
            });
            self.grenades.push(Grenade {
                body,
                fuse: 3.0,
                group,
                team: Team::Resistance,
            });
            self.audio.own("grenade_throw", 0.9);
        }
        let mut gone_off = Vec::new();
        let mut index = 0;
        while index < self.grenades.len() {
            let grenade = &mut self.grenades[index];
            grenade.fuse -= dt;
            let place = self.physics.loose_transform(grenade.body);
            if let (Some(group), Some((position, rotation))) = (grenade.group, place) {
                let pooled = &mut self.grenade_pool[group];
                let world = Mat4::from_rotation_translation(rotation, position);
                if pooled.hidden() {
                    pooled.place(renderer, world);
                    pooled.set_hidden(renderer, false);
                } else {
                    pooled.move_to(renderer, world);
                }
            }
            if grenade.fuse <= 0.0 {
                let grenade = self.grenades.remove(index);
                if let Some(group) = grenade.group {
                    self.grenade_pool[group].set_hidden(renderer, true);
                }
                if let Some((position, _)) = place {
                    gone_off.push((position, grenade.team));
                }
                self.physics.remove_loose(grenade.body);
            } else {
                index += 1;
            }
        }
        for (at, team) in gone_off {
            self.explosion(at, team);
        }

        // The fight's heat, for the music: rises with enemies fighting, falls away after.
        let fighting = self
            .npcs
            .iter()
            .filter(|npc| npc.active && npc.alive && npc.brain.team == Team::Directorate && npc.brain.fighting())
            .count();
        let wanted = (fighting as f32 / 3.0).min(1.0);
        let rate = if wanted > self.audio.intensity { 1.2 } else { 0.12 };
        self.audio.intensity += (wanted - self.audio.intensity) * (1.0 - (-dt * rate).exp());
    }

    /// Whether the game is still waiting under its title, nothing yet played.
    pub fn on_title(&self) -> bool {
        self.frames <= 1
    }

    /// Shows a thing blown up, or whole again.
    fn wreck(&mut self, renderer: &mut Renderer, name: &str, wrecked: bool) {
        if let Some((whole, wreck)) = self.swaps.get_mut(name) {
            for group in whole {
                group.set_hidden(renderer, wrecked);
            }
            for group in wreck {
                group.set_hidden(renderer, !wrecked);
            }
        }
    }

    /// Brings a spawn group into play: everyone at a `spawn` marker of that name.
    fn spawn_group(&mut self, renderer: &mut Renderer, group: &str) {
        let markers: Vec<_> = self
            .level
            .markers_of("spawn")
            .filter(|marker| marker.name == group)
            .cloned()
            .collect();
        for marker in markers {
            let kind = marker.option("kind").unwrap_or("soldier").to_owned();
            let team = if kind.starts_with("rebel") { Team::Resistance } else { Team::Directorate };
            let Some(index) = self.spawn(renderer, &kind, marker.position, marker.yaw, team, true) else {
                log::warn!("nobody left of kind {kind} for the group {group}");
                continue;
            };
            let npc = &mut self.npcs[index];
            npc.brain.follows_player = marker.number("follow", 0.0) > 0.5;
            npc.brain.waits = npc.brain.follows_player;
            npc.brain.rooted = marker.number("hold", 0.0) > 0.5;
            if let Some(route) = marker.option("patrol") {
                let mut stops: Vec<_> = self
                    .level
                    .markers_of("route")
                    .filter(|stop| stop.name == route)
                    .map(|stop| (stop.number("n", 0.0), stop.position))
                    .collect();
                stops.sort_by(|a, b| a.0.total_cmp(&b.0));
                npc.brain.patrol = stops.into_iter().map(|(_, position)| position).collect();
            }
            self.groups.entry(group.to_owned()).or_default().push(index);
        }
    }

    /// Puts the player back at the last point the mission remembered, whole and reloaded.
    pub fn restart(&mut self, renderer: &mut Renderer) {
        // Whatever was blown up after the point gone back to stands again.
        let names: Vec<String> = self.swaps.keys().cloned().collect();
        for name in names {
            self.wreck(renderer, &name, false);
        }
        if !self.player.alive {
            self.tally.deaths += 1;
        }
        self.mission.retry();
        self.player.alive = true;
        self.player.health = 100.0;
        self.hurt_flash = 0.0;
        self.since_hurt = 100.0;
        self.use_progress = 0.0;
        match self.saved {
            Some(saved) => {
                self.player.place(&mut self.physics, saved.feet, saved.yaw);
                let gun = &mut self.arsenal.guns[self.arsenal.current];
                gun.rounds = saved.rounds.max(gun.def.magazine);
                gun.reserve = saved.reserve.max(gun.def.magazine * 3);
                self.grenades_left = saved.grenades.max(2);
            }
            None => {
                let (feet, yaw) = self
                    .level
                    .marker("player", "start")
                    .map_or((self.player.feet, 0.0), |marker| (marker.position, marker.yaw));
                self.player.place(&mut self.physics, feet, yaw);
            }
        }
        // Whoever was hunting the player forgets where they were.
        for npc in &mut self.npcs {
            if npc.active && npc.alive && npc.brain.team == Team::Directorate {
                npc.brain.calm();
            }
        }
    }

    /// The view as it last was, for drawing while the game is held still.
    pub fn still(&mut self, renderer: &mut Renderer) -> View {
        let _ = renderer;
        // Before the first step is taken, the title stands over a view of the level chosen
        // for it, turning slowly, rather than over the wall the player happens to face.
        if self.frames <= 1 {
            if let Some(marker) = self.level.marker("view", "title") {
                self.title_time += 1.0 / 60.0;
                let mut view = self.last_view;
                view.camera.position = marker.position;
                view.camera.yaw = marker.yaw + (self.title_time * 0.07).sin() * marker.number("sweep", 0.12);
                view.camera.pitch = marker.number("pitch", 0.0).to_radians();
                view.camera.fov_y = marker.number("fov", 50.0).to_radians();
                return view;
            }
        }
        self.last_view
    }

    /// What the interface shows, as JSON. `aspect` is the picture's width over its height.
    pub fn hud(&self, aspect: f32) -> String {
        let gun = self.arsenal.gun();
        let camera = self.last_view.camera;
        let forward = camera.forward();
        let right = camera.right();
        let up = right.cross(forward);
        let half = (camera.fov_y * 0.5).tan();
        // The crosshair's gap, as a share of the picture's height.
        let spread = self.arsenal.spread(&self.player).tan() / half * 0.5;
        // Where on the picture a place in the world falls: x and y from 0 to 1, how far away
        // it is, and whether it is in view (else it is pinned to the edge towards it).
        let project = |point: Vec3| -> (f32, f32, f32, bool) {
            let to = point - camera.position;
            let (x, y, z) = (to.dot(right), to.dot(up), to.dot(forward));
            let distance = to.length();
            let mut sx = x / (z.abs().max(0.01) * half * aspect);
            let mut sy = y / (z.abs().max(0.01) * half);
            let inside = z > 0.0 && sx.abs() < 0.92 && sy.abs() < 0.88;
            if !inside {
                // Behind or off to the side: out to the edge, in its direction.
                if z <= 0.0 {
                    sx = if x >= 0.0 { 1.0 } else { -1.0 } * sx.abs().max(0.5) * 4.0;
                    sy = -sy.abs();
                }
                let scale = (sx.abs() / 0.92).max(sy.abs() / 0.88).max(1.0e-3);
                sx /= scale;
                sy /= scale;
            }
            (sx * 0.5 + 0.5, 0.5 - sy * 0.5, distance, inside)
        };
        let mut out = String::with_capacity(512);
        let state = match self.mission.state {
            State::Playing => "playing",
            State::Dead => "dead",
            State::Complete => "complete",
        };
        let hurt = self.hurt_from - camera.position;
        let hurt_angle = hurt.dot(right).atan2(hurt.dot(forward)).to_degrees();
        write!(
            out,
            "{{\"state\":\"{state}\",\"ended\":{:.2},\"title\":\"{}\",\"hp\":{:.0},\"flash\":{:.3},\"hurtAngle\":{:.1},\
             \"ammo\":{},\"reserve\":{},\"mag\":{},\"weapon\":\"{}\",\"reloading\":{},\"grenades\":{},\
             \"spread\":{:.4},\"aim\":{:.3},\"hit\":{:.3},\"ready\":{},\"compass\":{:.1},\"objective\":\"{}\"",
            self.mission.ended_for,
            escape(self.mission.title),
            self.player.health,
            self.hurt_flash,
            hurt_angle,
            gun.rounds,
            gun.reserve,
            gun.def.magazine,
            gun.def.title,
            self.arsenal.reloading(),
            self.grenades_left,
            spread,
            self.arsenal.aim,
            self.arsenal.hit_marker,
            self.arsenal.ready(),
            (-camera.yaw).to_degrees().rem_euclid(360.0),
            escape(self.mission.objective()),
        )
        .ok();
        if let Some(goal) = self.mission.goal() {
            let (x, y, distance, inside) = project(goal + Vec3::Y * 1.2);
            write!(out, ",\"goal\":[{x:.4},{y:.4},{distance:.1},{}]", u8::from(inside)).ok();
        }
        if let Some(line) = self.mission.lines.front() {
            write!(out, ",\"line\":[\"{}\",\"{}\"]", escape(line.speaker), escape(line.text)).ok();
        }
        if let Some(prompt) = &self.prompt {
            write!(out, ",\"prompt\":\"{}\",\"progress\":{:.3}", escape(prompt), self.use_progress).ok();
        }
        if let Some((rounds, _)) = self.picked_up {
            write!(out, ",\"picked\":{rounds}").ok();
        }
        let tally = &self.tally;
        write!(
            out,
            ",\"tally\":[{},{},{},{},{},{:.0}]",
            tally.shots, tally.hits, tally.kills, tally.headshots, tally.deaths, tally.seconds
        )
        .ok();
        // Friends, as marks on the picture, so that nobody shoots them by mistake.
        out.push_str(",\"friends\":[");
        let mut first = true;
        for npc in &self.npcs {
            if npc.active && npc.alive && npc.brain.team == Team::Resistance {
                let (x, y, distance, inside) = project(npc.head() + Vec3::Y * 0.28);
                if inside && distance < 60.0 {
                    if !first {
                        out.push(',');
                    }
                    first = false;
                    write!(out, "[{x:.4},{y:.4},{distance:.1}]").ok();
                }
            }
        }
        out.push_str("]}");
        out
    }
}

/// The turn that stands a thing upright at a place, facing a yaw.
pub fn upright(position: Vec3, yaw: f32) -> Mat4 {
    Mat4::from_rotation_translation(Quat::from_rotation_y(yaw), position)
}
