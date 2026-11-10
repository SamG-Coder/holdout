//! HOLDOUT: an original first-person shooter on the Solstice engine.
//!
//! [`Game`] is the whole game, with no window and no page: each frame it takes what the player
//! is asking for, moves the world on, and tells the renderer what moved and where the eye is.
//! The desktop runner (`main.rs`) and the browser page (`web.rs`) are thin shells around it.

pub mod actors;
pub mod ai;
pub mod anim;
pub mod audio;
pub mod fx;
pub mod ik;
pub mod input;
pub mod level;
pub mod mission;
pub mod nav;
pub mod npc;
pub mod prof;
pub mod physics;
pub mod play;
pub mod player;
pub mod weapons;
#[cfg(target_arch = "wasm32")]
mod web;

use actors::Group;
use ai::{Noise, Team};
use anim::{RifleHold, Rig};
use nav::Nav;
use audio::Audio;
use fx::Fx;
use glam::{Mat4, Quat, Vec3};
use input::{Action, Input};
use level::{Level, Surface, LEVEL_FILE};
use npc::{ray_capsule, Npc, Zone};
use physics::{Physics, DEBRIS, WORLD};
use player::Player;
use solstice_asset::scene::Viewpoint;
use solstice_asset::{Clip, Collision, GameFile, Skeleton};
use solstice_render::{Camera, Environment, Place, Renderer, TimeOfDay, Weather};
use mission::{Mission, State};
use play::{Grenade, Saved};
use std::collections::{HashMap, HashSet};
use weapons::{Arsenal, Gun, Shot};

/// The parts of a loaded scene the game needs.
#[derive(Clone, Copy)]
pub struct SceneInfo<'a> {
    pub gameplay: &'a [GameFile],
    pub collision: Option<&'a Collision>,
    pub skeletons: &'a [Skeleton],
    pub clips: &'a [Clip],
    /// The skeleton of each pose.
    pub poses: &'a [u32],
    pub viewpoint: Option<Viewpoint>,
}

/// What a frame came to: where to draw from, and under what light.
#[derive(Clone, Copy, Debug)]
pub struct View {
    pub camera: Camera,
    pub environment: Environment,
}

/// The mission's account of the player: shown when it is over.
#[derive(Clone, Copy, Debug, Default)]
pub struct Tally {
    pub shots: u32,
    pub hits: u32,
    pub kills: u32,
    pub headshots: u32,
    pub deaths: u32,
    pub seconds: f32,
}

/// The camera flown freely, away from the player's body: for looking at a level while making it.
struct FlyCamera {
    position: Vec3,
    yaw: f32,
    pitch: f32,
    velocity: Vec3,
}

pub struct Game {
    pub level: Level,
    pub physics: Physics,
    pub player: Player,
    pub arsenal: Arsenal,
    pub fx: Fx,
    pub audio: Audio,
    time: TimeOfDay,
    place: Place,
    daylight: Environment,
    /// Real seconds a whole day takes, or 0 to hold the time still.
    day_seconds: f32,
    /// The hour at which the level's clock stops: dusk deepens through a mission, but not to
    /// a night nobody can see in.
    time_stop: f32,
    /// How much brighter than daylight's exposure the level is shown.
    exposure: f32,
    /// The least share of its direct light a setting sun keeps.
    low_sun: f32,
    fly: Option<FlyCamera>,
    /// A change of weather asked for from the console, waiting for the next frame.
    wanted_weather: Option<(String, f32)>,
    /// Asked for from the console: go back to the last point remembered.
    wanted_retry: bool,
    /// Set from the console: the player takes no harm.
    god: bool,
    fov: f32,
    /// Seconds since the game began.
    pub elapsed: f32,
    /// How many frames have been played, and how long the title has been up before them.
    frames: u32,
    title_time: f32,
    /// Each kind of character's skeleton and clips.
    pub rigs: Vec<Rig>,
    rig_names: HashMap<String, usize>,
    pub npcs: Vec<Npc>,
    hold: RifleHold,
    /// Shots a test script has asked for: fired on the next frame as if the trigger were held.
    scripted_fire: u32,
    pub nav: Option<Nav>,
    cover_owner: Vec<Option<usize>>,
    noises: Vec<Noise>,
    /// Seconds since the player was last hurt: after a while unhurt, they recover.
    since_hurt: f32,
    /// How red the edges of the view are, and where the last hit came from, for the interface.
    pub hurt_flash: f32,
    pub hurt_from: Vec3,
    spawn_seed: u32,
    pub mission: Mission,
    /// The people each spawn group brought into play.
    groups: HashMap<String, Vec<usize>>,
    /// The `use` markers the player has used.
    used: HashSet<String>,
    /// What the player could use now, and how far through using it they are.
    prompt: Option<String>,
    use_progress: f32,
    /// Things to pick up: where, whether taken, and the rounds in each.
    pickups: Vec<(Vec3, bool, u32)>,
    pickup_groups: Vec<Group>,
    grenades: Vec<Grenade>,
    grenade_pool: Vec<Group>,
    /// What a mission's explosions destroy: for each name, the thing whole and its wreck.
    swaps: HashMap<String, (Vec<Group>, Vec<Group>)>,
    /// Explosions set to follow one that has gone off: how long until each, and where.
    blasts: Vec<(f32, Vec3)>,
    /// Rounds just picked up, and how much longer the interface says so.
    picked_up: Option<(u32, f32)>,
    /// What the player has done, for the end of the mission.
    pub tally: Tally,
    pub grenades_left: u32,
    saved: Option<Saved>,
    saved_stage: usize,
    last_view: View,
}

/// The lighting of a clear day with the sun well up, which the time of day then colours.
fn daylight() -> Environment {
    Environment {
        sun_direction: Vec3::new(0.62, 0.42, 0.5).normalize(),
        sun_illuminance: 14.0,
        sky_intensity: 3.0,
        gi_intensity: 0.85,
        ..Default::default()
    }
}

/// Where a camera is in the world, as a matrix: looking along its own -Z.
fn camera_matrix(position: Vec3, yaw: f32, pitch: f32, roll: f32) -> Mat4 {
    Mat4::from_rotation_translation(
        Quat::from_rotation_y(yaw) * Quat::from_rotation_x(pitch) * Quat::from_rotation_z(-roll),
        position,
    )
}

impl Game {
    /// Starts the game in a loaded scene.
    pub fn new(info: &SceneInfo<'_>, renderer: &mut Renderer) -> Result<Self, String> {
        let text = info
            .gameplay
            .iter()
            .find(|file| file.name == LEVEL_FILE)
            .map(|file| file.text.as_str())
            .ok_or_else(|| format!("the scene has no {LEVEL_FILE}: was it made by levelc?"))?;
        let level = Level::parse(text)?;

        let mut physics = Physics::new();
        if let Some(collision) = info.collision {
            physics.add_scene(collision, |index| renderer.instance_transform(index));
        }
        for blocker in &level.blockers {
            match blocker.surface {
                Some(surface) => {
                    physics.add_solid(blocker.centre, blocker.size, blocker.yaw, surface.solid_id());
                }
                None => physics.add_edge(blocker.centre, blocker.size, blocker.yaw),
            }
        }
        for trunk in &level.trunks {
            physics.add_trunk(trunk.position, trunk.radius, 6.0);
        }
        for warning in physics.warnings.drain(..) {
            log::warn!("physics: {warning}");
        }

        let (feet, yaw) = match level.marker("player", "start") {
            Some(marker) => (marker.position, marker.yaw),
            None => {
                let at = info
                    .viewpoint
                    .map_or(Vec3::new(0.0, 2.0, 0.0), |v| Vec3::from_array(v.position));
                (at - Vec3::Y * 1.6, info.viewpoint.map_or(0.0, |v| v.yaw))
            }
        };
        let player = Player::new(&mut physics, feet, yaw);
        // Once, so that rays and walkers see everything just added.
        physics.step(1.0 / 60.0);

        // Characters: each skinned kit is a rig, and each placement of it a body.
        let mut rigs = Vec::new();
        let mut rig_names = HashMap::new();
        let mut kits: Vec<(&String, &u32)> = level.skeletons.iter().collect();
        kits.sort();
        for (alias, skeleton) in kits {
            rig_names.insert(alias.clone(), rigs.len());
            rigs.push(Rig::new(alias, *skeleton, info.skeletons, info.clips)?);
        }
        let mut npcs = Vec::new();
        let mut rifles = Group::all(&level, "npc_rifle", renderer).into_iter();
        let mut names: Vec<(&String, &usize)> = rig_names.iter().collect();
        names.sort();
        for (alias, &rig_index) in names {
            if alias == "arms" {
                continue;
            }
            for mut body in Group::all(&level, alias, renderer) {
                body.set_hidden(renderer, true);
                let mut rifle = rifles.next();
                if let Some(rifle) = &mut rifle {
                    rifle.set_hidden(renderer, true);
                }
                npcs.push(Npc::new(body, rifle, rig_index, &rigs[rig_index], alias));
            }
        }

        // Where people can walk: sounded between the level's corners, or round its markers.
        let seeds: Vec<Vec3> = level.markers.iter().map(|m| m.position + Vec3::Y * 0.3).collect();
        let nav = if seeds.is_empty() {
            None
        } else {
            let words: Vec<f32> = level
                .setting("nav")
                .map(|text| text.split_whitespace().filter_map(|w| w.parse().ok()).collect())
                .unwrap_or_default();
            let (mut low, mut high) = (Vec3::splat(f32::MAX), Vec3::splat(f32::MIN));
            for seed in &seeds {
                low = low.min(*seed);
                high = high.max(*seed);
            }
            let (low, high) = if words.len() == 4 {
                (
                    Vec3::new(words[0], low.y - 3.0, words[1]),
                    Vec3::new(words[2], high.y + 7.0, words[3]),
                )
            } else {
                (low - Vec3::new(25.0, 3.0, 25.0), high + Vec3::new(25.0, 7.0, 25.0))
            };
            let nav = Nav::build(&physics, low, high, &seeds);
            log::info!("navigation: {} places, {} pieces of cover", nav.place_count(), nav.covers.len());
            Some(nav)
        };
        let cover_owner = vec![None; nav.as_ref().map_or(0, |nav| nav.covers.len())];

        let fx = Fx::new(&level, renderer);
        // The sidearm, in levels made since there was one.
        let mut guns = vec![Gun::new(weapons::carbine())];
        if level.one("fp_pistol_body").is_some() {
            guns.push(Gun::new(weapons::pistol()));
        }
        let arsenal = Arsenal::new(
            &level,
            renderer,
            guns,
            rig_names.get("arms").copied(),
        );
        // The sight's dot and tracers glow far brighter than a material can say.
        for placed in level.all("fp_carbine_dot") {
            for id in placed.instances() {
                renderer.set_instance_glow(id, 60.0);
            }
        }
        for placed in level.all("tracer") {
            for id in placed.instances() {
                renderer.set_instance_glow(id, 90.0);
            }
        }

        let mission = mission::by_name(level.setting("mission").unwrap_or(""), &level);
        let pickups: Vec<(Vec3, bool, u32)> = level
            .markers_of("pickup")
            .map(|marker| (marker.position, false, marker.number("rounds", 60.0) as u32))
            .collect();
        let pickup_groups = Group::all(&level, "pickup", renderer);
        // Wrecks wait out of sight for the explosion that makes them.
        let mut swaps: HashMap<String, (Vec<Group>, Vec<Group>)> = HashMap::new();
        let wrecked: Vec<String> = level
            .placed
            .keys()
            .filter_map(|tag| tag.strip_suffix("_wreck").map(str::to_owned))
            .collect();
        for name in wrecked {
            let whole = Group::all(&level, &format!("{name}_intact"), renderer);
            let mut wreck = Group::all(&level, &format!("{name}_wreck"), renderer);
            for group in &mut wreck {
                group.set_hidden(renderer, true);
            }
            swaps.insert(name, (whole, wreck));
        }
        let mut grenade_pool = Group::all(&level, "grenade", renderer);
        for group in &mut grenade_pool {
            group.set_hidden(renderer, true);
        }

        let time = TimeOfDay {
            day: level.setting_number("day", 265.0),
            hours: level.setting_number("time", 17.4),
        };
        let place = Place {
            latitude: level.setting_number("latitude", 44.0),
            north: -level.setting_number("north", 0.0).to_radians(),
        };
        if let Some(weather) = level.setting("weather").and_then(Weather::by_name) {
            renderer.set_weather(weather, 0.0);
        }
        let day_seconds = level.setting_number("day_seconds", 0.0);
        let time_stop = level.setting_number("time_stop", 24.0);
        let level_exposure = level.setting_number("exposure", 1.0).max(0.05);
        let mut game = Self {
            level,
            physics,
            player,
            arsenal,
            fx,
            audio: Audio::default(),
            time,
            place,
            daylight: daylight(),
            day_seconds,
            time_stop,
            exposure: level_exposure,
            low_sun: 1.0,
            fly: None,
            wanted_weather: None,
            wanted_retry: false,
            god: false,
            fov: 62.0_f32.to_radians(),
            elapsed: 0.0,
            frames: 0,
            title_time: 0.0,
            rigs,
            rig_names,
            npcs,
            hold: weapons::carbine().hold,
            scripted_fire: 0,
            nav,
            cover_owner,
            noises: Vec::new(),
            since_hurt: 100.0,
            hurt_flash: 0.0,
            hurt_from: Vec3::ZERO,
            spawn_seed: 7,
            mission,
            groups: HashMap::new(),
            used: HashSet::new(),
            prompt: None,
            use_progress: 0.0,
            pickups,
            pickup_groups,
            grenades: Vec::new(),
            grenade_pool,
            swaps,
            blasts: Vec::new(),
            picked_up: None,
            tally: Tally::default(),
            grenades_left: 2,
            saved: None,
            saved_stage: usize::MAX,
            last_view: View {
                camera: Camera::default(),
                environment: daylight(),
            },
        };
        // Until the first frame, the view is the player's own, standing where they start.
        game.last_view = View {
            camera: Camera {
                position: game.player.eye(),
                yaw: game.player.yaw,
                pitch: 0.0,
                fov_y: game.fov,
                near: 0.05,
            },
            environment: game.time.environment(&game.place, &game.daylight),
        };
        // Fires that burn from the start: `fire` markers, with how hot.
        let fires: Vec<(Vec3, f32)> = game
            .level
            .markers_of("fire")
            .map(|marker| (marker.position, marker.number("heat", 1.0)))
            .collect();
        for (at, heat) in fires {
            game.fx.fire(renderer, at, heat);
        }
        // And what burns beyond the town: `plume` markers.
        let plumes: Vec<(Vec3, f32)> = game
            .level
            .markers_of("plume")
            .map(|marker| (marker.position, marker.number("heat", 1.0)))
            .collect();
        for (at, heat) in plumes {
            game.fx.plume(renderer, at, heat);
        }
        // Until a mission places them: someone stands at each `npc` marker, as it says.
        let markers: Vec<_> = game.level.markers_of("npc").cloned().collect();
        for marker in &markers {
            let kind = marker.option("kind").unwrap_or("soldier").to_owned();
            let team = if kind.starts_with("rebel") { Team::Resistance } else { Team::Directorate };
            let thinking = marker.number("ai", 0.0) > 0.5;
            let Some(index) = game.spawn(renderer, &kind, marker.position, marker.yaw, team, thinking) else {
                log::warn!("no {kind} left for the npc marker `{}`", marker.name);
                continue;
            };
            let npc = &mut game.npcs[index];
            npc.speed = marker.number("speed", 0.0);
            npc.crouched = marker.number("crouch", 0.0) > 0.5;
            npc.stance.aim_yaw = marker.number("aim_yaw", 0.0).to_radians();
            npc.stance.aim_pitch = marker.number("aim_pitch", 0.0).to_radians();
            npc.stance.shouldered = marker.number("shouldered", 0.0);
            npc.stance.armed = marker.number("armed", 1.0);
            npc.brain.follows_player = marker.number("follow", 0.0) > 0.5;
            if let Some(action) = marker.option("action") {
                npc.animator.play(action, 0.0, 0.0, 1.0, true);
            }
        }
        Ok(game)
    }

    /// Brings someone of a kind into play at a place. Returns which, or `None` if every body of
    /// that kind is in use.
    pub fn spawn(
        &mut self,
        renderer: &mut Renderer,
        kind: &str,
        position: Vec3,
        yaw: f32,
        team: Team,
        thinking: bool,
    ) -> Option<usize> {
        // One not in play, or failing that the longest dead.
        let index = self
            .npcs
            .iter()
            .position(|npc| npc.kind == kind && !npc.active)
            .or_else(|| {
                self.npcs
                    .iter()
                    .enumerate()
                    .filter(|(_, npc)| npc.kind == kind && !npc.alive && npc.dead_for > 8.0)
                    .max_by(|a, b| a.1.dead_for.total_cmp(&b.1.dead_for))
                    .map(|(index, _)| index)
            })?;
        self.spawn_seed = self.spawn_seed.wrapping_mul(747_796_405).wrapping_add(2_891_336_453);
        let seed = self.spawn_seed;
        let rig = &self.rigs[self.npcs[index].rig];
        let followers = self
            .npcs
            .iter()
            .filter(|npc| npc.active && npc.brain.team == Team::Resistance)
            .count();
        let npc = &mut self.npcs[index];
        npc.enter(renderer, &mut self.physics, rig, position, yaw, team, thinking, seed);
        npc.brain.slot = followers;
        Some(index)
    }

    pub fn set_time(&mut self, hours: f32) {
        self.time.hours = hours.rem_euclid(24.0);
    }

    pub fn rig(&self, alias: &str) -> Option<usize> {
        self.rig_names.get(alias).copied()
    }

    /// Carries out a command from a test script or a developer. Returns false if there is no
    /// such command.
    ///
    /// * `fly X Y Z YAW PITCH` flies the camera there, leaving the body where it is.
    /// * `walk` puts the camera back in the body.
    /// * `goto X Y Z YAW` puts the body there.
    /// * `look YAW PITCH` turns the player's view.
    /// * `fire FRAMES` holds the trigger for that many frames.
    /// * `explode X Y Z` sets off an explosion.
    pub fn debug_command(&mut self, command: &str) -> bool {
        let words: Vec<&str> = command.split_whitespace().collect();
        let number = |index: usize| -> f32 {
            words
                .get(index)
                .and_then(|w| w.parse().ok())
                .unwrap_or(0.0)
        };
        match words.first().copied() {
            Some("fly") => {
                self.fly = Some(FlyCamera {
                    position: Vec3::new(number(1), number(2), number(3)),
                    yaw: number(4),
                    pitch: number(5),
                    velocity: Vec3::ZERO,
                });
            }
            Some("walk") => self.fly = None,
            Some("exposure") => self.exposure = number(1).max(0.05),
            Some("lowsun") => self.low_sun = number(1).clamp(0.01, 1.0),
            // Where the weapon is held in the picture: x y z, then pitch, yaw and roll.
            Some("hip") => {
                let current = self.arsenal.current;
                self.arsenal.guns[current].def.hip = weapons::ViewPose {
                    position: Vec3::new(number(1), number(2), number(3)),
                    turn: Vec3::new(number(4), number(5), number(6)),
                };
            }
            // For trying a mission out: nothing can hurt the player, a whole group falls
            // dead, a thing counts as used.
            Some("god") => self.god = true,
            Some("mortal") => self.god = false,
            Some("retry") => self.wanted_retry = true,
            Some("kill") => {
                let members = words
                    .get(1)
                    .and_then(|group| self.groups.get(*group))
                    .cloned()
                    .unwrap_or_default();
                for index in members {
                    let rig = &self.rigs[self.npcs[index].rig];
                    self.npcs[index].hurt(1000.0, Vec3::Z, Zone::Torso, rig);
                }
            }
            Some("used") => {
                if let Some(name) = words.get(1) {
                    self.used.insert((*name).to_owned());
                }
            }
            Some("weather") => {
                self.wanted_weather = words.get(1).map(|name| ((*name).to_owned(), number(2)));
            }
            Some("goto") => {
                let feet = Vec3::new(number(1), number(2), number(3));
                self.player.place(&mut self.physics, feet, number(4));
            }
            Some("look") => {
                self.player.yaw = number(1);
                self.player.pitch = number(2);
            }
            Some("fire") => self.scripted_fire = number(1).max(1.0) as u32 + 1,
            Some("explode") => {
                let at = Vec3::new(number(1), number(2), number(3));
                self.fx.explode(at, self.player.eye());
                self.audio.at("explosion", at, 1.0);
            }
            _ => return false,
        }
        true
    }

    /// A few lines about the state of the game, for a headless run to print.
    pub fn debug_summary(&self) -> Vec<String> {
        let gun = self.arsenal.gun();
        vec![
            format!(
                "player at {:.2} {:.2} {:.2}, yaw {:.2}, grounded {}, health {:.0}, {} colliders",
                self.player.feet.x,
                self.player.feet.y,
                self.player.feet.z,
                self.player.yaw,
                self.player.grounded,
                self.player.health,
                self.physics.collider_count(),
            ),
            format!(
                "{}: {} in the magazine, {} in reserve; {} people, {} alive",
                gun.def.name,
                gun.rounds,
                gun.reserve,
                self.npcs.len(),
                self.npcs.iter().filter(|n| n.alive && n.active).count()
            ),
            format!(
                "mission stage {}: {}; {:.2} h",
                self.mission.stage(),
                self.mission.objective(),
                self.time.hours
            ),
            prof::report().join("; "),
        ]
    }

    /// Follows a shot to whatever it hits first, and does what a bullet does there.
    fn resolve_shot(&mut self, shot: &Shot) {
        const REACH: f32 = 400.0;
        let world = self
            .physics
            .raycast(shot.origin, shot.direction, REACH, WORLD | DEBRIS);
        let mut reach = world.map_or(REACH, |hit| hit.distance);
        let mut struck: Option<(usize, Zone)> = None;
        self.tally.shots += 1;
        for (index, npc) in self.npcs.iter().enumerate() {
            // The cell is never hit by its own: a shot that would have, goes by.
            if !npc.alive || !npc.active || npc.brain.team == Team::Resistance {
                continue;
            }
            // Only those the ray passes near are worth the closer look.
            let to_chest = npc.chest() - shot.origin;
            let along = to_chest.dot(shot.direction);
            if along < -1.0 || along > reach + 1.0 {
                continue;
            }
            if (to_chest - shot.direction * along).length_squared() > 1.6 * 1.6 {
                continue;
            }
            for shape in npc.hit_shapes(&self.rigs[npc.rig]) {
                if let Some(t) = ray_capsule(shot.origin, shot.direction, reach, &shape) {
                    reach = t;
                    struck = Some((index, shape.zone));
                }
            }
        }
        let end = shot.origin + shot.direction * reach;
        self.fx.tracer(shot.muzzle, end);
        match struck {
            Some((index, zone)) => {
                let multiplier = match zone {
                    Zone::Head => shot.head_multiplier,
                    Zone::Torso => 1.0,
                    Zone::Limb => shot.limb_multiplier,
                };
                self.fx.impact(end, -shot.direction, Surface::Flesh);
                self.audio.at("impact_flesh", end, 1.0);
                let rig = &self.rigs[self.npcs[index].rig];
                self.npcs[index].brain.hit(shot.origin);
                let killed = self.npcs[index].hurt(shot.damage * multiplier, shot.direction, zone, rig);
                self.tally.hits += 1;
                if killed {
                    self.audio.at("death", end, 1.0);
                    self.tally.kills += 1;
                    if zone == Zone::Head {
                        self.tally.headshots += 1;
                    }
                }
                self.arsenal.hit_marker = if killed { 2.0 } else { 1.0 };
            }
            None => {
                if let Some(hit) = world {
                    let surface = self.level.surface_of(hit.instance);
                    self.fx.impact(hit.point, hit.normal, surface);
                    let sound = match surface {
                        Surface::Metal => "impact_metal",
                        Surface::Wood => "impact_wood",
                        Surface::Dirt | Surface::Grass => "impact_dirt",
                        Surface::Glass => "impact_glass",
                        _ => "impact_concrete",
                    };
                    self.audio.at(sound, hit.point, 1.0);
                }
            }
        }
    }

    /// Runs a frame of `seconds`, and says where to draw it from. The input's presses are used
    /// up: the caller need not clear them.
    pub fn frame(&mut self, renderer: &mut Renderer, input: &mut Input, seconds: f32) -> View {
        let dt = seconds.clamp(1.0 / 500.0, 1.0 / 20.0);
        self.elapsed += dt;
        self.frames += 1;
        if std::mem::take(&mut self.wanted_retry) {
            self.restart(renderer);
        }
        if let Some((name, over)) = self.wanted_weather.take() {
            match Weather::by_name(&name) {
                Some(weather) => renderer.set_weather(weather, over),
                None => log::warn!("no weather called {name}"),
            }
        }

        if input.take(Action::Fly) {
            self.fly = match self.fly.take() {
                Some(_) => None,
                None => Some(FlyCamera {
                    position: self.player.eye(),
                    yaw: self.player.yaw,
                    pitch: self.player.pitch,
                    velocity: Vec3::ZERO,
                }),
            };
        }
        if self.scripted_fire > 0 {
            self.scripted_fire -= 1;
            input.set(Action::Fire, self.scripted_fire > 0);
        }

        let (turn_left, turn_up) = input.turn(dt);
        let over = self.mission.state != State::Playing;
        if !over {
            self.tally.seconds += dt;
        }
        let flying = self.fly.is_some() || over;
        let use_held = !flying && input.held(Action::Use);
        let throw = !flying && input.pressed(Action::Grenade);
        let nobody = Input::new();
        let body_input: &Input = if flying { &nobody } else { input };
        if !flying {
            // Aimed, the same push of the mouse turns the view less, as the zoom would magnify it.
            let aimed = 1.0 - self.arsenal.aim * (1.0 - self.arsenal.gun().def.aim_zoom);
            self.player.turn(turn_left * aimed, turn_up * aimed);
        }
        let aiming = self.arsenal.aim > 0.5;
        let body = self
            .player
            .update(&mut self.physics, body_input, dt, aiming, flying);
        if let Some(weight) = body.footstep {
            let under = self
                .physics
                .raycast(self.player.feet + Vec3::Y * 0.3, Vec3::NEG_Y, 1.0, WORLD);
            let surface = self.level.surface_of(under.and_then(|hit| hit.instance));
            let sound = match surface {
                Surface::Grass | Surface::Dirt => "step_dirt",
                Surface::Wood => "step_wood",
                Surface::Metal => "step_metal",
                _ => "step_concrete",
            };
            self.audio.own(sound, 0.35 + weight * 0.5);
        }
        if body.jumped {
            self.audio.own("jump", 0.6);
        }
        if let Some(speed) = body.landed {
            self.audio.own("land", (speed / 8.0).clamp(0.3, 1.0));
            self.fx.shake((speed / 30.0).min(0.3));
        }

        let shots = self.arsenal.update(
            renderer,
            body_input,
            &mut self.player,
            &self.physics,
            &mut self.fx,
            &mut self.audio,
            dt,
            flying,
        );
        for shot in &shots {
            self.resolve_shot(shot);
            self.noises.push(Noise {
                position: shot.origin,
                reach: shot.loudness,
                team: Team::Resistance,
            });
        }

        // Everyone else.
        let noises = std::mem::take(&mut self.noises);
        let ai_time = prof::scope("ai");
        let harm = ai::update(
            &mut ai::World {
                npcs: &mut self.npcs,
                rigs: &self.rigs,
                nav: self.nav.as_ref(),
                physics: &mut self.physics,
                player: &self.player,
                level: &self.level,
                fx: &mut self.fx,
                audio: &mut self.audio,
                noises: &noises,
                cover_owner: &mut self.cover_owner,
                player_firing: !shots.is_empty(),
                time: self.elapsed,
            },
            dt,
        );
        drop(ai_time);
        self.since_hurt += dt;
        self.hurt_flash = (self.hurt_flash - dt * 1.6).max(0.0);
        for (damage, from) in &harm.hits {
            self.since_hurt = 0.0;
            self.hurt_flash = (self.hurt_flash + 0.5).min(1.0);
            self.hurt_from = *from;
            self.fx.shake(0.18);
            self.audio.own("player_hurt", 1.0);
            if !self.god && self.player.hurt(*damage) {
                self.audio.own("player_death", 1.0);
            }
        }
        if self.player.alive && self.since_hurt > 4.5 {
            self.player.health = (self.player.health + dt * 22.0).min(100.0);
        }
        self.update_mission(renderer, dt, use_held, throw);
        for npc in &mut self.npcs {
            if npc.active && !npc.alive {
                npc.dead_for += dt;
                // The dead no longer hold their cover or block the way.
                if npc.dead_for < dt * 1.5 {
                    if let Some(walker) = npc.walker {
                        self.physics.set_walker_enabled(walker, false);
                    }
                    for owner in &mut self.cover_owner {
                        *owner = None;
                    }
                }
            }
        }
        for landed in std::mem::take(&mut self.fx.casing_landed) {
            self.audio.at("casing", landed, 0.5);
        }

        // The view: the player's eye, thrown about by recoil and whatever shakes it.
        let punch = self.arsenal.view_punch();
        let shake = self.fx.view_shake();
        let eye = self.player.eye();
        let yaw = self.player.yaw + (punch.x + shake.x) * 0.02;
        let pitch = (self.player.pitch + punch.y * 0.02 + shake.y).clamp(-1.55, 1.55);
        let roll = punch.z * 0.02 + shake.z;
        let player_view = camera_matrix(eye, yaw, pitch, roll);
        self.arsenal.draw(
            renderer,
            &self.rigs,
            &self.player,
            &self.physics,
            player_view,
            (turn_left, turn_up),
            dt,
            flying,
        );

        // Dead, the view sinks and tips over with the body.
        let (eye, pitch, roll) = if self.player.alive {
            (eye, pitch, roll)
        } else {
            let fallen = (self.mission.ended_for * 1.6).min(1.0);
            (eye - Vec3::Y * 0.25 * fallen, pitch - 0.3 * fallen, roll + 0.55 * fallen)
        };
        let camera = if let Some(fly) = &mut self.fly {
            fly.yaw += turn_left;
            fly.pitch = (fly.pitch + turn_up).clamp(-1.5, 1.5);
            let (sy, cy) = fly.yaw.sin_cos();
            let (sp, cp) = fly.pitch.sin_cos();
            let forward = Vec3::new(-sy * cp, sp, -cy * cp);
            let right = Vec3::new(cy, 0.0, -sy);
            let (push_right, push_forward) = input.movement();
            let up = f32::from(u8::from(input.held(Action::FlyUp) || input.held(Action::Jump)))
                - f32::from(u8::from(input.held(Action::FlyDown) || input.held(Action::Crouch)));
            let speed = if input.held(Action::Sprint) { 40.0 } else { 8.0 };
            let wanted = (forward * push_forward + right * push_right + Vec3::Y * up) * speed;
            fly.velocity += (wanted - fly.velocity) * (1.0 - (-dt * 10.0).exp());
            fly.position += fly.velocity * dt;
            renderer.settings_mut().camera_roll = 0.0;
            Camera {
                position: fly.position,
                yaw: fly.yaw,
                pitch: fly.pitch,
                fov_y: self.fov,
                near: 0.05,
            }
        } else {
            renderer.settings_mut().camera_roll = roll;
            Camera {
                position: eye,
                yaw,
                pitch,
                fov_y: self.arsenal.fov(self.fov),
                near: 0.03,
            }
        };

        for npc in &mut self.npcs {
            if !npc.active {
                continue;
            }
            let rig = &self.rigs[npc.rig];
            npc.draw(renderer, rig, &self.hold, dt, camera.position);
        }
        self.fx.update(renderer, dt);
        self.physics.step(dt);
        input.end_frame();

        self.audio.listener = camera.position;
        self.audio.listener_forward = camera.forward();
        if self.day_seconds > 0.0 && self.time.hours < self.time_stop {
            self.time.advance(dt * 24.0 / self.day_seconds);
        }
        let mut environment = self.time.environment(&self.place, &self.daylight);
        // The eye opens as the light goes: a level set at dusk asks for more exposure than
        // daylight's, or its shadows are black.
        environment.daylight_illuminance /= self.exposure;
        // A sun on the horizon throws shadows a mile long, which draw as streaks across the
        // far ground: let its direct light go as it sets, and leave the dusk to the sky.
        // The sky is lit by that same sun, so what is taken from the one is given back to
        // the other.
        let height = environment.sun_direction.y;
        let direct = ((height + 0.01) / 0.08).clamp(0.0, 1.0);
        let keep = (direct * direct * (3.0 - 2.0 * direct)).max(self.low_sun);
        environment.sun_illuminance *= keep;
        environment.sky_intensity /= keep;
        self.last_view = View { camera, environment };
        self.last_view
    }
}
