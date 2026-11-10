//! The people of the level who aren't the player: their bodies, how they are drawn, and what
//! can hit them. What they decide to do is in `ai`.

use crate::actors::Group;
use crate::ai::{Brain, Mode, Team};
use crate::anim::{pose_soldier, Animator, Figure, RifleHold, Rig, Stance};
use crate::physics::{Physics, Walker};
use glam::{Mat4, Quat, Vec3};
use solstice_render::Renderer;

/// A capsule of a body that a bullet can hit, in the world.
#[derive(Clone, Copy, Debug)]
pub struct HitShape {
    pub a: Vec3,
    pub b: Vec3,
    pub radius: f32,
    pub zone: Zone,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Zone {
    Head,
    Torso,
    Limb,
}

/// One person: a body in the world, animated.
pub struct Npc {
    pub body: Group,
    pub weapon: Option<Group>,
    pub rig: usize,
    pub animator: Animator,
    /// Where the feet are.
    pub position: Vec3,
    /// The way the body faces, in radians about Y; zero faces -Z, as the camera's yaw does.
    pub yaw: f32,
    pub stance: Stance,
    pub speed: f32,
    pub crouched: bool,
    pub alive: bool,
    pub health: f32,
    /// Seconds since it died, for clearing the dead away.
    pub dead_for: f32,
    /// In play: drawn, thinking, and able to be shot. One that isn't waits hidden to be used.
    pub active: bool,
    pub brain: Brain,
    pub walker: Option<Walker>,
    pub velocity: Vec3,
    pub vertical: f32,
    /// Which kind of person it is: its kit's name in the level.
    pub kind: String,
    /// The last figure posed, in the mesh's space, for hit shapes and the muzzle.
    figure: Option<Figure>,
    /// Frames since the pose was last worked out: faraway people are posed less often.
    waited: u32,
    /// A dead person's weapon, falling from where it was held to where it lies: the two
    /// places, and how far between them it has got.
    dropped: Option<(Mat4, Mat4, f32)>,
    /// Whether what its weapon held has been taken from it.
    pub looted: bool,
    /// Seconds since it was last hurt: the cell's own get their breath back.
    since_hurt: f32,
}

impl Npc {
    pub fn new(body: Group, weapon: Option<Group>, rig_index: usize, rig: &Rig, kind: &str) -> Self {
        Self {
            active: false,
            brain: Brain::new(Team::Directorate, Vec3::ZERO, 0.0, 1),
            walker: None,
            velocity: Vec3::ZERO,
            vertical: 0.0,
            kind: kind.to_owned(),
            body,
            weapon,
            rig: rig_index,
            animator: Animator::new(rig),
            position: Vec3::ZERO,
            yaw: 0.0,
            stance: Stance::default(),
            speed: 0.0,
            crouched: false,
            alive: true,
            health: 100.0,
            dead_for: 0.0,
            figure: None,
            waited: u32::MAX,
            dropped: None,
            looted: false,
            since_hurt: 0.0,
        }
    }

    /// Puts it into play at a place: alive, whole, and on one side or the other. `thinking`
    /// gives it a mind; without, it stands as a mannequin does.
    #[allow(clippy::too_many_arguments)]
    pub fn enter(
        &mut self,
        renderer: &mut Renderer,
        physics: &mut Physics,
        rig: &Rig,
        position: Vec3,
        yaw: f32,
        team: Team,
        thinking: bool,
        seed: u32,
    ) {
        self.position = position;
        self.yaw = yaw;
        self.alive = true;
        self.active = true;
        self.health = if team == Team::Resistance { 260.0 } else { 100.0 };
        self.dead_for = 0.0;
        self.speed = 0.0;
        self.velocity = Vec3::ZERO;
        self.vertical = 0.0;
        self.crouched = false;
        self.stance = Stance::default();
        self.animator = Animator::new(rig);
        self.figure = None;
        self.waited = u32::MAX;
        self.dropped = None;
        self.looted = false;
        self.brain = Brain::new(team, position, yaw, seed);
        if !thinking {
            self.brain.mode = Mode::Still;
        }
        match self.walker {
            Some(walker) => {
                physics.set_walker_enabled(walker, true);
                physics.place_walker(walker, position);
            }
            None => self.walker = Some(physics.add_walker(position, 0.32, 1.8)),
        }
        self.body.set_hidden(renderer, false);
        self.body.place(renderer, self.world());
        if let Some(weapon) = &mut self.weapon {
            weapon.set_hidden(renderer, false);
        }
    }

    /// Takes it out of play, to wait hidden until it is wanted again.
    pub fn leave(&mut self, renderer: &mut Renderer, physics: &mut Physics) {
        self.active = false;
        self.body.set_hidden(renderer, true);
        if let Some(weapon) = &mut self.weapon {
            weapon.set_hidden(renderer, true);
        }
        if let Some(walker) = self.walker {
            physics.set_walker_enabled(walker, false);
        }
    }

    /// The body's place in the world. Its mesh faces +Z, and the body faces -Z at no turn.
    pub fn world(&self) -> Mat4 {
        Mat4::from_rotation_translation(
            Quat::from_rotation_y(self.yaw + std::f32::consts::PI),
            self.position,
        )
    }

    pub fn forward(&self) -> Vec3 {
        Vec3::new(-self.yaw.sin(), 0.0, -self.yaw.cos())
    }

    /// Moves the animation on and draws the body where it is. `viewer` is where it is seen
    /// from, which decides how often a far body is posed afresh.
    pub fn draw(&mut self, renderer: &mut Renderer, rig: &Rig, hold: &RifleHold, dt: f32, viewer: Vec3) {
        self.since_hurt += dt;
        if self.alive && self.brain.team == Team::Resistance && self.since_hurt > 6.0 {
            self.health = (self.health + 14.0 * dt).min(100.0);
        }
        self.animator.advance(rig, dt, self.speed, self.crouched);
        let world = self.world();
        self.body.move_to(renderer, world);
        let interval = solstice_anim::update_interval(self.position.distance(viewer));
        self.waited = self.waited.saturating_add(1);
        if self.waited >= interval || self.figure.is_none() {
            self.waited = 0;
            let base = self.animator.evaluate(rig);
            let figure = pose_soldier(rig, base, &self.stance, hold);
            if let Some(pose) = self.body.pose {
                renderer.set_pose(pose, &figure.bones);
            }
            self.figure = Some(figure);
        }
        if let (Some(weapon), Some(figure)) = (&self.weapon, &self.figure) {
            if self.alive {
                self.dropped = None;
                weapon.move_to(renderer, world * figure.weapon);
            } else {
                // It falls from dead hands, and comes to rest on its side beside the body.
                let held = world * figure.weapon;
                let (from, to, fallen) = self.dropped.get_or_insert_with(|| {
                    let (_, turn, at) = held.to_scale_rotation_translation();
                    let heading = turn.to_euler(glam::EulerRot::YXZ).0;
                    let side = Quat::from_rotation_y(self.yaw) * Vec3::new(0.35, 0.0, -0.45);
                    let lying = Quat::from_rotation_y(heading + 0.5) * Quat::from_rotation_z(1.48);
                    let rest = Vec3::new(at.x + side.x, self.position.y + 0.035, at.z + side.z);
                    (held, Mat4::from_rotation_translation(lying, rest), 0.0)
                });
                *fallen = (*fallen + dt / 0.55).min(1.0);
                // Gravity's curve down, the turn spread evenly over the fall.
                let (_, from_turn, from_at) = from.to_scale_rotation_translation();
                let (_, to_turn, to_at) = to.to_scale_rotation_translation();
                let drop = *fallen * *fallen;
                let at = Vec3::new(
                    from_at.x + (to_at.x - from_at.x) * *fallen,
                    from_at.y + (to_at.y - from_at.y) * drop,
                    from_at.z + (to_at.z - from_at.z) * *fallen,
                );
                weapon.move_to(renderer, Mat4::from_rotation_translation(from_turn.slerp(to_turn, *fallen), at));
            }
        }
    }

    /// Where a dead person's weapon lies, once it has come to rest.
    pub fn fallen_weapon(&self) -> Option<Vec3> {
        match self.dropped {
            Some((_, to, fallen)) if !self.alive && fallen >= 1.0 => Some(to.w_axis.truncate()),
            _ => None,
        }
    }

    /// Takes a hit of `amount`, from a bullet going `direction`. Returns whether it killed.
    pub fn hurt(&mut self, amount: f32, direction: Vec3, zone: Zone, rig: &Rig) -> bool {
        if !self.alive {
            return false;
        }
        self.health -= amount;
        self.since_hurt = 0.0;
        if self.health > 0.0 {
            // A flinch over whatever it was doing, the legs carrying on.
            let clip = if zone == Zone::Head { "hit_head" } else { "hit_chest" };
            if rig.has_clip(clip) && !self.animator.busy() {
                self.animator.play_upper(clip, 0.06, 0.25, 1.4);
            }
            return false;
        }
        self.alive = false;
        self.speed = 0.0;
        self.stance.armed = 0.0;
        // Shot from the front, it goes over backwards; from behind, forwards.
        let from_front = direction.dot(self.forward()) < 0.0;
        if from_front && rig.has_clip("lay_to_idle") && zone != Zone::Limb {
            self.animator.play_reversed("lay_to_idle", 0.12, 1.5, true);
        } else if rig.has_clip("death") {
            self.animator.play("death", 0.1, 0.0, 1.15, true);
        }
        true
    }

    /// Where the muzzle is, and the way it points, in the world.
    pub fn muzzle(&self) -> (Vec3, Vec3) {
        let world = self.world();
        match &self.figure {
            Some(figure) => (
                world.transform_point3(figure.muzzle),
                world.transform_vector3(figure.muzzle_direction).normalize_or(self.forward()),
            ),
            None => (self.position + Vec3::Y * 1.4, self.forward()),
        }
    }

    pub fn head(&self) -> Vec3 {
        match &self.figure {
            Some(figure) => self.world().transform_point3(figure.head),
            None => self.position + Vec3::Y * 1.65,
        }
    }

    pub fn chest(&self) -> Vec3 {
        match &self.figure {
            Some(figure) => self.world().transform_point3(figure.chest),
            None => self.position + Vec3::Y * 1.25,
        }
    }

    /// The shapes of the body as it is posed, for bullets.
    pub fn hit_shapes(&self, rig: &Rig) -> Vec<HitShape> {
        let Some(figure) = &self.figure else {
            return Vec::new();
        };
        let world = self.world();
        let at = |bone: usize| world.transform_point3(figure.bones[bone].w_axis.truncate());
        let human = &rig.human;
        let head = at(human.head);
        let neck = at(human.neck);
        let crown = head + (head - neck).normalize_or(Vec3::Y) * 0.1;
        let mut shapes = vec![
            HitShape {
                a: head + (crown - head) * 0.3,
                b: crown,
                radius: 0.105,
                zone: Zone::Head,
            },
            HitShape {
                a: at(human.pelvis),
                b: at(human.spine[1]),
                radius: 0.17,
                zone: Zone::Torso,
            },
            HitShape {
                a: at(human.spine[1]),
                b: neck,
                radius: 0.185,
                zone: Zone::Torso,
            },
        ];
        for arm in &human.arms {
            shapes.push(HitShape {
                a: at(arm.upper),
                b: at(arm.lower),
                radius: 0.06,
                zone: Zone::Limb,
            });
            shapes.push(HitShape {
                a: at(arm.lower),
                b: at(arm.hand),
                radius: 0.05,
                zone: Zone::Limb,
            });
        }
        for leg in &human.legs {
            shapes.push(HitShape {
                a: at(leg.thigh),
                b: at(leg.calf),
                radius: 0.09,
                zone: Zone::Limb,
            });
            shapes.push(HitShape {
                a: at(leg.calf),
                b: at(leg.foot),
                radius: 0.065,
                zone: Zone::Limb,
            });
        }
        shapes
    }
}

/// Where along a ray it first comes within `radius` of the segment from `a` to `b`, if it does
/// within `reach`.
pub fn ray_capsule(origin: Vec3, direction: Vec3, reach: f32, shape: &HitShape) -> Option<f32> {
    let axis = shape.b - shape.a;
    let from = origin - shape.a;
    let axis_squared = axis.length_squared();
    let along = axis.dot(direction);
    let side = axis.dot(from);
    let across = direction.dot(from);
    let depth = from.length_squared() - shape.radius * shape.radius;
    // The side of the capsule: a cylinder about its axis.
    let a = axis_squared - along * along;
    let b = axis_squared * across - side * along;
    let c = axis_squared * depth - side * side;
    let mut best: Option<f32> = None;
    let mut consider = |t: f32| {
        if t >= 0.0 && t <= reach && best.is_none_or(|b| t < b) {
            best = Some(t);
        }
    };
    if a.abs() > 1.0e-8 {
        let discriminant = b * b - a * c;
        if discriminant >= 0.0 {
            let t = (-b - discriminant.sqrt()) / a;
            let y = side + t * along;
            if y > 0.0 && y < axis_squared {
                consider(t);
            }
        }
    }
    // Its rounded ends.
    for centre in [shape.a, shape.b] {
        let offset = origin - centre;
        let half_b = offset.dot(direction);
        let c = offset.length_squared() - shape.radius * shape.radius;
        let discriminant = half_b * half_b - c;
        if discriminant >= 0.0 {
            let root = discriminant.sqrt();
            let t = -half_b - root;
            // A ray starting inside a ball hits it at once.
            consider(if t < 0.0 && -half_b + root >= 0.0 { 0.0 } else { t });
        }
    }
    best
}

#[cfg(test)]
mod tests {
    use super::*;

    fn upright() -> HitShape {
        HitShape {
            a: Vec3::new(0.0, 0.0, -5.0),
            b: Vec3::new(0.0, 1.0, -5.0),
            radius: 0.2,
            zone: Zone::Torso,
        }
    }

    #[test]
    fn a_ray_hits_a_capsules_side_and_its_ends() {
        let shape = upright();
        let side = ray_capsule(Vec3::new(0.0, 0.5, 0.0), Vec3::NEG_Z, 100.0, &shape).unwrap();
        assert!((side - 4.8).abs() < 1.0e-3, "{side}");
        let top = ray_capsule(Vec3::new(0.0, 1.15, 0.0), Vec3::NEG_Z, 100.0, &shape).unwrap();
        assert!(top > 4.8 && top < 5.0, "the rounded top: {top}");
        assert!(ray_capsule(Vec3::new(0.0, 1.3, 0.0), Vec3::NEG_Z, 100.0, &shape).is_none());
        assert!(ray_capsule(Vec3::new(0.3, 0.5, 0.0), Vec3::NEG_Z, 100.0, &shape).is_none());
    }

    #[test]
    fn a_ray_stops_at_its_reach_and_does_not_look_behind() {
        let shape = upright();
        assert!(ray_capsule(Vec3::new(0.0, 0.5, 0.0), Vec3::NEG_Z, 3.0, &shape).is_none());
        assert!(ray_capsule(Vec3::new(0.0, 0.5, 0.0), Vec3::Z, 100.0, &shape).is_none());
    }
}
