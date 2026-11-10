//! What a fight looks like: muzzle flashes and their light, tracers, the dust and sparks a
//! bullet knocks out of what it hits, the holes it leaves, spent cases, explosions, and the
//! shake they give the view.
//!
//! The renderer's particle system has room for a fixed number of emitters, and a scene's
//! instances and lights are fixed when it is baked. So nothing here is made as it is needed:
//! each kind of effect keeps a few emitters running all the time and tells one to puff when
//! something happens, and tracers, holes and cases are drawn from pools of hidden instances.

use crate::actors::Group;
use crate::level::{Level, Surface};
use crate::physics::{Physics, WORLD};
use glam::{Mat4, Quat, Vec3};
use solstice_asset::Light;
use solstice_render::{Effect, EffectId, Renderer};

const MUZZLE: &str = "
param flash 0
param smoke 0
emitter flash
  budget 96
  spawn rate=5*flash
  shape sphere 0.008
  lifetime 0.018 0.04
  velocity 0 0 -13 cone=26 spread=0.7
  size 0.012 0.034
  temperature 2700 3200
  glow 0.55
  color 1 0.82 0.55 1
  color life 0=1 1 1 1 0.6=1 1 1 0.8 1=1 1 1 0
  size life 0=0.5 1=1.7
  render sprite blend=add soft=0.04 shading=unlit
emitter smoke
  budget 320
  spawn rate=6*smoke
  shape sphere 0.02
  lifetime 0.7 1.6
  velocity 0 0 -2.4 cone=28 spread=0.7
  size 0.05 0.11
  drag 3.5
  gravity -0.3
  wind 0.5
  curl 0.5 scale=1.6 change=0.4
  color 0.62 0.62 0.64 0.11
  color life 0=1 1 1 0 0.1=1 1 1 1 1=1 1 1 0
  size life 0=0.5 1=3.4
  render sprite sort soft=0.2
";

const IMPACT: &str = "
param dust 0
param chips 0
param sparks 0
param r 0.4
param g 0.38
param b 0.35
emitter puff
  budget 360
  spawn rate=11*dust
  shape sphere 0.03
  lifetime 0.6 1.6
  velocity 0 1.9 0 cone=40 spread=0.75
  size 0.06 0.15
  drag 3.2
  gravity 0.35
  wind 0.5
  curl 0.4 scale=2 change=0.3
  color r g b 0.3
  color life 0=1 1 1 0 0.07=1 1 1 1 1=1 1 1 0
  size life 0=0.35 1=3.6
  render sprite sort soft=0.15
emitter chips
  budget 320
  spawn rate=10*chips
  shape sphere 0.02
  lifetime 0.6 1.3
  velocity 0 3.6 0 cone=58 spread=0.65
  size 0.004 0.012
  gravity
  drag 0.5
  color r g b 1
  collide depth bounce restitution=0.3 friction=0.5
  render sprite solid
emitter sparks
  budget 240
  spawn rate=16*sparks
  shape point
  lifetime 0.12 0.45
  velocity 0 8 0 cone=52 spread=0.75
  size 0.003 0.007
  gravity
  drag 1.0
  temperature 2100 2800
  cooling 2.5
  glow 2.5
  collide depth bounce restitution=0.45 friction=0.2
  render sprite blend=add shading=unlit
";

const BLOOD: &str = "
param go 0
emitter mist
  budget 200
  spawn rate=9*go
  shape sphere 0.03
  lifetime 0.35 0.8
  velocity 0 1.6 0 cone=45 spread=0.8
  size 0.04 0.09
  drag 4
  gravity 1.5
  color 0.33 0.02 0.02 0.42
  color life 0=1 1 1 0 0.1=1 1 1 1 1=1 1 1 0
  size life 0=0.4 1=2.6
  render sprite sort soft=0.1
emitter drops
  budget 200
  spawn rate=12*go
  shape sphere 0.02
  lifetime 0.4 0.9
  velocity 0 2.8 0 cone=50 spread=0.7
  size 0.004 0.01
  gravity
  drag 0.4
  color 0.28 0.012 0.012 1
  collide depth kill
  render sprite solid
";

const EXPLOSION: &str = "
param go 0
emitter fire
  budget 320
  spawn rate=42*go
  shape sphere 0.35
  lifetime 0.25 0.6
  velocity 0 3.5 0 cone=85 spread=0.8
  size 0.35 0.85
  drag 2.5
  temperature 2300 3000
  cooling 1.6
  glow 1.8
  buoyancy 1.5
  color 1 0.6 0.25 1
  color life 0=1 1 1 1 0.5=1 1 1 0.7 1=1 1 1 0
  size life 0=0.5 1=2.2
  render sprite blend=add soft=0.3 shading=unlit
emitter smoke
  budget 640
  spawn rate=46*go
  shape sphere 0.6
  lifetime 2.5 5.5
  velocity 0 3.2 0 cone=75 spread=0.8
  size 0.5 1.2
  drag 1.8
  gravity -0.5
  wind 1
  curl 1.2 scale=4 change=0.3
  color 0.09 0.085 0.08 0.55
  color life 0=1 1 1 0 0.06=1 1 1 1 0.5=1 1 1 0.7 1=1 1 1 0
  size life 0=0.4 1=3.2
  render sprite sort soft=0.5
emitter sparks
  budget 400
  spawn rate=70*go
  shape sphere 0.2
  lifetime 0.4 1.3
  velocity 0 11 0 cone=80 spread=0.8
  size 0.006 0.014
  gravity
  drag 0.6
  temperature 2200 2900
  cooling 1.2
  glow 2.5
  collide depth bounce restitution=0.4 friction=0.3
  render sprite blend=add shading=unlit
emitter debris
  budget 400
  spawn rate=60*go
  shape sphere 0.3
  lifetime 0.9 2.2
  velocity 0 9 0 cone=70 spread=0.75
  size 0.012 0.045
  gravity
  drag 0.3
  color 0.1 0.09 0.08 1
  collide depth bounce restitution=0.25 friction=0.6
  render sprite solid
emitter dust
  budget 400
  spawn rate=36*go
  shape sphere 0.8
  lifetime 1.5 3.5
  velocity 0 0.8 0 cone=88 spread=0.9
  size 0.5 1.1
  drag 2.2
  wind 0.8
  curl 0.6 scale=5 change=0.2
  color 0.36 0.32 0.27 0.26
  color life 0=1 1 1 0 0.1=1 1 1 1 1=1 1 1 0
  size life 0=0.5 1=2.8
  render sprite sort soft=0.6
";

/// A column of smoke from something burning: placed once, and left to burn.
const SMOULDER: &str = "
param heat 1
emitter smoke
  budget 700
  spawn rate=7*heat
  shape sphere 0.5
  lifetime 9 14
  velocity 0 2.2 0 cone=14 spread=0.4
  size 0.9 1.6
  drag 0.5
  gravity -0.45
  wind 1
  curl 0.9 scale=7 change=0.12
  color 0.06 0.058 0.055 0.5
  color life 0=1 1 1 0 0.06=1 1 1 1 0.6=1 1 1 0.55 1=1 1 1 0
  size life 0=0.5 1=5
  render sprite sort soft=1
emitter embers
  budget 160
  spawn rate=6*heat
  shape sphere 0.6
  lifetime 1.2 3
  velocity 0 1.8 0 cone=30 spread=0.6
  size 0.005 0.012
  drag 1.5
  wind 1
  curl 1.5 scale=2 change=0.5
  buoyancy 2
  temperature 1500 1900
  cooling 0.6
  glow 2
  render sprite blend=add shading=unlit
";

/// An open fire: in a drum, or what is left burning of a wreck.
const FIRE: &str = "
param heat 1
emitter flames
  budget 300
  spawn rate=85*heat
  shape sphere 0.13
  lifetime 0.22 0.5
  velocity 0 1.5 0 cone=14 spread=0.5
  size 0.07 0.15
  drag 1.6
  temperature 1250 1650
  cooling 1.1
  glow 0.28
  buoyancy 1.6
  curl 1.6 scale=3 change=1.2
  color 1 0.5 0.16 1
  color life 0=1 1 1 0 0.15=1 1 1 0.9 0.7=1 1 1 0.5 1=1 1 1 0
  size life 0=1 1=0.35
  render sprite blend=add soft=0.3 shading=unlit
emitter smoke
  budget 220
  spawn rate=5*heat
  shape sphere 0.2
  lifetime 5 8
  velocity 0 1.6 0 cone=12 spread=0.4
  size 0.3 0.6
  drag 0.5
  gravity -0.4
  wind 1
  curl 0.8 scale=5 change=0.15
  color 0.05 0.048 0.045 0.4
  color life 0=1 1 1 0 0.1=1 1 1 0.8 0.6=1 1 1 0.4 1=1 1 1 0
  size life 0=0.5 1=4
  render sprite sort soft=1
emitter embers
  budget 90
  spawn rate=4*heat
  shape sphere 0.2
  lifetime 1.2 2.6
  velocity 0 2.0 0 cone=28 spread=0.6
  size 0.003 0.006
  drag 1.5
  wind 1
  curl 1.5 scale=2 change=0.5
  buoyancy 2
  temperature 1500 1900
  cooling 0.6
  glow 2
  render sprite blend=add shading=unlit
";

/// Smoke standing over something burning a long way off: a column on the skyline.
const PLUME: &str = "
param heat 1
emitter smoke
  budget 420
  spawn rate=2.2*heat
  shape sphere 5
  lifetime 45 70
  velocity 0 3.4 0 cone=8 spread=0.3
  size 9 15
  drag 0.05
  gravity -0.02
  wind 1
  curl 0.5 scale=60 change=0.03
  color 0.035 0.034 0.034 0.75
  color life 0=1 1 1 0 0.05=1 1 1 1 0.5=1 1 1 0.8 1=1 1 1 0
  size life 0=0.4 1=5
  render sprite sort soft=1
";

/// A handful of one effect, kept running, each puffing when told to.
struct Channel {
    ids: Vec<EffectId>,
    /// Which of them puffed last frame, and must be told to stop.
    fired: Vec<bool>,
    next: usize,
    /// The parameters that make it puff, which go back to zero the frame after.
    triggers: Vec<&'static str>,
    waiting: Vec<(Mat4, Vec<(&'static str, f32)>)>,
}

impl Channel {
    fn new(renderer: &mut Renderer, text: &str, count: usize, triggers: &[&'static str]) -> Self {
        let effect = Effect::parse(text).unwrap_or_else(|error| panic!("a built-in effect is wrong: {error}"));
        let far_below = Mat4::from_translation(Vec3::new(0.0, -500.0, 0.0));
        let ids: Vec<EffectId> = (0..count)
            .filter_map(|_| renderer.particles().spawn(&effect, far_below))
            .collect();
        Self {
            fired: vec![false; ids.len()],
            ids,
            next: 0,
            triggers: triggers.to_vec(),
            waiting: Vec::new(),
        }
    }

    fn puff(&mut self, transform: Mat4, params: Vec<(&'static str, f32)>) {
        // More in a frame than there are emitters: the rest are dropped.
        if self.waiting.len() < self.ids.len() {
            self.waiting.push((transform, params));
        }
    }

    fn flush(&mut self, renderer: &mut Renderer, dt: f32) {
        let particles = renderer.particles();
        for (index, fired) in self.fired.iter_mut().enumerate() {
            if std::mem::take(fired) {
                for trigger in &self.triggers {
                    particles.set(self.ids[index], trigger, 0.0);
                }
            }
        }
        if self.ids.is_empty() {
            self.waiting.clear();
            return;
        }
        // A trigger is a rate, so that one frame of it makes the same number of particles
        // however long the frame is.
        let per_frame = 1.0 / dt.max(1.0e-4);
        for (transform, params) in self.waiting.drain(..) {
            let index = self.next % self.ids.len();
            self.next += 1;
            let id = self.ids[index];
            particles.set_transform(id, transform);
            for (name, value) in params {
                let value = if self.triggers.contains(&name) {
                    value * per_frame
                } else {
                    value
                };
                particles.set(id, name, value);
            }
            self.fired[index] = true;
        }
    }
}

struct Tracer {
    group: usize,
    from: Vec3,
    direction: Vec3,
    /// How far its head has flown, and how far it has to go.
    travelled: f32,
    length: f32,
}

struct Casing {
    group: usize,
    position: Vec3,
    velocity: Vec3,
    rotation: Quat,
    spin: Vec3,
    floor: f32,
    age: f32,
    bounces: u32,
}

/// A light that flares and dies: a muzzle flash, an explosion.
struct Flare {
    slot: u32,
    position: Vec3,
    colour: Vec3,
    range: f32,
    /// Seconds it lasts, and how long it has.
    life: f32,
    age: f32,
}

/// A bullet hole, or a scorch.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Decal {
    Hole,
    Scorch,
}

pub struct Fx {
    muzzle: Channel,
    impact: Channel,
    blood: Channel,
    explosion: Channel,
    smoulder: Option<Effect>,
    fire: Option<Effect>,
    plume: Option<Effect>,
    tracer_pool: Vec<Group>,
    tracers: Vec<Tracer>,
    next_tracer: usize,
    holes: Vec<Group>,
    next_hole: usize,
    scorches: Vec<Group>,
    next_scorch: usize,
    casing_pool: Vec<Group>,
    casings: Vec<Casing>,
    next_casing: usize,
    light_slots: Vec<u32>,
    flares: Vec<Flare>,
    next_light: usize,
    /// How shaken the view is, 0 to 1, falling away by itself.
    trauma: f32,
    time: f32,
    seed: u32,
    /// Sounds of cases landing, for the game to play: where each landed.
    pub casing_landed: Vec<Vec3>,
}

const TRACER_SPEED: f32 = 320.0;
const TRACER_LENGTH: f32 = 9.0;

impl Fx {
    pub fn new(level: &Level, renderer: &mut Renderer) -> Self {
        let mut pool = |tag: &str| -> Vec<Group> {
            let mut groups = Group::all(level, tag, renderer);
            for group in &mut groups {
                group.set_hidden(renderer, true);
            }
            groups
        };
        let tracer_pool = pool("tracer");
        let holes = pool("decal_hole");
        let scorches = pool("decal_scorch");
        let casing_pool = pool("casing");
        Self {
            muzzle: Channel::new(renderer, MUZZLE, 4, &["flash", "smoke"]),
            impact: Channel::new(renderer, IMPACT, 5, &["dust", "chips", "sparks"]),
            blood: Channel::new(renderer, BLOOD, 2, &["go"]),
            explosion: Channel::new(renderer, EXPLOSION, 2, &["go"]),
            smoulder: Effect::parse(SMOULDER).ok(),
            fire: Effect::parse(FIRE).ok(),
            plume: Effect::parse(PLUME).ok(),
            tracer_pool,
            tracers: Vec::new(),
            next_tracer: 0,
            holes,
            next_hole: 0,
            scorches,
            next_scorch: 0,
            casing_pool,
            casings: Vec::new(),
            next_casing: 0,
            light_slots: level.lights.get("flash").cloned().unwrap_or_default(),
            flares: Vec::new(),
            next_light: 0,
            trauma: 0.0,
            time: 0.0,
            seed: 0x9e37_79b9,
            casing_landed: Vec::new(),
        }
    }

    fn random(&mut self) -> f32 {
        self.seed ^= self.seed << 13;
        self.seed ^= self.seed >> 17;
        self.seed ^= self.seed << 5;
        (self.seed >> 8) as f32 / (1u32 << 24) as f32
    }

    fn signed(&mut self) -> f32 {
        self.random() * 2.0 - 1.0
    }

    /// A shot leaving a muzzle: the flash, its smoke and its light. `transform` is the
    /// muzzle's place, looking along its -Z.
    pub fn muzzle_flash(&mut self, transform: Mat4, strength: f32) {
        self.muzzle
            .puff(transform, vec![("flash", strength), ("smoke", strength)]);
        let position = transform.transform_point3(Vec3::new(0.0, 0.0, -0.25));
        self.flare(
            position,
            Vec3::new(1.0, 0.72, 0.38) * 90.0 * strength,
            7.0,
            0.05,
        );
    }

    /// A light that flares up and dies over `life` seconds.
    pub fn flare(&mut self, position: Vec3, colour: Vec3, range: f32, life: f32) {
        if self.light_slots.is_empty() {
            return;
        }
        // The oldest slot is taken over if all are lit.
        let slot = self.light_slots[self.next_light % self.light_slots.len()];
        self.next_light += 1;
        self.flares.retain(|flare| flare.slot != slot);
        self.flares.push(Flare {
            slot,
            position,
            colour,
            range,
            life,
            age: 0.0,
        });
    }

    /// A tracer from a muzzle to where its shot ended.
    pub fn tracer(&mut self, from: Vec3, to: Vec3) {
        let span = to - from;
        let length = span.length();
        if self.tracer_pool.is_empty() || length < 3.0 {
            return;
        }
        let group = self.next_tracer % self.tracer_pool.len();
        self.next_tracer += 1;
        self.tracers.retain(|tracer| tracer.group != group);
        self.tracers.push(Tracer {
            group,
            from,
            direction: span / length,
            travelled: 1.5,
            length,
        });
    }

    /// A bullet striking something: what flies off it, and the hole it leaves.
    pub fn impact(&mut self, point: Vec3, normal: Vec3, surface: Surface) {
        let normal = normal.normalize_or(Vec3::Y);
        let transform = Mat4::from_rotation_translation(Quat::from_rotation_arc(Vec3::Y, normal), point + normal * 0.02);
        if surface == Surface::Flesh {
            self.blood.puff(transform, vec![("go", 1.0)]);
            return;
        }
        // Dust and chips take the colour of what was hit; hard things spark.
        let (dust, chips, sparks, colour) = match surface {
            Surface::Concrete => (1.0, 1.0, 0.25, Vec3::new(0.42, 0.41, 0.38)),
            Surface::Asphalt => (0.8, 1.0, 0.2, Vec3::new(0.2, 0.2, 0.2)),
            Surface::Brick => (1.0, 1.0, 0.1, Vec3::new(0.42, 0.24, 0.17)),
            Surface::Dirt => (1.2, 0.9, 0.0, Vec3::new(0.26, 0.19, 0.12)),
            Surface::Grass => (0.8, 0.8, 0.0, Vec3::new(0.2, 0.18, 0.09)),
            Surface::Wood => (0.5, 1.2, 0.0, Vec3::new(0.46, 0.35, 0.22)),
            Surface::Metal => (0.25, 0.2, 1.3, Vec3::new(0.3, 0.3, 0.3)),
            Surface::Glass => (0.3, 1.4, 0.0, Vec3::new(0.7, 0.75, 0.75)),
            Surface::Cloth => (0.5, 0.3, 0.0, Vec3::new(0.4, 0.38, 0.33)),
            Surface::Flesh => unreachable!(),
        };
        self.impact.puff(
            transform,
            vec![
                ("dust", dust),
                ("chips", chips),
                ("sparks", sparks),
                ("r", colour.x),
                ("g", colour.y),
                ("b", colour.z),
            ],
        );
        if !matches!(surface, Surface::Grass | Surface::Dirt | Surface::Cloth) {
            self.decal(Decal::Hole, point, normal, 1.0);
        }
    }

    /// Lays a mark on a surface.
    pub fn decal(&mut self, kind: Decal, point: Vec3, normal: Vec3, scale: f32) {
        let turn = self.random() * std::f32::consts::TAU;
        let size = scale * (0.85 + self.random() * 0.3);
        let (pool, next) = match kind {
            Decal::Hole => (&mut self.holes, &mut self.next_hole),
            Decal::Scorch => (&mut self.scorches, &mut self.next_scorch),
        };
        if pool.is_empty() {
            return;
        }
        let index = *next % pool.len();
        *next += 1;
        // Decals lie in their own X and Z, facing +Y.
        let rotation = Quat::from_rotation_arc(Vec3::Y, normal) * Quat::from_rotation_y(turn);
        let lift = if kind == Decal::Hole { 0.004 } else { 0.012 };
        pool[index].waiting_place = Some(Mat4::from_scale_rotation_translation(
            Vec3::splat(size),
            rotation,
            point + normal * lift,
        ));
    }

    /// A spent case thrown from an ejection port.
    pub fn casing(&mut self, physics: &Physics, position: Vec3, velocity: Vec3) {
        if self.casing_pool.is_empty() {
            return;
        }
        let group = self.next_casing % self.casing_pool.len();
        self.next_casing += 1;
        self.casings.retain(|casing| casing.group != group);
        let floor = physics
            .raycast(position, Vec3::NEG_Y, 4.0, WORLD)
            .map_or(position.y - 1.5, |hit| hit.point.y);
        let spin = Vec3::new(self.signed(), self.signed(), self.signed()) * 28.0;
        let turn = self.random() * 6.0;
        self.casings.push(Casing {
            group,
            position,
            velocity,
            rotation: Quat::from_rotation_y(turn),
            spin,
            floor,
            age: 0.0,
            bounces: 0,
        });
    }

    /// An explosion: fire, smoke, sparks, debris, its light, its scorch, and a shaken view.
    pub fn explode(&mut self, point: Vec3, viewer: Vec3) {
        let transform = Mat4::from_translation(point + Vec3::Y * 0.2);
        self.explosion.puff(transform, vec![("go", 1.0)]);
        self.flare(point + Vec3::Y * 0.8, Vec3::new(1.0, 0.6, 0.25) * 9000.0, 26.0, 0.35);
        self.decal(Decal::Scorch, point, Vec3::Y, 1.0);
        let distance = point.distance(viewer);
        self.shake((1.0 - distance / 30.0).clamp(0.0, 1.0));
    }

    /// Starts something smouldering, for good: a wreck, a house.
    pub fn smoulder(&mut self, renderer: &mut Renderer, position: Vec3, heat: f32) {
        if let Some(effect) = &self.smoulder {
            if let Some(id) = renderer
                .particles()
                .spawn(effect, Mat4::from_translation(position))
            {
                renderer.particles().set(id, "heat", heat);
            }
        }
    }

    /// Lights a fire, for good: `heat` 1 fills an oil drum.
    pub fn fire(&mut self, renderer: &mut Renderer, position: Vec3, heat: f32) {
        if let Some(effect) = &self.fire {
            if let Some(id) = renderer
                .particles()
                .spawn(effect, Mat4::from_translation(position))
            {
                renderer.particles().set(id, "heat", heat);
            }
        }
    }

    /// Raises a column of smoke on the skyline, for good.
    pub fn plume(&mut self, renderer: &mut Renderer, position: Vec3, heat: f32) {
        if let Some(effect) = &self.plume {
            if let Some(id) = renderer
                .particles()
                .spawn(effect, Mat4::from_translation(position))
            {
                renderer.particles().set(id, "heat", heat);
            }
        }
    }

    /// Shakes the view: `amount` from 0 to 1.
    pub fn shake(&mut self, amount: f32) {
        self.trauma = (self.trauma + amount).min(1.0);
    }

    /// How far the shaking turns the view now: yaw, pitch and roll, in radians.
    pub fn view_shake(&self) -> Vec3 {
        let strength = self.trauma * self.trauma;
        let t = self.time * 31.0;
        Vec3::new(
            (t * 1.3).sin() * (t * 0.71 + 1.7).cos(),
            (t * 1.7 + 4.0).sin() * (t * 0.93).cos(),
            (t * 1.1 + 2.0).sin() * (t * 1.37 + 0.5).cos(),
        ) * strength
            * Vec3::new(0.025, 0.02, 0.035)
    }

    /// Moves everything on by `dt` and tells the renderer.
    pub fn update(&mut self, renderer: &mut Renderer, dt: f32) {
        self.time += dt;
        self.trauma = (self.trauma - dt * 1.4).max(0.0);
        self.muzzle.flush(renderer, dt);
        self.impact.flush(renderer, dt);
        self.blood.flush(renderer, dt);
        self.explosion.flush(renderer, dt);

        // Tracers fly; one that has arrived goes back to the pool.
        let pool = &mut self.tracer_pool;
        self.tracers.retain_mut(|tracer| {
            tracer.travelled += TRACER_SPEED * dt;
            let group = &mut pool[tracer.group];
            if tracer.travelled >= tracer.length + TRACER_LENGTH * 0.5 {
                group.set_hidden(renderer, true);
                return false;
            }
            let head = tracer.travelled.min(tracer.length);
            let tail = (tracer.travelled - TRACER_LENGTH).max(0.0);
            let middle = tracer.from + tracer.direction * (head + tail) * 0.5;
            // A tracer's mesh is a metre long, along its own Z.
            let world = Mat4::from_scale_rotation_translation(
                Vec3::new(1.0, 1.0, (head - tail).max(0.05)),
                Quat::from_rotation_arc(Vec3::NEG_Z, tracer.direction),
                middle,
            );
            if group.hidden() {
                group.place(renderer, world);
                group.set_hidden(renderer, false);
            } else {
                group.move_to(renderer, world);
            }
            true
        });

        for pool in [&mut self.holes, &mut self.scorches] {
            for group in pool.iter_mut() {
                if let Some(world) = group.waiting_place.take() {
                    group.place(renderer, world);
                    group.set_hidden(renderer, false);
                }
            }
        }

        // Spent cases fall, bounce a couple of times and lie still, then are taken away.
        let pool = &mut self.casing_pool;
        let landed = &mut self.casing_landed;
        self.casings.retain_mut(|casing| {
            casing.age += dt;
            let group = &mut pool[casing.group];
            if casing.age > 7.0 {
                group.set_hidden(renderer, true);
                return false;
            }
            let resting = casing.bounces >= 3;
            if !resting {
                casing.velocity.y -= 9.81 * dt;
                casing.position += casing.velocity * dt;
                let turn = casing.spin * dt;
                casing.rotation = (Quat::from_euler(glam::EulerRot::XYZ, turn.x, turn.y, turn.z)
                    * casing.rotation)
                    .normalize();
                if casing.position.y < casing.floor + 0.006 && casing.velocity.y < 0.0 {
                    casing.position.y = casing.floor + 0.006;
                    casing.velocity = Vec3::new(
                        casing.velocity.x * 0.45,
                        -casing.velocity.y * 0.32,
                        casing.velocity.z * 0.45,
                    );
                    casing.spin *= 0.4;
                    casing.bounces += 1;
                    if casing.bounces == 1 {
                        landed.push(casing.position);
                    }
                    if casing.bounces >= 3 {
                        // Lying on its side.
                        casing.rotation = Quat::from_rotation_y(casing.rotation.to_euler(glam::EulerRot::YXZ).0);
                    }
                }
            }
            let world = Mat4::from_rotation_translation(casing.rotation, casing.position);
            if group.hidden() {
                group.place(renderer, world);
                group.set_hidden(renderer, false);
            } else if !resting {
                group.move_to(renderer, world);
            }
            true
        });

        // Flares burn down. One that has gone out is made dark, once.
        self.flares.retain_mut(|flare| {
            flare.age += dt;
            let left = 1.0 - flare.age / flare.life;
            let alive = left > 0.0;
            let brightness = if alive { left * left } else { 0.0 };
            renderer.set_light(
                flare.slot,
                Light {
                    position: flare.position.to_array(),
                    range: flare.range,
                    intensity: (flare.colour * brightness).to_array(),
                    _pad: 0,
                },
            );
            alive
        });
    }
}
