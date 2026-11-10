//! What the people of the level decide to do: stand a post or walk a round until something
//! gives the enemy away, then fight as a soldier would. They move from cover to cover, rise to
//! fire in short bursts and drop back down, reload in shelter, close in on someone who has gone
//! quiet, and tell each other what they have seen.
//!
//! Everyone here is on one of two sides, and fights whoever of the other side they can see: the
//! player is simply one of the resistance.

use crate::audio::Audio;
use crate::fx::Fx;
use crate::level::{Level, Surface};
use crate::nav::Nav;
use crate::npc::{ray_capsule, HitShape, Npc, Zone};
use crate::physics::{Physics, DEBRIS, WORLD};
use crate::player::Player;
use crate::anim::Rig;
use glam::{Mat4, Quat, Vec3};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Team {
    /// The occupying army.
    Directorate,
    /// The resistance: the player's side.
    Resistance,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Mode {
    /// A mannequin: stands as it was put, and does nothing.
    Still,
    /// Unaware: at its post, or walking its round.
    Calm,
    /// Something was heard or glimpsed: it goes to look.
    Wary,
    Fighting,
}

/// Who someone is fighting: the player, or one of the others.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Foe {
    Player,
    Npc(usize),
}

/// What one person knows and intends.
#[derive(Clone, Debug)]
pub struct Brain {
    pub team: Team,
    pub mode: Mode,
    /// Where it stands when it has nothing to do, and the way it faces there.
    pub post: Vec3,
    pub post_yaw: f32,
    /// The round it walks when calm, if it has one.
    pub patrol: Vec<Vec3>,
    patrol_next: usize,
    pause: f32,
    /// One of the resistance who keeps near the player when there is nobody to fight.
    pub follows_player: bool,
    /// Its place among those following, which decides where beside the player it keeps.
    pub slot: usize,

    foe: Option<Foe>,
    /// Whether it can see its foe right now, where it last did, and how long ago.
    sees: bool,
    last_seen: Vec3,
    unseen_for: f32,
    /// How sure it is that it has seen someone: at 1, it has.
    awareness: f32,
    look_timer: f32,

    path: Vec<Vec3>,
    goal: Option<Vec3>,
    repath: f32,
    /// A follower stays where it is until the player first comes up to it.
    pub waits: bool,
    /// Never leaves its post: a sentry in a tower.
    pub rooted: bool,
    /// How long until it may look for a way again, after finding there was none.
    no_way: f32,
    stuck: f32,
    /// The cover it has chosen: an index into the level's.
    cover: Option<usize>,
    in_cover: bool,
    cover_age: f32,

    think: f32,
    /// Up to shoot, or down behind cover; and how long until that changes.
    exposed: bool,
    expose_timer: f32,
    burst: u32,
    shot_timer: f32,
    rounds: u32,
    reloading: f32,
    /// How far its shots stray now, in radians: it shrinks as it holds its aim, and jumps when
    /// it is hit or made to move.
    scatter: f32,
    aim: Vec3,
    /// Seconds for which it is too shaken to shoot straight: it has just been hit.
    flinch: f32,
    seed: u32,
    /// The speed it wants to go, for the animation's sake.
    pub pace: f32,
    since_bark: f32,
}

impl Brain {
    pub fn new(team: Team, post: Vec3, post_yaw: f32, seed: u32) -> Self {
        Self {
            team,
            mode: Mode::Calm,
            post,
            post_yaw,
            patrol: Vec::new(),
            patrol_next: 0,
            pause: 0.0,
            follows_player: false,
            slot: 0,
            foe: None,
            sees: false,
            last_seen: post,
            unseen_for: 100.0,
            awareness: 0.0,
            look_timer: 0.0,
            path: Vec::new(),
            goal: None,
            repath: 0.0,
            waits: false,
            rooted: false,
            no_way: 0.0,
            stuck: 0.0,
            cover: None,
            in_cover: false,
            cover_age: 0.0,
            think: 0.0,
            exposed: false,
            expose_timer: 0.0,
            burst: 0,
            shot_timer: 0.0,
            rounds: 30,
            reloading: 0.0,
            scatter: 0.09,
            aim: Vec3::NEG_Z,
            flinch: 0.0,
            seed: seed.wrapping_mul(2_654_435_761).max(1),
            pace: 0.0,
            since_bark: 10.0,
        }
    }

    fn random(&mut self) -> f32 {
        self.seed ^= self.seed << 13;
        self.seed ^= self.seed >> 17;
        self.seed ^= self.seed << 5;
        (self.seed >> 8) as f32 / (1u32 << 24) as f32
    }

    fn between(&mut self, low: f32, high: f32) -> f32 {
        low + (high - low) * self.random()
    }

    pub fn fighting(&self) -> bool {
        self.mode == Mode::Fighting
    }

    /// Told of an enemy at a place, by a shot heard or a comrade's shout.
    pub fn alert(&mut self, at: Vec3, certain: bool) {
        if self.mode == Mode::Still {
            return;
        }
        if self.mode != Mode::Fighting {
            self.last_seen = at;
            self.unseen_for = 0.0;
            self.goal = None;
            self.path.clear();
            self.mode = if certain { Mode::Fighting } else { Mode::Wary };
            self.think = 0.0;
            self.pause = 0.0;
        } else if !self.sees && self.unseen_for > 1.5 {
            self.last_seen = at;
        }
    }

    /// Forgets the fight: back to its post, as when the one it hunted is gone.
    pub fn calm(&mut self) {
        if self.mode == Mode::Still {
            return;
        }
        self.mode = Mode::Calm;
        self.foe = None;
        self.sees = false;
        self.awareness = 0.0;
        self.unseen_for = 100.0;
        self.goal = None;
        self.path.clear();
        self.cover = None;
        self.in_cover = false;
        self.burst = 0;
    }

    /// It has been hit: its aim goes, and if it wasn't fighting, it is now.
    pub fn hit(&mut self, from: Vec3) {
        self.flinch = 0.6;
        self.scatter = (self.scatter + 0.07).min(0.16);
        self.alert(from, true);
        // Being hit in cover means the cover is no good.
        self.cover_age = 100.0;
    }
}

/// Someone who can be seen and shot at: a snapshot taken at the start of a frame.
#[derive(Clone, Copy, Debug)]
struct Seen {
    foe: Foe,
    team: Team,
    head: Vec3,
    chest: Vec3,
    velocity: Vec3,
    /// How easy to notice, 1 being someone standing in the open.
    profile: f32,
}

/// A noise that gives a position away: a shot, an explosion.
#[derive(Clone, Copy, Debug)]
pub struct Noise {
    pub position: Vec3,
    /// How far it carries, in metres.
    pub reach: f32,
    /// Who made it: only the other side reacts.
    pub team: Team,
}

/// A shot one of the people fired, to be followed to what it hits.
#[derive(Clone, Copy, Debug)]
struct Fired {
    by: usize,
    team: Team,
    origin: Vec3,
    direction: Vec3,
    muzzle: Vec3,
}

/// What the people did to the player this frame.
#[derive(Clone, Debug, Default)]
pub struct Harm {
    /// Damage taken, and where each hit came from.
    pub hits: Vec<(f32, Vec3)>,
    /// Shots that passed close by the player's head.
    pub near_misses: u32,
}

const EYE: f32 = 1.62;
const CROUCH_EYE: f32 = 1.0;
const WALK: f32 = 1.25;
const JOG: f32 = 3.6;
const RUN: f32 = 5.0;
const SIGHT: f32 = 75.0;
const NPC_DAMAGE: f32 = 5.5;
/// How many of those firing on the player at once aim to hit.
const MARKSMEN: u32 = 2;
const ALLY_DAMAGE: f32 = 24.0;
const RATE: f32 = 9.5;

fn flat(v: Vec3) -> Vec3 {
    Vec3::new(v.x, 0.0, v.z)
}

fn yaw_of(direction: Vec3) -> f32 {
    (-direction.x).atan2(-direction.z)
}

fn turn_towards(yaw: f32, wanted: f32, most: f32) -> f32 {
    let mut apart = (wanted - yaw).rem_euclid(std::f32::consts::TAU);
    if apart > std::f32::consts::PI {
        apart -= std::f32::consts::TAU;
    }
    yaw + apart.clamp(-most, most)
}

/// Everything the people need of the game, borrowed apart so that each can be changed while
/// the others are read.
pub struct World<'a> {
    pub npcs: &'a mut Vec<Npc>,
    pub rigs: &'a [Rig],
    pub nav: Option<&'a Nav>,
    pub physics: &'a mut Physics,
    pub player: &'a Player,
    pub level: &'a Level,
    pub fx: &'a mut Fx,
    pub audio: &'a mut Audio,
    pub noises: &'a [Noise],
    /// Which person holds each piece of cover.
    pub cover_owner: &'a mut Vec<Option<usize>>,
    pub player_firing: bool,
    pub time: f32,
}

/// Picks the best cover for someone at `from` fighting a foe at `threat`.
#[allow(clippy::too_many_arguments)]
fn choose_cover(
    nav: &Nav,
    physics: &Physics,
    owners: &[Option<usize>],
    me: usize,
    from: Vec3,
    threat: Vec3,
    push: bool,
    brain: &mut Brain,
) -> Option<usize> {
    let apart = flat(threat - from).length();
    // Closing in, cover nearer the foe is wanted; otherwise, a fighting distance.
    let wanted_range = if push { (apart * 0.6).clamp(8.0, 22.0) } else { apart.clamp(14.0, 30.0) };
    let mut candidates: Vec<(f32, usize)> = Vec::new();
    for (index, cover) in nav.covers.iter().enumerate() {
        if owners[index].is_some_and(|owner| owner != me) {
            continue;
        }
        let travel = flat(cover.position - from).length();
        if travel > 26.0 || (cover.position.y - from.y).abs() > 2.5 {
            continue;
        }
        let to_threat = flat(threat - cover.position);
        let range = to_threat.length();
        if range < 6.0 {
            continue;
        }
        // The cover must stand between it and the foe.
        let facing = cover.toward.dot(to_threat / range.max(0.01));
        if facing < 0.45 {
            continue;
        }
        let score = facing * 2.0 - travel * 0.16 - (range - wanted_range).abs() * 0.12
            + if cover.low { 0.6 } else { 0.0 }
            + brain.random() * 0.8;
        candidates.push((score, index));
    }
    candidates.sort_by(|a, b| b.0.total_cmp(&a.0));
    // Only the likeliest few are worth the rays that prove them.
    for &(_, index) in candidates.iter().take(6) {
        let cover = &nav.covers[index];
        let hidden = !physics.clear_line(cover.position + Vec3::Y * 0.85, threat);
        if !hidden {
            continue;
        }
        let can_fire = !cover.low || physics.clear_line(cover.position + Vec3::Y * 1.5, threat);
        if can_fire || push {
            return Some(index);
        }
    }
    None
}

/// Runs everyone for a frame. Returns what they did to the player.
pub fn update(world: &mut World<'_>, dt: f32) -> Harm {
    let mut harm = Harm::default();
    let player = world.player;
    let mut seen: Vec<Seen> = Vec::with_capacity(world.npcs.len() + 1);
    if player.alive {
        let mut profile = 1.0 - player.crouch * 0.45;
        if player.sprinting {
            profile *= 1.5;
        }
        if world.player_firing {
            profile *= 3.0;
        }
        seen.push(Seen {
            foe: Foe::Player,
            team: Team::Resistance,
            head: player.eye(),
            chest: player.chest(),
            velocity: player.velocity,
            profile,
        });
    }
    for (index, npc) in world.npcs.iter().enumerate() {
        if npc.alive && npc.active {
            seen.push(Seen {
                foe: Foe::Npc(index),
                team: npc.brain.team,
                head: npc.head(),
                chest: npc.chest(),
                velocity: npc.velocity,
                profile: if npc.crouched { 0.6 } else { 1.0 },
            });
        }
    }

    let mut fired: Vec<Fired> = Vec::new();
    let mut shouts: Vec<(usize, Team, Vec3, Vec3)> = Vec::new();
    // How many have a clear shot at the player so far this frame. Only the first few shoot
    // to hit; the rest keep heads down, or a squad would cut anyone down the moment they
    // showed themselves.
    let mut on_player = 0;
    for index in 0..world.npcs.len() {
        let (before, rest) = world.npcs.split_at_mut(index);
        let (npc, after) = rest.split_first_mut().expect("in range");
        if !npc.active || !npc.alive || npc.brain.mode == Mode::Still {
            continue;
        }
        let Some(walker) = npc.walker else {
            continue;
        };
        let rig = &world.rigs[npc.rig];
        let position = npc.position;
        let eye = position + Vec3::Y * if npc.crouched { CROUCH_EYE } else { EYE };
        let brain = &mut npc.brain;
        brain.since_bark += dt;
        brain.flinch = (brain.flinch - dt).max(0.0);
        brain.cover_age += dt;

        let _whole = crate::prof::scope("ai one");
        // --- Hearing.
        for noise in world.noises {
            if noise.team != brain.team && noise.position.distance(position) < noise.reach {
                let wrong = Vec3::new(brain.between(-2.0, 2.0), 0.0, brain.between(-2.0, 2.0));
                brain.alert(noise.position + wrong, false);
            }
        }

        let seeing = crate::prof::scope("ai see");
        // --- Seeing, a few times a second.
        brain.look_timer -= dt;
        if brain.look_timer <= 0.0 {
            brain.look_timer = brain.between(0.1, 0.18);
            let looking = if brain.fighting() { brain.aim } else { npc_forward(npc.yaw) };
            let wide = if brain.fighting() { -0.35 } else { 0.42 };
            let mut best: Option<(f32, Seen)> = None;
            for other in &seen {
                if other.team == brain.team || other.foe == Foe::Npc(index) {
                    continue;
                }
                let to = other.chest - eye;
                let distance = to.length();
                if distance > SIGHT {
                    continue;
                }
                // Very close, someone is noticed whichever way one is looking.
                if distance > 3.0 && looking.dot(to / distance) < wide {
                    continue;
                }
                if !world.physics.clear_line(eye, other.head)
                    && !world.physics.clear_line(eye, other.chest)
                {
                    continue;
                }
                // The foe already being fought is kept, unless another is much nearer.
                let keep = if brain.foe == Some(other.foe) { 0.6 } else { 1.0 };
                let weight = distance * keep;
                if best.is_none_or(|(w, _)| weight < w) {
                    best = Some((weight, *other));
                }
            }
            match best {
                Some((_, other)) => {
                    let distance = other.chest.distance(eye);
                    if brain.fighting() {
                        brain.awareness = 1.0;
                    } else {
                        // Nearer and plainer things are noticed sooner.
                        let rate = (26.0 / distance.max(4.0)).clamp(0.5, 6.0) * other.profile;
                        brain.awareness += rate * 0.14 * if brain.mode == Mode::Wary { 2.0 } else { 1.0 };
                    }
                    if brain.awareness >= 1.0 {
                        if !brain.fighting() {
                            shouts.push((index, brain.team, position, other.chest));
                            if brain.since_bark > 4.0 {
                                brain.since_bark = 0.0;
                                let bark = if brain.team == Team::Directorate { "bark_contact" } else { "bark_ally_contact" };
                                world.audio.at(bark, eye, 1.0);
                            }
                        }
                        brain.mode = Mode::Fighting;
                        brain.foe = Some(other.foe);
                        brain.sees = true;
                        brain.last_seen = other.chest;
                        brain.unseen_for = 0.0;
                    } else if brain.mode == Mode::Calm && brain.awareness > 0.35 {
                        brain.mode = Mode::Wary;
                        brain.last_seen = other.chest;
                        brain.unseen_for = 0.0;
                        brain.pause = 0.9;
                    }
                }
                None => {
                    brain.sees = false;
                    if !brain.fighting() {
                        brain.awareness = (brain.awareness - 0.05).max(0.0);
                    }
                }
            }
        }
        if !brain.sees {
            brain.unseen_for += dt;
        }
        // The foe's place is known exactly while it is seen.
        let foe_now = brain.foe.and_then(|foe| seen.iter().find(|s| s.foe == foe).copied());
        if brain.fighting() && foe_now.is_none() {
            // Whoever it was fighting is dead or gone.
            brain.foe = None;
            brain.sees = false;
        }
        if let (true, Some(foe)) = (brain.sees, foe_now) {
            brain.last_seen = foe.chest;
        }

        drop(seeing);
        let deciding = crate::prof::scope("ai decide");
        // --- Deciding.
        brain.think -= dt;
        let mut want_speed = 0.0;
        let mut face: Option<Vec3> = None;
        let mut shouldered = false;
        let mut crouch = false;
        match brain.mode {
            Mode::Still => {}
            Mode::Calm => {
                brain.exposed = false;
                if brain.follows_player && brain.waits {
                    // Not yet met: stand and watch for the player to come up.
                    let to_player = flat(world.player.feet - position);
                    if to_player.length() < 4.5 {
                        brain.waits = false;
                    }
                    face = Some(to_player);
                } else if brain.follows_player {
                    // Keep a few paces behind and to one side of the player.
                    let side = if brain.slot % 2 == 0 { -1.0 } else { 1.0 };
                    let back = 2.6 + (brain.slot / 2) as f32 * 1.6;
                    let wanted = world.player.feet - world.player.flat_forward() * back
                        + world.player.right() * side * (1.6 + (brain.slot / 2) as f32 * 0.8);
                    let apart = flat(wanted - position).length();
                    if apart > 2.2 && brain.goal.is_none_or(|g| g.distance(wanted) > 2.0) {
                        brain.goal = Some(wanted);
                        brain.repath = 0.0;
                    }
                    want_speed = if apart > 9.0 { RUN } else if apart > 4.0 { JOG } else { WALK * 1.3 };
                    if apart <= 2.2 {
                        brain.goal = None;
                        brain.path.clear();
                        face = Some(world.player.flat_forward());
                    }
                } else if !brain.patrol.is_empty() {
                    if brain.pause > 0.0 {
                        brain.pause -= dt;
                    } else if brain.goal.is_none() {
                        brain.goal = Some(brain.patrol[brain.patrol_next % brain.patrol.len()]);
                        brain.repath = 0.0;
                    }
                    want_speed = WALK;
                } else if flat(brain.post - position).length() > 1.2 {
                    if brain.goal.is_none() {
                        brain.goal = Some(brain.post);
                        brain.repath = 0.0;
                    }
                    want_speed = WALK;
                } else {
                    face = Some(npc_forward(brain.post_yaw));
                }
            }
            Mode::Wary => {
                shouldered = true;
                brain.exposed = false;
                if brain.pause > 0.0 {
                    // A moment looking towards it first.
                    brain.pause -= dt;
                    face = Some(flat(brain.last_seen - position));
                } else {
                    if brain.goal.is_none() && flat(brain.last_seen - position).length() > 4.0 {
                        brain.goal = Some(brain.last_seen);
                        brain.repath = 0.0;
                    }
                    want_speed = WALK * 1.4;
                    if brain.unseen_for > 14.0 {
                        brain.mode = Mode::Calm;
                        brain.awareness = 0.0;
                        brain.goal = None;
                        brain.path.clear();
                    }
                }
            }
            Mode::Fighting => {
                let threat = brain.last_seen;
                let range = threat.distance(position);
                if brain.think <= 0.0 {
                    brain.think = brain.between(0.25, 0.4);
                    // Long out of sight: stop fighting the air.
                    if brain.unseen_for > 22.0 {
                        brain.mode = Mode::Wary;
                        brain.awareness = 0.4;
                        brain.unseen_for = 6.0;
                        if let Some(cover) = brain.cover.take() {
                            world.cover_owner[cover] = None;
                        }
                        brain.in_cover = false;
                    } else if let Some(nav) = world.nav {
                        // Is the cover still good? Not if the foe can see behind it, has come
                        // too close, or has been out of sight long enough to go and find.
                        let push = brain.unseen_for > 4.5;
                        let stale = match brain.cover {
                            None => true,
                            Some(cover) => {
                                let at = nav.covers[cover].position;
                                let flanked = brain.in_cover
                                    && brain.sees
                                    && world.physics.clear_line(at + Vec3::Y * 0.8, threat);
                                flanked
                                    || flat(threat - at).length() < 5.0
                                    || brain.cover_age > if push { 5.0 } else { brain.between(9.0, 16.0) }
                            }
                        };
                        if stale {
                            let chosen = choose_cover(
                                nav,
                                world.physics,
                                world.cover_owner,
                                index,
                                position,
                                threat,
                                push,
                                brain,
                            );
                            if let Some(old) = brain.cover.take() {
                                world.cover_owner[old] = None;
                            }
                            brain.in_cover = false;
                            brain.cover_age = 0.0;
                            match chosen {
                                Some(cover) => {
                                    world.cover_owner[cover] = Some(index);
                                    brain.cover = Some(cover);
                                    brain.goal = Some(nav.covers[cover].position - nav.covers[cover].toward * 0.15);
                                    brain.repath = 0.0;
                                }
                                None if push => {
                                    // Nothing to hide behind on the way: go and look anyway.
                                    brain.goal = Some(threat);
                                    brain.repath = 0.0;
                                }
                                None => {}
                            }
                        }
                    }
                }
                let moving_to_cover = brain.goal.is_some();
                want_speed = if moving_to_cover {
                    if range > 22.0 || brain.unseen_for > 3.0 { RUN } else { JOG }
                } else {
                    0.0
                };
                // Up and down behind cover: up to shoot, down to rest and to reload.
                brain.expose_timer -= dt;
                if brain.expose_timer <= 0.0 {
                    brain.exposed = !brain.exposed;
                    brain.expose_timer = if brain.exposed {
                        brain.between(1.6, 3.6)
                    } else {
                        brain.between(0.8, 2.2)
                    };
                }
                if brain.reloading > 0.0 {
                    brain.reloading -= dt;
                    brain.exposed = false;
                    if brain.reloading <= 0.0 {
                        brain.rounds = 30;
                    }
                }
                let settled = !moving_to_cover;
                let low_cover = brain.cover.zip(world.nav).is_some_and(|(c, nav)| nav.covers[c].low);
                crouch = settled && brain.in_cover && low_cover && !brain.exposed;
                shouldered = settled || range < 16.0;
                face = Some(flat(threat - position));
                // Fire: in bursts, while up, with the foe in view or lately there.
                let pressing = on_player;
                if brain.foe == Some(Foe::Player) && brain.sees {
                    on_player += 1;
                }
                brain.shot_timer -= dt;
                let can_see_target = brain.sees || brain.unseen_for < 2.5;
                let up = (brain.exposed || !brain.in_cover) && (settled || range < 14.0);
                if up && can_see_target && brain.rounds > 0 && brain.reloading <= 0.0 && brain.flinch <= 0.0 {
                    if brain.burst == 0 && brain.shot_timer <= 0.0 {
                        brain.burst = 2 + (brain.random() * 4.0) as u32;
                    }
                    if brain.burst > 0 && brain.shot_timer <= 0.0 {
                        brain.burst -= 1;
                        brain.rounds -= 1;
                        brain.shot_timer = if brain.burst == 0 {
                            brain.between(0.5, 1.5)
                        } else {
                            1.0 / RATE
                        };
                        // Aim where the foe will be, less well the faster it moves and the
                        // further off it is.
                        let lead = foe_now.map_or(Vec3::ZERO, |foe| foe.velocity * (range / 300.0));
                        let target = if brain.sees { threat + lead } else { threat };
                        let aim = (target - eye).normalize_or(brain.aim);
                        let moving = foe_now.map_or(0.0, |foe| flat(foe.velocity).length());
                        let wild = if brain.foe == Some(Foe::Player) && pressing >= MARKSMEN { 0.1 } else { 0.0 };
                        // A rifle shot from the shoulder in a fight spreads with the range.
                        let scatter = brain.scatter * (1.0 + moving * 0.22)
                            + if settled { 0.0 } else { 0.03 }
                            + (range - 8.0).max(0.0) * 0.0007
                            + wild;
                        let across = aim.cross(Vec3::Y).normalize_or(Vec3::X);
                        let upward = across.cross(aim);
                        let radius = scatter * brain.random().sqrt();
                        let angle = brain.random() * std::f32::consts::TAU;
                        let direction =
                            (aim + across * (radius * angle.cos()) + upward * (radius * angle.sin())).normalize();
                        fired.push(Fired {
                            by: index,
                            team: brain.team,
                            origin: eye,
                            direction,
                            muzzle: eye + aim * 0.6 - Vec3::Y * 0.12,
                        });
                    }
                } else if brain.rounds == 0 && brain.reloading <= 0.0 {
                    brain.reloading = 2.6;
                    brain.burst = 0;
                }
                // Holding still on a foe in view steadies the aim.
                let steady = if settled && brain.sees { 0.035 } else { -0.03 };
                brain.scatter = (brain.scatter - steady * dt).clamp(0.02, 0.16);
            }
        }

        // A sentry on a tower fights from where it stands.
        if brain.rooted {
            brain.goal = None;
            brain.path.clear();
            want_speed = 0.0;
        }
        drop(deciding);
        let walking = crate::prof::scope("ai walk");
        // --- Walking: along the path to the goal.
        let nav = world.nav;
        brain.repath -= dt;
        if let (Some(goal), Some(nav)) = (brain.goal, nav) {
            if brain.repath <= 0.0 && brain.no_way <= 0.0 {
                brain.repath = brain.between(1.2, 2.0);
                let _pathing = crate::prof::scope("ai path");
                match nav.path(position, goal) {
                    Some(path) => brain.path = path,
                    None => {
                        // No way there: don't ask again at once, however much it is wanted.
                        brain.path.clear();
                        brain.goal = None;
                        brain.no_way = brain.between(1.5, 2.5);
                    }
                }
            }
        }
        brain.no_way = (brain.no_way - dt).max(0.0);
        let mut velocity = Vec3::ZERO;
        while let Some(&next) = brain.path.first() {
            if flat(next - position).length() < 0.45 {
                brain.path.remove(0);
            } else {
                break;
            }
        }
        if let Some(&next) = brain.path.first() {
            let direction = flat(next - position).normalize_or_zero();
            // Slow into the last corner rather than overrun it.
            let left = flat(next - position).length();
            let speed = if brain.path.len() == 1 { want_speed.min(left * 3.5 + 0.6) } else { want_speed };
            velocity = direction * speed;
        } else if brain.goal.is_some() {
            // Arrived.
            brain.goal = None;
            if brain.mode == Mode::Calm && !brain.patrol.is_empty() {
                brain.patrol_next = (brain.patrol_next + 1) % brain.patrol.len();
                brain.pause = brain.between(2.0, 5.0);
            }
            if brain.mode == Mode::Fighting && brain.cover.is_some() {
                brain.in_cover = true;
                brain.exposed = false;
                brain.expose_timer = brain.between(0.4, 1.0);
            }
            if brain.mode == Mode::Wary {
                brain.pause = brain.between(2.0, 3.5);
            }
        }
        // Keep off each other's toes.
        for other in before.iter().chain(after.iter()) {
            if !other.active || !other.alive {
                continue;
            }
            let apart = flat(position - other.position);
            let distance = apart.length();
            if distance < 0.85 && distance > 1.0e-3 {
                velocity += apart / distance * (0.85 - distance) * 3.0;
            }
        }
        let apart = flat(position - world.player.feet);
        if apart.length() < 0.9 && apart.length() > 1.0e-3 {
            velocity += apart.normalize() * (0.9 - apart.length()) * 4.0;
        }
        // Not getting anywhere: think again.
        let wanted = flat(velocity).length();
        if wanted > 0.5 && flat(npc.velocity).length() < wanted * 0.25 {
            brain.stuck += dt;
            if brain.stuck > 1.2 {
                brain.stuck = 0.0;
                brain.repath = 0.0;
                brain.cover_age = 100.0;
            }
        } else {
            brain.stuck = 0.0;
        }
        brain.pace = wanted;

        let was = npc.position;
        let stepping = crate::prof::scope("ai step");
        #[cfg(not(target_arch = "wasm32"))]
        let began = std::time::Instant::now();
        let walked = world.physics.walk(walker, velocity, npc.vertical, dt);
        #[cfg(not(target_arch = "wasm32"))]
        if began.elapsed().as_secs_f32() > 0.004 {
            log::warn!("slow step: {:.1} ms at {:.2} {:.2} {:.2}", began.elapsed().as_secs_f32() * 1000.0, position.x, position.y, position.z);
        }
        drop(stepping);
        npc.vertical = walked.vertical;
        npc.position = walked.feet;
        npc.velocity = (npc.position - was) / dt.max(1.0e-4);
        npc.speed = flat(npc.velocity).length();
        npc.crouched = crouch;

        drop(walking);
        let _aiming = crate::prof::scope("ai aim");
        // --- Facing and aiming.
        let brain = &mut npc.brain;
        let moving = wanted > 0.8;
        let body_wanted = if moving && !(shouldered && wanted < JOG * 0.9 && brain.sees) {
            Some(flat(velocity))
        } else {
            face
        };
        if let Some(direction) = body_wanted.filter(|d| d.length_squared() > 1.0e-4) {
            npc.yaw = turn_towards(npc.yaw, yaw_of(direction), dt * if moving { 8.0 } else { 5.0 });
        }
        let aim_wanted = if brain.fighting() {
            (brain.last_seen - eye).normalize_or(npc_forward(npc.yaw))
        } else {
            face.unwrap_or(npc_forward(npc.yaw)).normalize_or(npc_forward(npc.yaw))
        };
        brain.aim = brain.aim.lerp(aim_wanted, 1.0 - (-dt * 9.0f32).exp()).normalize_or(aim_wanted);
        let forward = npc_forward(npc.yaw);
        let left = Vec3::new(-npc.yaw.cos(), 0.0, npc.yaw.sin());
        let level_aim = flat(brain.aim);
        let aim_yaw = level_aim.dot(left).atan2(level_aim.dot(forward));
        // Turned too far from where it is going, the rifle comes down until it stops.
        let can_aim = aim_yaw.abs() < 1.45;
        let shoulder = if shouldered && can_aim && brain.reloading <= 0.0 { 1.0 } else { 0.0 };
        npc.stance.shouldered += (shoulder - npc.stance.shouldered) * (1.0 - (-dt * 7.0f32).exp());
        npc.stance.aim_yaw += (aim_yaw.clamp(-1.4, 1.4) * shoulder - npc.stance.aim_yaw) * (1.0 - (-dt * 10.0f32).exp());
        npc.stance.aim_pitch +=
            (brain.aim.y.clamp(-0.8, 0.8).asin() * shoulder - npc.stance.aim_pitch) * (1.0 - (-dt * 10.0f32).exp());
        npc.stance.reload = if brain.reloading > 0.0 { 1.0 - brain.reloading / 2.6 } else { -1.0 };
        npc.stance.recoil = (npc.stance.recoil - dt * 9.0).max(0.0);
        let _ = rig;
    }

    // What one sees, those near it of its side soon know.
    for (shouter, team, from, at) in shouts {
        for (index, npc) in world.npcs.iter_mut().enumerate() {
            if index != shouter && npc.active && npc.alive && npc.brain.team == team && npc.position.distance(from) < 34.0 {
                npc.brain.alert(at, true);
            }
        }
    }

    // --- The shots fired.
    for shot in fired {
        const REACH: f32 = 300.0;
        let hit = world
            .physics
            .raycast(shot.origin, shot.direction, REACH, WORLD | DEBRIS);
        let mut reach = hit.map_or(REACH, |h| h.distance);
        let mut struck: Option<(Foe, Zone)> = None;
        if shot.team == Team::Directorate && world.player.alive {
            let feet = world.player.feet;
            let top = world.player.eye();
            let shapes = [
                HitShape { a: feet + Vec3::Y * 0.3, b: top - Vec3::Y * 0.25, radius: 0.3, zone: Zone::Torso },
                HitShape { a: top - Vec3::Y * 0.05, b: top + Vec3::Y * 0.06, radius: 0.13, zone: Zone::Head },
            ];
            for shape in &shapes {
                if let Some(t) = ray_capsule(shot.origin, shot.direction, reach, shape) {
                    reach = t;
                    struck = Some((Foe::Player, shape.zone));
                }
            }
            if struck.is_none() {
                // A shot that goes by the head is heard going by.
                let to_head = top - shot.origin;
                let along = to_head.dot(shot.direction);
                if along > 0.0 && along < reach {
                    let miss = (to_head - shot.direction * along).length();
                    if miss < 1.3 {
                        harm.near_misses += 1;
                        world.audio.at("whiz", shot.origin + shot.direction * along, 1.0);
                    }
                }
            }
        }
        for (index, npc) in world.npcs.iter().enumerate() {
            if !npc.active || !npc.alive || npc.brain.team == shot.team || index == shot.by {
                continue;
            }
            let to_chest = npc.chest() - shot.origin;
            let along = to_chest.dot(shot.direction);
            if along < 0.0 || along > reach + 1.0 || (to_chest - shot.direction * along).length_squared() > 2.0 {
                continue;
            }
            for shape in npc.hit_shapes(&world.rigs[npc.rig]) {
                if let Some(t) = ray_capsule(shot.origin, shot.direction, reach, &shape) {
                    reach = t;
                    struck = Some((Foe::Npc(index), shape.zone));
                }
            }
        }
        let end = shot.origin + shot.direction * reach;
        let shooter = &mut world.npcs[shot.by];
        shooter.stance.recoil = 1.0;
        let (muzzle, _) = shooter.muzzle();
        let muzzle = if muzzle.distance(shot.muzzle) < 1.5 { muzzle } else { shot.muzzle };
        world.fx.muzzle_flash(
            Mat4::from_rotation_translation(Quat::from_rotation_arc(Vec3::NEG_Z, shot.direction), muzzle),
            0.8,
        );
        world.fx.tracer(muzzle, end);
        world.audio.at("rifle_shot", muzzle, 1.0);
        match struck {
            Some((Foe::Player, zone)) => {
                let damage = NPC_DAMAGE * if zone == Zone::Head { 1.8 } else { 1.0 };
                harm.hits.push((damage, shot.origin));
            }
            Some((Foe::Npc(index), zone)) => {
                // The cell's own are hard to kill: the story needs them, and a friend who
                // falls in the first exchange is no company.
                let damage = if shot.team == Team::Resistance { ALLY_DAMAGE } else { NPC_DAMAGE * 0.45 };
                let damage = damage * if zone == Zone::Head { 2.5 } else { 1.0 };
                world.fx.impact(end, -shot.direction, Surface::Flesh);
                let rig = &world.rigs[world.npcs[index].rig];
                let victim = &mut world.npcs[index];
                victim.brain.hit(shot.origin);
                victim.hurt(damage, shot.direction, zone, rig);
            }
            None => {
                if let Some(hit) = hit {
                    let surface = world.level.surface_of(hit.instance);
                    world.fx.impact(hit.point, hit.normal, surface);
                    if hit.point.distance(world.player.eye()) < 25.0 {
                        world.audio.at("impact_concrete", hit.point, 0.8);
                    }
                }
            }
        }
    }
    harm
}

fn npc_forward(yaw: f32) -> Vec3 {
    Vec3::new(-yaw.sin(), 0.0, -yaw.cos())
}
