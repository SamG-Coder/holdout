//! The player's weapons: what each one is, firing and reloading them, and the first-person
//! view of them, with arms that hold them wherever recoil, sway and a reload carry them.
//!
//! A weapon's own space has its muzzle towards -Z, +Y up and +X to the firer's right, with its
//! origin at the trigger: the same directions as the camera's, so a weapon's place in the view
//! is just where its trigger is, in metres right of, above and behind the eye.

use crate::actors::Group;
use crate::anim::{place_hands, rifle_hands, RifleHold, Rig};
use crate::audio::Audio;
use crate::fx::Fx;
use crate::ik::Posed;
use crate::input::{Action, Input};
use crate::level::Level;
use crate::physics::Physics;
use crate::player::Player;
use glam::{EulerRot, Mat4, Quat, Vec3};
use solstice_render::Renderer;

/// What kind of thing a moving part of a weapon is.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Part {
    /// Never moves relative to the weapon.
    Fixed,
    /// Comes out and goes back in a reload.
    Magazine,
    /// Flies back by this many metres with every shot, and stays back when empty.
    Bolt(f32),
    /// Pulled back by this many metres when a round is chambered by hand.
    Charge(f32),
}

/// A place in the view: where the trigger is, in metres right of, above and ahead of the eye
/// (ahead being negative Z), and how the weapon is turned: yaw to the left, pitch up, and roll,
/// in degrees.
#[derive(Clone, Copy, Debug)]
pub struct ViewPose {
    pub position: Vec3,
    pub turn: Vec3,
}

impl ViewPose {
    const fn new(position: [f32; 3], turn: [f32; 3]) -> Self {
        Self {
            position: Vec3::new(position[0], position[1], position[2]),
            turn: Vec3::new(turn[0], turn[1], turn[2]),
        }
    }

    fn lerp(&self, other: &Self, t: f32) -> Self {
        Self {
            position: self.position.lerp(other.position, t),
            turn: self.turn.lerp(other.turn, t),
        }
    }

    fn matrix(&self) -> Mat4 {
        let rotation = Quat::from_euler(
            EulerRot::YXZ,
            self.turn.x.to_radians(),
            self.turn.y.to_radians(),
            self.turn.z.to_radians(),
        );
        Mat4::from_rotation_translation(rotation, self.position)
    }
}

/// Everything that makes one weapon what it is.
#[derive(Clone, Debug)]
pub struct WeaponDef {
    pub name: &'static str,
    /// What the interface calls it.
    pub title: &'static str,
    /// The level's tags for its first-person parts, and how each moves.
    pub parts: &'static [(&'static str, Part)],
    /// The level's tag for the one-piece copy that others carry and that lies on the ground.
    pub whole: &'static str,
    pub damage: f32,
    pub head_multiplier: f32,
    pub limb_multiplier: f32,
    /// Rounds a minute.
    pub rate: f32,
    pub automatic: bool,
    pub magazine: u32,
    pub reserve: u32,
    pub pellets: u32,
    /// Seconds to reload with a round still chambered, and from empty.
    pub reload_seconds: f32,
    pub reload_empty_seconds: f32,
    /// How far shots stray, in radians: from the hip, aimed, extra per shot, extra moving.
    pub spread_hip: f32,
    pub spread_aimed: f32,
    pub spread_bloom: f32,
    pub spread_moving: f32,
    /// How far each shot lifts the view, in radians, and how far it may pull to either side.
    pub recoil_pitch: f32,
    pub recoil_yaw: f32,
    /// How far each shot shoves the weapon back in the hands, in metres.
    pub kick: f32,
    pub aim_seconds: f32,
    /// The field of view when aimed, as a share of the unaimed one.
    pub aim_zoom: f32,
    pub hip: ViewPose,
    pub aimed: ViewPose,
    pub sprint: ViewPose,
    pub muzzle: Vec3,
    pub eject: Vec3,
    pub hold: RifleHold,
    /// Where the hand that changes the magazine holds it, on the weapon.
    pub magazine_grip: Vec3,
    pub shot_sound: &'static str,
    /// How far the shot is heard by those it wasn't aimed at, in metres.
    pub loudness: f32,
}

pub fn carbine() -> WeaponDef {
    WeaponDef {
        name: "carbine",
        title: "MK4 CARBINE",
        parts: &[
            ("fp_carbine_body", Part::Fixed),
            ("fp_carbine_mag", Part::Magazine),
            ("fp_carbine_bolt", Part::Bolt(0.055)),
            ("fp_carbine_charge", Part::Charge(0.06)),
            ("fp_carbine_dot", Part::Fixed),
        ],
        whole: "carbine_whole",
        damage: 34.0,
        head_multiplier: 3.0,
        limb_multiplier: 0.75,
        rate: 760.0,
        automatic: true,
        magazine: 30,
        reserve: 150,
        pellets: 1,
        reload_seconds: 2.25,
        reload_empty_seconds: 2.75,
        spread_hip: 0.026,
        spread_aimed: 0.0016,
        spread_bloom: 0.0042,
        spread_moving: 0.02,
        recoil_pitch: 0.0125,
        recoil_yaw: 0.0065,
        kick: 0.022,
        aim_seconds: 0.2,
        aim_zoom: 0.74,
        // Low and canted up toward the middle of the picture: the stock stays under its edge.
        hip: ViewPose::new([0.125, -0.19, -0.355], [6.0, 2.4, -2.5]),
        // The red dot's axis is 101.5 mm above the trigger: this puts it through the eye.
        aimed: ViewPose::new([0.0, -0.1015, -0.192], [0.0, 0.0, 0.0]),
        // Running, the rifle is carried high at the shoulder, muzzle up and out of the way.
        sprint: ViewPose::new([0.17, -0.25, -0.33], [-6.0, 40.0, -14.0]),
        muzzle: Vec3::new(0.0, 0.035, -0.505),
        eject: Vec3::new(0.022, 0.036, 0.0),
        hold: RifleHold {
            grip: Vec3::new(0.0, -0.062, 0.036),
            support: Vec3::new(0.0, -0.008, -0.235),
            butt: Vec3::new(0.0, 0.004, 0.318),
            muzzle: Vec3::new(0.0, 0.035, -0.505),
            support_fingers: crate::anim::UNDER_FINGERS,
            support_palm: crate::anim::UNDER_PALM,
        },
        magazine_grip: Vec3::new(0.0, -0.165, -0.085),
        shot_sound: "carbine_shot",
        loudness: 70.0,
    }
}

/// The P9: a 9 mm sidearm. Quick to bring up and quick to reload, for when the carbine is dry.
pub fn pistol() -> WeaponDef {
    WeaponDef {
        name: "pistol",
        title: "P9 PISTOL",
        parts: &[
            ("fp_pistol_body", Part::Fixed),
            ("fp_pistol_mag", Part::Magazine),
            ("fp_pistol_slide", Part::Bolt(0.034)),
        ],
        whole: "pistol_whole",
        damage: 26.0,
        head_multiplier: 2.6,
        limb_multiplier: 0.75,
        rate: 430.0,
        automatic: false,
        magazine: 15,
        reserve: 75,
        pellets: 1,
        reload_seconds: 1.55,
        reload_empty_seconds: 1.9,
        spread_hip: 0.022,
        spread_aimed: 0.0042,
        spread_bloom: 0.0075,
        spread_moving: 0.012,
        recoil_pitch: 0.021,
        recoil_yaw: 0.008,
        kick: 0.03,
        aim_seconds: 0.13,
        aim_zoom: 0.88,
        // Held out in both hands, a little below the line of sight.
        hip: ViewPose::new([0.07, -0.108, -0.39], [2.0, 3.0, -2.0]),
        // The sights stand 49 mm above the trigger.
        aimed: ViewPose::new([0.0, -0.049, -0.4], [0.0, 0.0, 0.0]),
        // Running, it is drawn in to the chest, muzzle up.
        sprint: ViewPose::new([0.1, -0.2, -0.3], [42.0, 8.0, -6.0]),
        muzzle: Vec3::new(0.0, 0.030, -0.09),
        eject: Vec3::new(0.014, 0.04, 0.022),
        hold: RifleHold {
            grip: Vec3::new(0.0, -0.05, 0.082),
            // The other hand wraps the first, from the left and a little below.
            support: Vec3::new(-0.012, -0.062, 0.07),
            butt: Vec3::new(0.0, 0.01, 0.12),
            muzzle: Vec3::new(0.0, 0.030, -0.09),
            support_fingers: Vec3::new(0.2, -0.3, -0.93),
            support_palm: Vec3::new(0.97, 0.08, 0.2),
        },
        magazine_grip: Vec3::new(0.0, -0.115, 0.09),
        shot_sound: "pistol_shot",
        loudness: 55.0,
    }
}

/// A weapon in the player's hands or on their back: its kind, and what is in it.
#[derive(Clone, Debug)]
pub struct Gun {
    pub def: WeaponDef,
    pub rounds: u32,
    pub reserve: u32,
}

impl Gun {
    pub fn new(def: WeaponDef) -> Self {
        Self {
            rounds: def.magazine,
            reserve: def.reserve,
            def,
        }
    }
}

/// A shot fired by the player, for the game to follow to whatever it hits.
#[derive(Clone, Copy, Debug)]
pub struct Shot {
    pub origin: Vec3,
    pub direction: Vec3,
    pub damage: f32,
    pub head_multiplier: f32,
    pub limb_multiplier: f32,
    /// Where the tracer starts: the muzzle, in the world.
    pub muzzle: Vec3,
    pub loudness: f32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Phase {
    Ready,
    /// Seconds into a reload, and whether it began with the chamber empty.
    Reloading(f32, bool),
    /// Seconds into putting this weapon away, and which one comes out next.
    Lowering(f32, usize),
    Raising(f32),
}

const SWAP_SECONDS: f32 = 0.32;

fn ramp(t: f32, from: f32, to: f32) -> f32 {
    let x = ((t - from) / (to - from)).clamp(0.0, 1.0);
    x * x * (3.0 - 2.0 * x)
}

/// 0, rising to 1 between `a` and `b`, holding, and falling back between `c` and `d`.
fn window(t: f32, a: f32, b: f32, c: f32, d: f32) -> f32 {
    ramp(t, a, b) - ramp(t, c, d)
}

/// A value on a spring: pushed, it comes back and settles.
#[derive(Clone, Copy, Debug, Default)]
struct Spring {
    value: Vec3,
    velocity: Vec3,
}

impl Spring {
    fn update(&mut self, dt: f32, stiffness: f32, damping: f32) {
        // Small steps keep a stiff spring stable at low frame rates.
        let steps = (dt / 0.004).ceil().max(1.0) as u32;
        let h = dt / steps as f32;
        for _ in 0..steps {
            let acceleration = -stiffness * self.value - damping * self.velocity;
            self.velocity += acceleration * h;
            self.value += self.velocity * h;
        }
    }
}

/// The first-person parts of one weapon.
struct Parts {
    groups: Vec<(Group, Part)>,
}

/// The weapons the player carries, and the view of the one in their hands.
pub struct Arsenal {
    pub guns: Vec<Gun>,
    pub current: usize,
    parts: Vec<Parts>,
    arms: Option<Group>,
    arms_rig: Option<usize>,
    phase: Phase,
    cooldown: f32,
    /// 0 from the hip, 1 aimed down the sights.
    pub aim: f32,
    /// How far shots have bloomed with firing, in radians.
    bloom: f32,
    /// The weapon thrown about in the hands: its place, and its turn.
    kick: Spring,
    twist: Spring,
    /// The view thrown about by recoil, beyond what is given to the player's own aim.
    punch: Spring,
    /// The weapon trailing behind a turning view.
    sway: Vec3,
    sprint: f32,
    blocked: f32,
    /// The bolt's travel, 1 fully back.
    bolt: f32,
    time: f32,
    seed: u32,
    shots_in_burst: u32,
    /// The weapon's place in the world this frame.
    world: Mat4,
    reload_marks: u32,
    pub hit_marker: f32,
}

impl Arsenal {
    pub fn new(level: &Level, renderer: &mut Renderer, guns: Vec<Gun>, arms_rig: Option<usize>) -> Self {
        let parts = guns
            .iter()
            .map(|gun| Parts {
                groups: gun
                    .def
                    .parts
                    .iter()
                    .filter_map(|(tag, part)| {
                        level
                            .one(tag)
                            .map(|placed| (Group::new(&placed, renderer), *part))
                    })
                    .collect(),
            })
            .collect();
        let arms = level.one("fp_arms").map(|placed| Group::new(&placed, renderer));
        let mut arsenal = Self {
            guns,
            current: 0,
            parts,
            arms,
            arms_rig,
            phase: Phase::Raising(0.0),
            cooldown: 0.0,
            aim: 0.0,
            bloom: 0.0,
            kick: Spring::default(),
            twist: Spring::default(),
            punch: Spring::default(),
            sway: Vec3::ZERO,
            sprint: 0.0,
            blocked: 0.0,
            bolt: 0.0,
            time: 0.0,
            seed: 0x2545_f491,
            shots_in_burst: 0,
            world: Mat4::IDENTITY,
            reload_marks: 0,
            hit_marker: 0.0,
        };
        arsenal.show_only_current(renderer);
        arsenal
    }

    fn show_only_current(&mut self, renderer: &mut Renderer) {
        for (index, parts) in self.parts.iter_mut().enumerate() {
            for (group, _) in &mut parts.groups {
                group.set_hidden(renderer, index != self.current);
            }
        }
    }

    fn random(&mut self) -> f32 {
        self.seed ^= self.seed << 13;
        self.seed ^= self.seed >> 17;
        self.seed ^= self.seed << 5;
        (self.seed >> 8) as f32 / (1u32 << 24) as f32
    }

    pub fn gun(&self) -> &Gun {
        &self.guns[self.current]
    }

    pub fn reloading(&self) -> bool {
        matches!(self.phase, Phase::Reloading(..))
    }

    /// How far shots stray now, in radians: for the crosshair.
    pub fn spread(&self, player: &Player) -> f32 {
        let def = &self.gun().def;
        let base = def.spread_hip + (def.spread_aimed - def.spread_hip) * self.aim;
        let moving = def.spread_moving * player.pace().min(1.6) * (1.0 - self.aim * 0.7);
        let airborne = if player.grounded { 0.0 } else { 0.03 };
        base + moving + airborne + self.bloom
    }

    /// The field of view to draw with, given the unaimed one.
    pub fn fov(&self, base: f32) -> f32 {
        let zoom = self.gun().def.aim_zoom;
        base * (1.0 + (zoom - 1.0) * self.aim)
    }

    /// How far recoil turns the view this frame, beyond the player's own aim: yaw, pitch and
    /// roll, in radians.
    pub fn view_punch(&self) -> Vec3 {
        self.punch.value
    }

    /// Whether the weapon is up and can be aimed: the crosshair hides while it isn't.
    pub fn ready(&self) -> bool {
        self.phase == Phase::Ready && self.sprint < 0.4
    }

    /// Takes rounds for the current weapon. Returns how many were taken.
    pub fn add_rounds(&mut self, rounds: u32) -> u32 {
        let gun = &mut self.guns[self.current];
        let room = gun.def.reserve.saturating_sub(gun.reserve);
        let taken = rounds.min(room);
        gun.reserve += taken;
        taken
    }

    /// Runs the weapons for a frame: the trigger, the reload, changing weapon, and aiming.
    /// Returns the shots fired. `eye` and `forward` are the view's, after recoil.
    #[allow(clippy::too_many_arguments)]
    pub fn update(
        &mut self,
        renderer: &mut Renderer,
        input: &Input,
        player: &mut Player,
        physics: &Physics,
        fx: &mut Fx,
        audio: &mut Audio,
        dt: f32,
        frozen: bool,
    ) -> Vec<Shot> {
        self.time += dt;
        self.cooldown = (self.cooldown - dt).max(0.0);
        self.hit_marker = (self.hit_marker - dt * 4.0).max(0.0);
        let def = self.gun().def.clone();
        let mut shots = Vec::new();

        // Changing weapon.
        if !frozen && self.phase == Phase::Ready && self.guns.len() > 1 {
            let wanted = if input.pressed(Action::Primary) {
                Some(0)
            } else if input.pressed(Action::Secondary) {
                Some(1)
            } else if input.pressed(Action::SwapWeapon) || input.wheel.abs() > 0.5 {
                Some((self.current + 1) % self.guns.len())
            } else {
                None
            };
            if let Some(wanted) = wanted.filter(|w| *w != self.current && *w < self.guns.len()) {
                self.phase = Phase::Lowering(0.0, wanted);
                audio.own("weapon_lower", 0.6);
            }
        }
        match self.phase {
            Phase::Lowering(time, next) => {
                let time = time + dt;
                if time >= SWAP_SECONDS {
                    self.current = next;
                    self.show_only_current(renderer);
                    self.phase = Phase::Raising(0.0);
                    self.bolt = 0.0;
                    audio.own("weapon_raise", 0.6);
                } else {
                    self.phase = Phase::Lowering(time, next);
                }
            }
            Phase::Raising(time) => {
                let time = time + dt;
                self.phase = if time >= SWAP_SECONDS {
                    Phase::Ready
                } else {
                    Phase::Raising(time)
                };
            }
            Phase::Reloading(time, empty) => {
                let length = if empty {
                    def.reload_empty_seconds
                } else {
                    def.reload_seconds
                };
                let before = time / length;
                let time = time + dt;
                let now = time / length;
                // The sounds of a reload, each as its moment passes.
                let scale = if empty { def.reload_seconds / def.reload_empty_seconds } else { 1.0 };
                for (mark, (at, sound)) in [(0.2 * scale, "mag_out"), (0.68 * scale, "mag_in")]
                    .into_iter()
                    .enumerate()
                {
                    if before < at && now >= at && self.reload_marks & (1 << mark) == 0 {
                        self.reload_marks |= 1 << mark;
                        audio.own(sound, 0.9);
                    }
                }
                if before < 0.7 * scale && now >= 0.7 * scale {
                    let gun = &mut self.guns[self.current];
                    let taken = gun.def.magazine.saturating_sub(gun.rounds).min(gun.reserve);
                    gun.rounds += taken;
                    gun.reserve -= taken;
                }
                if empty && before < 0.86 && now >= 0.86 {
                    audio.own("bolt_release", 0.9);
                    self.bolt = 0.0;
                }
                self.phase = if time >= length {
                    Phase::Ready
                } else {
                    Phase::Reloading(time, empty)
                };
            }
            Phase::Ready => {}
        }

        // Sprinting lowers the weapon; pulling the trigger or aiming stops the sprint.
        let wants_fire = !frozen
            && if def.automatic {
                input.held(Action::Fire)
            } else {
                input.pressed(Action::Fire)
            };
        let wants_aim = !frozen && input.held(Action::Aim);
        let sprinting = player.sprinting && !wants_fire && !wants_aim;
        let rate = if sprinting { 7.0 } else { 11.0 };
        self.sprint += (f32::from(u8::from(sprinting)) - self.sprint) * (1.0 - (-dt * rate).exp());

        // Aiming.
        let can_aim = wants_aim && self.phase == Phase::Ready && self.sprint < 0.5;
        let step = dt / def.aim_seconds.max(0.01);
        self.aim = if can_aim {
            (self.aim + step).min(1.0)
        } else {
            (self.aim - step * 1.3).max(0.0)
        };

        // Reloading, asked for or because the magazine is empty.
        let gun = &self.guns[self.current];
        let wants_reload = !frozen
            && (input.pressed(Action::Reload) || (gun.rounds == 0 && input.pressed(Action::Fire)));
        if wants_reload && self.phase == Phase::Ready && gun.rounds < gun.def.magazine && gun.reserve > 0 {
            self.phase = Phase::Reloading(0.0, gun.rounds == 0);
            self.reload_marks = 0;
            audio.own("reload_start", 0.7);
        }

        // Firing.
        if !wants_fire {
            self.shots_in_burst = 0;
        }
        if wants_fire && self.phase == Phase::Ready && self.cooldown <= 0.0 && self.sprint < 0.35 {
            if self.guns[self.current].rounds == 0 {
                if input.pressed(Action::Fire) {
                    audio.own("dry_fire", 0.8);
                }
            } else {
                self.guns[self.current].rounds -= 1;
                self.cooldown = 60.0 / def.rate;
                let spread = self.spread(player);
                let eye = player.eye();
                let forward = player.forward();
                let right = forward.cross(Vec3::Y).normalize_or(Vec3::X);
                let up = right.cross(forward);
                let muzzle = self.world.transform_point3(def.muzzle);
                for _ in 0..def.pellets.max(1) {
                    // Strays gather towards the middle of the cone, as real groups do.
                    let radius = spread * self.random().sqrt() * (0.5 + 0.5 * self.random());
                    let angle = self.random() * std::f32::consts::TAU;
                    let direction = (forward
                        + right * (radius * angle.cos())
                        + up * (radius * angle.sin()))
                    .normalize();
                    shots.push(Shot {
                        origin: eye,
                        direction,
                        damage: def.damage,
                        head_multiplier: def.head_multiplier,
                        limb_multiplier: def.limb_multiplier,
                        muzzle,
                        loudness: def.loudness,
                    });
                }
                // Recoil: the muzzle climbs, most of which the firer must pull back down
                // themself, and wanders to the side, more as a burst goes on.
                self.shots_in_burst += 1;
                let steadied = 1.0 - self.aim * 0.3 - player.crouch * 0.2;
                let climb = def.recoil_pitch * steadied * (1.0 + (self.shots_in_burst.min(8) as f32) * 0.035);
                let side = (self.random() * 2.0 - 1.0) * def.recoil_yaw * steadied;
                player.turn(side * 0.6, climb * 0.62);
                let r: [f32; 6] = std::array::from_fn(|_| self.random());
                self.punch.velocity += Vec3::new(side * 9.0, climb * 16.0, (r[0] - 0.5) * 0.35);
                self.kick.velocity +=
                    Vec3::new((r[1] - 0.5) * 0.25, 0.12 + r[2] * 0.1, def.kick * 62.0) * (1.0 - self.aim * 0.35);
                self.twist.velocity += Vec3::new((r[3] - 0.5) * 16.0, 22.0 + r[4] * 8.0, (r[5] - 0.5) * 26.0)
                    * (1.0 - self.aim * 0.55);
                self.bloom = (self.bloom + def.spread_bloom * (1.0 - self.aim * 0.6)).min(0.05);
                self.bolt = 1.0;

                let muzzle_world = self.world * Mat4::from_translation(def.muzzle);
                fx.muzzle_flash(muzzle_world, 1.0);
                let port = self.world.transform_point3(def.eject);
                let gun_right = self.world.transform_vector3(Vec3::X);
                let gun_up = self.world.transform_vector3(Vec3::Y);
                let gun_back = self.world.transform_vector3(Vec3::Z);
                let r: [f32; 3] = std::array::from_fn(|_| self.random());
                let throw = gun_right * (2.4 + r[0] * 1.2)
                    + gun_up * (1.4 + r[1] * 0.9)
                    + gun_back * (0.5 + r[2] * 0.8)
                    + player.velocity;
                fx.casing(physics, port, throw);
                audio.own(def.shot_sound, 1.0);
                fx.shake(0.05);
            }
        }
        self.bloom = (self.bloom - dt * 0.09).max(0.0);
        self.kick.update(dt, 210.0, 24.0);
        self.twist.update(dt, 190.0, 22.0);
        self.punch.update(dt, 120.0, 17.0);
        // The bolt comes forward again unless the magazine is empty.
        if self.guns[self.current].rounds > 0 || self.reloading() {
            let closing = if self.reloading() { 0.0 } else { 26.0 };
            self.bolt = (self.bolt - dt * closing).max(0.0);
        }
        shots
    }

    /// Places the weapon and the arms in the view. `look` is how far the view turned this
    /// frame, to the left and up, in radians, which the weapon trails behind.
    #[allow(clippy::too_many_arguments)]
    pub fn draw(
        &mut self,
        renderer: &mut Renderer,
        rigs: &[Rig],
        player: &Player,
        physics: &Physics,
        camera: Mat4,
        look: (f32, f32),
        dt: f32,
        hidden: bool,
    ) {
        let def = self.gun().def.clone();
        let parts = &mut self.parts[self.current];
        for (group, _) in &mut parts.groups {
            group.set_hidden(renderer, hidden);
        }
        if let Some(arms) = &mut self.arms {
            arms.set_hidden(renderer, hidden);
        }
        if hidden {
            return;
        }

        // Where the weapon sits: between the hip and the sights, lowered in a sprint.
        let mut pose = def.hip.lerp(&def.aimed, ramp(self.aim, 0.0, 1.0));
        pose = pose.lerp(&def.sprint, ramp(self.sprint, 0.0, 1.0) * (1.0 - self.aim));
        let loose = 1.0 - self.aim * 0.85;

        // It trails behind a turning view, and swings back.
        let target = Vec3::new(
            (-look.0 / dt.max(1.0e-4) * 0.011).clamp(-0.06, 0.06),
            (-look.1 / dt.max(1.0e-4) * 0.011).clamp(-0.05, 0.05),
            0.0,
        );
        self.sway += (target - self.sway) * (1.0 - (-dt * 9.0).exp());
        pose.turn.x += self.sway.x.to_degrees() * loose * 0.9;
        pose.turn.y += self.sway.y.to_degrees() * loose * 0.9;
        pose.turn.z += self.sway.x.to_degrees() * loose * 0.8;
        pose.position.x -= self.sway.x * 0.12 * loose;
        pose.position.y -= self.sway.y * 0.1 * loose;

        // It moves with the body: a figure of eight as the feet fall, and with breathing.
        let (stride, bob) = player.stride();
        let bob = bob * loose;
        pose.position.x += stride.sin() * 0.0065 * bob;
        pose.position.y += -(stride * 2.0).cos() * 0.0052 * bob - bob * 0.002;
        pose.turn.z += stride.sin() * 1.1 * bob;
        pose.turn.x += stride.cos() * 0.5 * bob;
        let breath = self.time * 1.25;
        pose.position.y += breath.sin() * 0.0016 * loose + (breath * 0.5).sin() * 0.0008;
        pose.turn.y += (breath + 0.6).sin() * 0.22 * loose;
        pose.turn.x += (breath * 0.5).cos() * 0.14 * loose;
        // Off the ground, it floats up a little; landing, it dips.
        if !player.grounded {
            pose.position.y += 0.008 * loose;
            pose.turn.y += 1.2 * loose;
        }

        // Something close ahead pushes the muzzle up and the weapon back.
        let eye = camera.w_axis.truncate();
        let ahead = camera.transform_vector3(Vec3::NEG_Z);
        let reach = 0.62;
        let clear = physics.sweep_ball(eye + ahead * 0.12, eye + ahead * reach, 0.045);
        let blocked = (1.0 - clear).clamp(0.0, 1.0) * (1.0 - self.aim * 0.5);
        self.blocked += (blocked - self.blocked) * (1.0 - (-dt * 12.0).exp());
        pose.position.z += self.blocked * 0.17;
        pose.position.y -= self.blocked * 0.05;
        pose.turn.y += self.blocked * 34.0;
        pose.turn.x += self.blocked * 10.0;

        // Recoil.
        pose.position += Vec3::new(self.kick.value.x * 0.02, self.kick.value.y * 0.02, self.kick.value.z);
        pose.turn += Vec3::new(self.twist.value.x, self.twist.value.y, self.twist.value.z) * 0.12;

        // Changing weapon: down and away, and back up.
        let away = match self.phase {
            Phase::Lowering(time, _) => ramp(time / SWAP_SECONDS, 0.0, 1.0),
            Phase::Raising(time) => 1.0 - ramp(time / SWAP_SECONDS, 0.0, 1.0),
            _ => 0.0,
        };
        pose.position += Vec3::new(0.03, -0.26, 0.06) * away;
        pose.turn += Vec3::new(18.0, -42.0, 22.0) * away;

        // A reload: the weapon rolls to show its magazine well, the magazine comes out and a
        // fresh one goes in, and from empty the bolt is sent home.
        let mut magazine = Vec3::ZERO;
        let mut hand_on_magazine = 0.0;
        let mut hand_on_catch = 0.0;
        let mut charge = 0.0;
        if let Phase::Reloading(time, empty) = self.phase {
            let length = if empty { def.reload_empty_seconds } else { def.reload_seconds };
            // The magazine change takes the same time either way; from empty, the bolt follows.
            let u = time / def.reload_seconds;
            let tilt = window(u, 0.0, 0.14, 0.76, 0.94);
            pose.position += Vec3::new(-0.03, 0.03, 0.03) * tilt;
            pose.turn += Vec3::new(7.0, 12.0, -27.0) * tilt;
            let seat = window(u, 0.665, 0.69, 0.70, 0.76);
            pose.position.y += seat * 0.012;
            pose.turn.y += seat * 2.5;
            let dropped = window(u, 0.16, 0.27, 0.6, 0.69);
            let gone = window(u, 0.26, 0.38, 0.46, 0.6);
            magazine = Vec3::new(0.0, -0.17, -0.02) * dropped + Vec3::new(-0.1, -0.32, 0.12) * gone;
            hand_on_magazine = window(u, 0.05, 0.15, 0.72, 0.82);
            if empty {
                let v = time / length;
                hand_on_catch = window(v, 0.76, 0.84, 0.88, 0.95);
                let slap = window(v, 0.845, 0.86, 0.87, 0.9);
                pose.position.x += slap * 0.006;
                pose.turn.z -= slap * 3.0;
            }
            let _ = &mut charge;
        }

        let world = camera * pose.matrix();
        self.world = world;
        let parts = &self.parts[self.current];
        for (group, part) in &parts.groups {
            let local = match part {
                Part::Fixed => Mat4::IDENTITY,
                Part::Magazine => Mat4::from_translation(magazine),
                Part::Bolt(travel) => Mat4::from_translation(Vec3::Z * travel * self.bolt),
                Part::Charge(travel) => Mat4::from_translation(Vec3::Z * travel * charge),
            };
            group.move_to(renderer, world * local);
        }

        // The arms: shoulders fixed below the eye, hands wherever the weapon and the reload
        // put them.
        let (Some(arms), Some(rig)) = (&self.arms, self.arms_rig.and_then(|index| rigs.get(index))) else {
            return;
        };
        let shoulder_height = rig.rest_model[rig.human.arms[0].upper].w_axis.y;
        // The arms' mesh faces +Z; the view looks along -Z.
        let arms_in_view = Mat4::from_translation(Vec3::new(0.0, -shoulder_height - 0.215, 0.115))
            * Mat4::from_rotation_y(std::f32::consts::PI);
        let arms_world = camera * arms_in_view;
        arms.move_to(renderer, arms_world);
        let weapon_in_arms = arms_in_view.inverse() * pose.matrix();
        let (_, rotation, origin) = weapon_in_arms.to_scale_rotation_translation();
        let (grip, mut support) = rifle_hands(rotation, origin, &def.hold);
        let on_weapon = |point: Vec3| origin + rotation * point;
        if hand_on_magazine > 0.0 {
            // The hand takes the magazine from below, palm to the right, and goes where it goes.
            let fingers = rotation * Vec3::new(0.25, 0.9, -0.35).normalize();
            let palm = rotation * Vec3::new(0.95, -0.1, 0.25).normalize();
            let wrist = on_weapon(def.magazine_grip + magazine) - fingers * 0.07 - palm * 0.03;
            support.wrist = support.wrist.lerp(wrist, hand_on_magazine);
            support.fingers = support.fingers.lerp(fingers, hand_on_magazine).normalize();
            support.palm = support.palm.lerp(palm, hand_on_magazine).normalize();
            support.curl = support.curl + (0.85 - support.curl) * hand_on_magazine;
        }
        if hand_on_catch > 0.0 {
            // Up to the bolt catch on the left of the receiver, to send the bolt home.
            let fingers = rotation * Vec3::new(0.35, 0.75, -0.55).normalize();
            let palm = rotation * Vec3::new(0.9, -0.3, 0.3).normalize();
            let wrist = on_weapon(Vec3::new(-0.03, 0.0, -0.03)) - fingers * 0.085 - palm * 0.02;
            support.wrist = support.wrist.lerp(wrist, hand_on_catch);
            support.fingers = support.fingers.lerp(fingers, hand_on_catch).normalize();
            support.palm = support.palm.lerp(palm, hand_on_catch).normalize();
            support.curl = support.curl + (0.35 - support.curl) * hand_on_catch;
        }
        let mut posed = Posed::new(&rig.skeleton, rig.rest.clone());
        place_hands(rig, &mut posed, Some(&grip), Some(&support), Vec3::NEG_X, Vec3::Z, 1.0);
        if let Some(pose) = arms.pose {
            renderer.set_pose(pose, &posed.model);
        }
    }

    /// Where the muzzle is in the world, for anything that needs to know after `draw`.
    pub fn muzzle(&self) -> Vec3 {
        self.world.transform_point3(self.gun().def.muzzle)
    }
}
