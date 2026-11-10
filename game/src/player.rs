//! The player's body: walking, sprinting, crouching and jumping through the world, and the eye
//! that goes with it, with the small motions of a head on a moving body.

use crate::input::{Action, Input};
use crate::physics::{Physics, Walker};
use glam::{Vec2, Vec3};

pub const RADIUS: f32 = 0.34;
pub const STAND_HEIGHT: f32 = 1.82;
pub const CROUCH_HEIGHT: f32 = 1.18;
const STAND_EYE: f32 = 1.66;
const CROUCH_EYE: f32 = 1.02;

const WALK_SPEED: f32 = 3.9;
const SPRINT_SPEED: f32 = 6.3;
const CROUCH_SPEED: f32 = 1.9;
/// How much slower the player goes while aiming down the sights.
const AIM_SLOWDOWN: f32 = 0.55;
const GROUND_RESPONSE: f32 = 11.0;
const AIR_RESPONSE: f32 = 1.6;
const JUMP_SPEED: f32 = 4.3;
/// Seconds after walking off an edge in which a jump still counts.
const COYOTE_SECONDS: f32 = 0.12;
const MAX_PITCH: f32 = 1.48;

/// What the player's body did this frame that others want to know about.
#[derive(Clone, Copy, Debug, Default)]
pub struct BodyEvents {
    /// A foot came down: how hard, from 0 to 1.
    pub footstep: Option<f32>,
    pub jumped: bool,
    /// Landed after a fall: the speed of the landing, in metres a second.
    pub landed: Option<f32>,
}

pub struct Player {
    walker: Walker,
    pub feet: Vec3,
    /// Across the ground, metres a second.
    pub velocity: Vec3,
    vertical: f32,
    pub grounded: bool,
    since_grounded: f32,
    /// Radians about Y; zero faces -Z.
    pub yaw: f32,
    pub pitch: f32,
    /// 0 standing, 1 fully crouched.
    pub crouch: f32,
    crouching: bool,
    pub sprinting: bool,
    /// How far through a stride, in radians: a foot comes down at each multiple of pi.
    stride: f32,
    /// How much the head bobs, eased so that it starts and stops gently.
    bob: f32,
    /// The head's dip after a landing: a damped spring.
    dip: f32,
    dip_speed: f32,
    pub health: f32,
    pub alive: bool,
}

impl Player {
    pub fn new(physics: &mut Physics, feet: Vec3, yaw: f32) -> Self {
        let walker = physics.add_walker(feet, RADIUS, STAND_HEIGHT);
        Self {
            walker,
            feet,
            velocity: Vec3::ZERO,
            vertical: 0.0,
            grounded: false,
            since_grounded: 1.0,
            yaw,
            pitch: 0.0,
            crouch: 0.0,
            crouching: false,
            sprinting: false,
            stride: 0.0,
            bob: 0.0,
            dip: 0.0,
            dip_speed: 0.0,
            health: 100.0,
            alive: true,
        }
    }

    pub fn walker(&self) -> Walker {
        self.walker
    }

    /// Puts the player somewhere at once, as at a checkpoint.
    pub fn place(&mut self, physics: &mut Physics, feet: Vec3, yaw: f32) {
        physics.place_walker(self.walker, feet);
        self.feet = feet;
        self.yaw = yaw;
        self.pitch = 0.0;
        self.velocity = Vec3::ZERO;
        self.vertical = 0.0;
    }

    pub fn forward(&self) -> Vec3 {
        let (sy, cy) = self.yaw.sin_cos();
        let (sp, cp) = self.pitch.sin_cos();
        Vec3::new(-sy * cp, sp, -cy * cp)
    }

    pub fn flat_forward(&self) -> Vec3 {
        Vec3::new(-self.yaw.sin(), 0.0, -self.yaw.cos())
    }

    pub fn right(&self) -> Vec3 {
        Vec3::new(self.yaw.cos(), 0.0, -self.yaw.sin())
    }

    /// How fast the player is going across the ground, as a share of walking pace.
    pub fn pace(&self) -> f32 {
        Vec2::new(self.velocity.x, self.velocity.z).length() / WALK_SPEED
    }

    pub fn speed(&self) -> f32 {
        Vec2::new(self.velocity.x, self.velocity.z).length()
    }

    pub fn eye_height(&self) -> f32 {
        STAND_EYE + (CROUCH_EYE - STAND_EYE) * self.crouch
    }

    /// Where the eye is, with the head's bob and dip.
    pub fn eye(&self) -> Vec3 {
        let bob_up = (self.stride * 2.0).sin() * 0.028 * self.bob;
        let bob_side = self.stride.sin() * 0.02 * self.bob;
        self.feet + Vec3::Y * (self.eye_height() + bob_up - self.dip) + self.right() * bob_side
    }

    /// Where the middle of the chest is: what others aim at.
    pub fn chest(&self) -> Vec3 {
        self.feet + Vec3::Y * (self.eye_height() * 0.74)
    }

    /// The bob's phase and strength, for the weapon to move with the body.
    pub fn stride(&self) -> (f32, f32) {
        (self.stride, self.bob)
    }

    /// Turns the view by this much, in radians: to the left, and up.
    pub fn turn(&mut self, left: f32, up: f32) {
        self.yaw = (self.yaw + left).rem_euclid(std::f32::consts::TAU);
        self.pitch = (self.pitch + up).clamp(-MAX_PITCH, MAX_PITCH);
    }

    /// Moves the body through a frame of `dt` seconds. `aiming` slows it; `frozen` holds it
    /// still, as in a menu or a scripted moment.
    pub fn update(
        &mut self,
        physics: &mut Physics,
        input: &Input,
        dt: f32,
        aiming: bool,
        frozen: bool,
    ) -> BodyEvents {
        let mut events = BodyEvents::default();
        if !self.alive {
            // The body drops where it stood.
            self.crouch = (self.crouch + dt * 2.5).min(1.0);
            let walked = physics.walk(self.walker, Vec3::ZERO, self.vertical, dt);
            self.feet = walked.feet;
            self.vertical = walked.vertical;
            self.velocity = Vec3::ZERO;
            return events;
        }
        let (push_right, push_forward) = if frozen { (0.0, 0.0) } else { input.movement() };
        let wish = (self.flat_forward() * push_forward + self.right() * push_right)
            .clamp_length_max(1.0);

        // Crouching: held, and kept if there is no room to stand.
        let wants_crouch = !frozen && input.held(Action::Crouch);
        if wants_crouch && !self.crouching {
            self.crouching = true;
            physics.set_walker_height(self.walker, RADIUS, CROUCH_HEIGHT);
        } else if !wants_crouch
            && self.crouching
            && physics.walker_fits(self.walker, RADIUS, STAND_HEIGHT)
        {
            self.crouching = false;
            physics.set_walker_height(self.walker, RADIUS, STAND_HEIGHT);
        }
        let crouch_target = if self.crouching { 1.0 } else { 0.0 };
        self.crouch += (crouch_target - self.crouch) * (1.0 - (-dt * 12.0).exp());

        // Sprinting: forwards only, on the ground, standing, not aiming.
        self.sprinting = !frozen
            && input.held(Action::Sprint)
            && push_forward > 0.5
            && !self.crouching
            && !aiming
            && self.grounded;
        let mut top_speed = if self.crouching {
            CROUCH_SPEED
        } else if self.sprinting {
            SPRINT_SPEED
        } else {
            WALK_SPEED
        };
        if aiming {
            top_speed *= AIM_SLOWDOWN;
        }
        // Backing up and sidestepping are slower than going forwards.
        if push_forward < -0.1 {
            top_speed *= 0.8;
        }

        let response = if self.grounded {
            GROUND_RESPONSE
        } else {
            AIR_RESPONSE
        };
        let wanted = wish * top_speed;
        self.velocity += (wanted - self.velocity) * (1.0 - (-dt * response).exp());

        self.since_grounded = if self.grounded {
            0.0
        } else {
            self.since_grounded + dt
        };
        if !frozen
            && input.pressed(Action::Jump)
            && self.since_grounded < COYOTE_SECONDS
            && self.vertical <= 0.01
            && !self.crouching
        {
            self.vertical = JUMP_SPEED;
            self.grounded = false;
            self.since_grounded = COYOTE_SECONDS;
            events.jumped = true;
        }

        let was_grounded = self.grounded;
        let falling_speed = -self.vertical;
        let before = self.feet;
        let walked = physics.walk(self.walker, self.velocity, self.vertical, dt);
        self.feet = walked.feet;
        self.vertical = walked.vertical;
        self.grounded = walked.grounded;
        // What the world allowed is the real velocity: a wall takes away what ran into it.
        if dt > 1.0e-5 {
            let actual = (self.feet - before) / dt;
            let allowed = Vec3::new(actual.x, 0.0, actual.z);
            if allowed.length() < self.velocity.length() * 0.7 {
                self.velocity = self.velocity.lerp(allowed, 0.5);
            }
        }

        if self.grounded && !was_grounded && falling_speed > 2.0 {
            events.landed = Some(falling_speed);
            self.dip_speed += (falling_speed * 0.085).min(0.7);
        }
        // The landing dip springs back.
        let (stiffness, damping) = (160.0, 20.0);
        self.dip_speed += (-stiffness * self.dip - damping * self.dip_speed) * dt;
        self.dip += self.dip_speed * dt;

        // Strides: a step's length grows with speed, as a real walk's does.
        let speed = self.speed();
        let moving = self.grounded && speed > 0.6;
        let bob_target = if moving {
            (speed / WALK_SPEED).min(1.6)
        } else {
            0.0
        };
        self.bob += (bob_target - self.bob) * (1.0 - (-dt * 9.0).exp());
        if moving {
            let step_length = 0.62 + 0.11 * speed;
            let before = self.stride;
            self.stride += speed / step_length * std::f32::consts::PI * dt;
            if (before / std::f32::consts::PI).floor() != (self.stride / std::f32::consts::PI).floor()
            {
                let weight = if self.sprinting {
                    1.0
                } else if self.crouching {
                    0.35
                } else {
                    0.65
                };
                events.footstep = Some(weight);
            }
            if self.stride > std::f32::consts::TAU * 64.0 {
                self.stride -= std::f32::consts::TAU * 64.0;
            }
        }
        events
    }

    /// Takes damage. Returns whether this killed the player.
    pub fn hurt(&mut self, amount: f32) -> bool {
        if !self.alive {
            return false;
        }
        self.health = (self.health - amount).max(0.0);
        if self.health <= 0.0 {
            self.alive = false;
            return true;
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn world() -> Physics {
        let mut physics = Physics::new();
        physics.add_blocker(Vec3::new(0.0, -0.5, 0.0), Vec3::new(200.0, 1.0, 200.0), 0.0);
        physics.step(1.0 / 60.0);
        physics
    }

    fn run(player: &mut Player, physics: &mut Physics, input: &mut Input, frames: u32) -> u32 {
        let mut steps = 0;
        for _ in 0..frames {
            let events = player.update(physics, input, 1.0 / 60.0, false, false);
            steps += u32::from(events.footstep.is_some());
            input.end_frame();
            physics.step(1.0 / 60.0);
        }
        steps
    }

    #[test]
    fn walking_reaches_walking_pace_and_sprinting_is_faster() {
        let mut physics = world();
        let mut player = Player::new(&mut physics, Vec3::new(0.0, 0.1, 0.0), 0.0);
        let mut input = Input::new();
        run(&mut player, &mut physics, &mut input, 30);
        assert!(player.grounded);
        input.key("KeyW", true);
        let steps = run(&mut player, &mut physics, &mut input, 120);
        assert!((player.speed() - WALK_SPEED).abs() < 0.2, "{}", player.speed());
        assert!(player.feet.z < -5.0, "walked forwards, -Z: {}", player.feet);
        assert!((3..=9).contains(&steps), "{steps} footsteps in two seconds");
        input.key("ShiftLeft", true);
        run(&mut player, &mut physics, &mut input, 120);
        assert!(player.speed() > WALK_SPEED + 1.5, "{}", player.speed());
    }

    #[test]
    fn a_jump_leaves_the_ground_and_comes_back() {
        let mut physics = world();
        let mut player = Player::new(&mut physics, Vec3::new(0.0, 0.1, 0.0), 0.0);
        let mut input = Input::new();
        run(&mut player, &mut physics, &mut input, 30);
        input.key("Space", true);
        let mut highest = 0.0f32;
        for _ in 0..90 {
            player.update(&mut physics, &input, 1.0 / 60.0, false, false);
            input.end_frame();
            physics.step(1.0 / 60.0);
            highest = highest.max(player.feet.y);
        }
        assert!(highest > 0.6 && highest < 1.3, "jumped {highest} m");
        assert!(player.grounded && player.feet.y < 0.05);
    }

    #[test]
    fn crouching_lowers_the_eye_and_slows_the_walk() {
        let mut physics = world();
        let mut player = Player::new(&mut physics, Vec3::new(0.0, 0.1, 0.0), 0.0);
        let mut input = Input::new();
        run(&mut player, &mut physics, &mut input, 30);
        let standing = player.eye().y;
        input.key("KeyC", true);
        input.key("KeyW", true);
        run(&mut player, &mut physics, &mut input, 90);
        assert!(player.eye().y < standing - 0.5);
        assert!(player.speed() < CROUCH_SPEED + 0.2);
        assert!(player.feet.y.abs() < 0.05, "feet stay down: {}", player.feet.y);
    }
}
