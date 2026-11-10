//! The physical world: the scene's baked collision as fixed shapes, people as capsules walked by
//! a character controller, loose things (grenades, debris) as rigid bodies, and the rays that
//! bullets and eyes follow.

use glam::{Mat4, Quat, Vec3};
use rapier3d::control::{CharacterAutostep, CharacterLength, KinematicCharacterController};
use rapier3d::parry::query::ShapeCastOptions;
use rapier3d::parry::shape::TriMeshFlags;
use rapier3d::parry::utils::Array2;
use rapier3d::prelude::*;
use solstice_asset::{Collision, CollisionShape, Heightfield, NO_SHAPE};
use std::collections::HashMap;

pub const GRAVITY: f32 = 9.81;
/// The tallest step a person climbs without jumping.
pub const MAX_STEP: f32 = 0.42;
pub const MAX_SLOPE_DEGREES: f32 = 48.0;
const TERMINAL_SPEED: f32 = 55.0;

/// The fixed world: the scene, invisible walls, tree trunks.
pub const WORLD: Group = Group::GROUP_1;
/// People's capsules, which block each other's way.
pub const BODIES: Group = Group::GROUP_2;
/// Loose things: grenades, casings, props.
pub const DEBRIS: Group = Group::GROUP_3;
/// The edges of the level, and things like coils of wire: they stop people, and nothing else.
pub const EDGE: Group = Group::GROUP_4;

/// The collider data that marks a collider as not being a scene instance.
const NO_INSTANCE: u128 = u128::MAX;

fn to_vector(v: Vec3) -> Vector {
    Vector::new(v.x, v.y, v.z)
}

fn from_vector(v: Vector) -> Vec3 {
    Vec3::new(v.x, v.y, v.z)
}

fn to_pose(position: Vec3, rotation: Quat) -> Pose {
    let mut pose = Pose::from_translation(to_vector(position));
    pose.rotation = Rotation::from_xyzw(rotation.x, rotation.y, rotation.z, rotation.w);
    pose
}

fn groups(memberships: Group, filter: Group) -> InteractionGroups {
    InteractionGroups::new(memberships, filter, InteractionTestMode::And)
}

/// Where a ray met something.
#[derive(Clone, Copy, Debug)]
pub struct RayHit {
    pub distance: f32,
    pub point: Vec3,
    pub normal: Vec3,
    /// The scene instance that was hit, if it was one.
    pub instance: Option<u32>,
}

/// A person's capsule in the world.
#[derive(Clone, Copy, Debug)]
pub struct Walker {
    body: RigidBodyHandle,
    collider: ColliderHandle,
}

/// How a walk came out.
#[derive(Clone, Copy, Debug, Default)]
pub struct Walked {
    /// Where the feet are now.
    pub feet: Vec3,
    pub grounded: bool,
    /// The vertical speed to carry into the next walk.
    pub vertical: f32,
}

/// A loose rigid body.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Loose(RigidBodyHandle);

pub struct Physics {
    bodies: RigidBodySet,
    colliders: ColliderSet,
    impulse_joints: ImpulseJointSet,
    multibody_joints: MultibodyJointSet,
    soft_bodies: SoftBodySet,
    pipeline: PhysicsPipeline,
    islands: IslandManager,
    broad_phase: DefaultBroadPhase,
    narrow_phase: NarrowPhase,
    ccd: CCDSolver,
    params: IntegrationParameters,
    controller: KinematicCharacterController,
    /// Problems with the scene's shapes, for the log.
    pub warnings: Vec<String>,
}

impl Default for Physics {
    fn default() -> Self {
        Self::new()
    }
}

impl Physics {
    pub fn new() -> Self {
        let controller = KinematicCharacterController {
            up: Vector::Y,
            offset: CharacterLength::Absolute(0.02),
            slide: true,
            autostep: Some(CharacterAutostep {
                max_height: CharacterLength::Absolute(MAX_STEP),
                min_width: CharacterLength::Absolute(0.12),
                include_dynamic_bodies: false,
            }),
            max_slope_climb_angle: MAX_SLOPE_DEGREES.to_radians(),
            min_slope_slide_angle: (MAX_SLOPE_DEGREES + 6.0).to_radians(),
            snap_to_ground: Some(CharacterLength::Absolute(0.25)),
            ..KinematicCharacterController::default()
        };
        Self {
            bodies: RigidBodySet::new(),
            colliders: ColliderSet::new(),
            impulse_joints: ImpulseJointSet::new(),
            multibody_joints: MultibodyJointSet::new(),
            soft_bodies: SoftBodySet::new(),
            pipeline: PhysicsPipeline::new(),
            islands: IslandManager::new(),
            broad_phase: DefaultBroadPhase::new(),
            narrow_phase: NarrowPhase::new(),
            ccd: CCDSolver::new(),
            params: IntegrationParameters::default(),
            controller,
            warnings: Vec::new(),
        }
    }

    /// Adds a scene's collision as the fixed world. `instance` gives where each instance is.
    pub fn add_scene(&mut self, collision: &Collision, instance: impl Fn(u32) -> Option<Mat4>) {
        let mut built: HashMap<(u32, [u32; 3]), Option<SharedShape>> = HashMap::new();
        for (index, &shape) in collision.instance_shapes.iter().enumerate() {
            if shape == NO_SHAPE {
                continue;
            }
            let Some(transform) = instance(index as u32) else {
                continue;
            };
            let (scale, rotation, translation) = transform.to_scale_rotation_translation();
            let sound = scale.is_finite()
                && scale.abs().min_element() > 1.0e-6
                && rotation.is_finite()
                && translation.is_finite();
            if !sound {
                self.warnings
                    .push(format!("instance {index} has a degenerate transform"));
                continue;
            }
            let key = (shape, scale_key(scale));
            let warnings = &mut self.warnings;
            let built = built
                .entry(key)
                .or_insert_with(|| build_shape(&collision.shapes[shape as usize], scale, warnings));
            if let Some(shape) = built {
                self.colliders.insert(
                    ColliderBuilder::new(shape.clone())
                        .position(to_pose(translation, rotation))
                        .collision_groups(groups(WORLD, Group::ALL))
                        .user_data(index as u128),
                );
            }
        }
        if let Some(ground) = &collision.heightfield {
            self.add_ground(ground);
        }
    }

    fn add_ground(&mut self, ground: &Heightfield) {
        let (rows, columns) = (ground.rows as usize, ground.columns as usize);
        let mut heights = Array2::new(rows, columns, vec![0.0; rows * columns]);
        for row in 0..rows {
            for column in 0..columns {
                heights[(row, column)] = ground.heights[row * columns + column];
            }
        }
        let size = Vec3::new(
            ground.spacing[0] * (columns - 1) as f32,
            1.0,
            ground.spacing[1] * (rows - 1) as f32,
        );
        let centre = Vec3::new(
            ground.origin[0] + size.x * 0.5,
            0.0,
            ground.origin[1] + size.z * 0.5,
        );
        self.colliders.insert(
            ColliderBuilder::new(SharedShape::heightfield(heights, to_vector(size)))
                .translation(to_vector(centre))
                .collision_groups(groups(WORLD, Group::ALL))
                .user_data(NO_INSTANCE),
        );
    }

    /// Adds an invisible wall: a box of this full size, centred here, turned about Y.
    pub fn add_blocker(&mut self, centre: Vec3, size: Vec3, yaw: f32) {
        let half = size * 0.5;
        self.colliders.insert(
            ColliderBuilder::cuboid(half.x, half.y, half.z)
                .position(to_pose(centre, Quat::from_rotation_y(yaw)))
                .collision_groups(groups(WORLD, Group::ALL))
                .user_data(NO_INSTANCE),
        );
    }

    /// Adds a wall only people are stopped by: shots and thrown things pass.
    pub fn add_edge(&mut self, centre: Vec3, size: Vec3, yaw: f32) {
        let half = size * 0.5;
        self.colliders.insert(
            ColliderBuilder::cuboid(half.x, half.y, half.z)
                .position(to_pose(centre, Quat::from_rotation_y(yaw)))
                .collision_groups(groups(EDGE, Group::ALL))
                .user_data(NO_INSTANCE),
        );
    }

    /// Adds a solid box that stands in for something drawn: `id` is what a ray that hits it
    /// reports as its instance.
    pub fn add_solid(&mut self, centre: Vec3, size: Vec3, yaw: f32, id: u32) {
        let half = size * 0.5;
        self.colliders.insert(
            ColliderBuilder::cuboid(half.x, half.y, half.z)
                .position(to_pose(centre, Quat::from_rotation_y(yaw)))
                .collision_groups(groups(WORLD, Group::ALL))
                .user_data(u128::from(id)),
        );
    }

    /// Adds a tree's trunk, standing at `foot`.
    pub fn add_trunk(&mut self, foot: Vec3, radius: f32, height: f32) {
        let half = height * 0.5;
        self.colliders.insert(
            ColliderBuilder::cylinder(half, radius.max(0.05))
                .translation(to_vector(foot + Vec3::Y * half))
                .collision_groups(groups(WORLD, Group::ALL))
                .user_data(NO_INSTANCE),
        );
    }

    /// Adds a person standing with their feet at `feet`.
    pub fn add_walker(&mut self, feet: Vec3, radius: f32, height: f32) -> Walker {
        let half = (height * 0.5 - radius).max(0.01);
        let body = self.bodies.insert(
            RigidBodyBuilder::kinematic_position_based()
                .translation(to_vector(feet + Vec3::Y * (half + radius))),
        );
        let collider = self.colliders.insert_with_parent(
            ColliderBuilder::capsule_y(half, radius)
                .collision_groups(groups(BODIES, WORLD | BODIES | DEBRIS | EDGE)),
            body,
            &mut self.bodies,
        );
        Walker { body, collider }
    }

    /// Whether a walker takes part: one that doesn't blocks nobody and is hit by nothing.
    pub fn set_walker_enabled(&mut self, walker: Walker, enabled: bool) {
        if let Some(collider) = self.colliders.get_mut(walker.collider) {
            collider.set_enabled(enabled);
        }
    }

    /// Changes how tall a walker stands, keeping its feet where they are: for crouching.
    pub fn set_walker_height(&mut self, walker: Walker, radius: f32, height: f32) {
        let feet = self.walker_feet(walker);
        let half = (height * 0.5 - radius).max(0.01);
        if let Some(collider) = self.colliders.get_mut(walker.collider) {
            collider.set_shape(SharedShape::capsule_y(half, radius));
        }
        if let Some(body) = self.bodies.get_mut(walker.body) {
            let centre = to_vector(feet + Vec3::Y * (half + radius));
            body.set_translation(centre, true);
            body.set_next_kinematic_translation(centre);
        }
    }

    fn walker_half_height(&self, walker: Walker) -> f32 {
        self.colliders
            .get(walker.collider)
            .and_then(|c| c.shape().as_capsule().map(|c| c.half_height() + c.radius))
            .unwrap_or(0.9)
    }

    pub fn walker_feet(&self, walker: Walker) -> Vec3 {
        let centre = self
            .bodies
            .get(walker.body)
            .map_or(Vec3::ZERO, |b| from_vector(b.translation()));
        centre - Vec3::Y * self.walker_half_height(walker)
    }

    /// Puts a walker's feet somewhere at once.
    pub fn place_walker(&mut self, walker: Walker, feet: Vec3) {
        let centre = to_vector(feet + Vec3::Y * self.walker_half_height(walker));
        if let Some(body) = self.bodies.get_mut(walker.body) {
            body.set_translation(centre, true);
            body.set_next_kinematic_translation(centre);
        }
    }

    /// Whether a capsule of this size could stand with its feet at the walker's feet: for
    /// standing up from a crouch.
    pub fn walker_fits(&self, walker: Walker, radius: f32, height: f32) -> bool {
        let feet = self.walker_feet(walker);
        let half = (height * 0.5 - radius).max(0.01);
        let shape = Capsule::new_y(half, radius - 0.02);
        let pose = to_pose(feet + Vec3::Y * (half + radius + 0.03), Quat::IDENTITY);
        let filter = QueryFilter::new()
            .exclude_sensors()
            .exclude_rigid_body(walker.body)
            .groups(groups(BODIES, WORLD | EDGE));
        let queries = self.broad_phase.as_query_pipeline(
            self.narrow_phase.query_dispatcher(),
            &self.bodies,
            &self.colliders,
            filter,
        );
        let fits = queries.intersect_shape(pose, &shape).next().is_none();
        fits
    }

    /// Walks a person by `velocity` (across the ground, metres a second) for `dt`, falling at
    /// `vertical` metres a second, as the character controller allows: sliding along walls,
    /// climbing steps, staying on the ground.
    pub fn walk(&mut self, walker: Walker, velocity: Vec3, vertical: f32, dt: f32) -> Walked {
        let Some(rigid) = self.bodies.get(walker.body) else {
            return Walked::default();
        };
        let collider = &self.colliders[walker.collider];
        let shape = collider.shared_shape().clone();
        let pose = *collider.position();
        let falling = (vertical - GRAVITY * dt).max(-TERMINAL_SPEED);
        let desired = Vec3::new(velocity.x, 0.0, velocity.z) * dt + Vec3::Y * falling * dt;
        let filter = QueryFilter::new()
            .exclude_sensors()
            .exclude_rigid_body(walker.body)
            .groups(groups(BODIES, WORLD | BODIES | EDGE));
        let queries = self.broad_phase.as_query_pipeline(
            self.narrow_phase.query_dispatcher(),
            &self.bodies,
            &self.colliders,
            filter,
        );
        let mut controller = self.controller;
        // Rising, there is no ground to hold on to: snapping would cancel a jump.
        if falling > 0.0 {
            controller.snap_to_ground = None;
        }
        let moved = controller.move_shape(dt, &queries, &*shape, &pose, to_vector(desired), |_| {});
        let next = rigid.translation() + moved.translation;
        // A ceiling stops a jump short.
        let blocked_above = falling > 0.0 && moved.translation.y < desired.y * 0.5;
        let vertical = if moved.grounded || blocked_above {
            0.0
        } else {
            falling
        };
        let half = self.walker_half_height(walker);
        let body = self.bodies.get_mut(walker.body).expect("found above");
        body.set_translation(next, true);
        body.set_next_kinematic_translation(next);
        Walked {
            feet: from_vector(next) - Vec3::Y * half,
            grounded: moved.grounded,
            vertical,
        }
    }

    fn ray_filter(mask: Group) -> QueryFilter<'static> {
        QueryFilter::new()
            .exclude_sensors()
            .groups(groups(Group::ALL, mask))
    }

    /// The first thing a ray meets among the groups in `mask`, within `reach`.
    pub fn raycast(&self, origin: Vec3, direction: Vec3, reach: f32, mask: Group) -> Option<RayHit> {
        let direction = direction.normalize_or_zero();
        if direction == Vec3::ZERO || !origin.is_finite() {
            return None;
        }
        let queries = self.broad_phase.as_query_pipeline(
            self.narrow_phase.query_dispatcher(),
            &self.bodies,
            &self.colliders,
            Self::ray_filter(mask),
        );
        let ray = Ray::new(to_vector(origin), to_vector(direction));
        let (handle, hit) = queries.cast_ray_and_get_normal(&ray, reach, true)?;
        let data = self.colliders.get(handle).map_or(NO_INSTANCE, |c| c.user_data);
        let mut normal = from_vector(hit.normal).normalize_or(Vec3::Y);
        // Two-sided meshes can answer with either face's normal: give the one that faces the ray.
        if normal.dot(direction) > 0.0 {
            normal = -normal;
        }
        Some(RayHit {
            distance: hit.time_of_impact,
            point: origin + direction * hit.time_of_impact,
            normal,
            instance: (data != NO_INSTANCE && data <= u128::from(u32::MAX)).then_some(data as u32),
        })
    }

    /// Whether nothing of the fixed world stands between two points.
    pub fn clear_line(&self, from: Vec3, to: Vec3) -> bool {
        let span = to - from;
        let length = span.length();
        if length < 1.0e-4 {
            return true;
        }
        self.raycast(from, span / length, length, WORLD).is_none()
    }

    /// The height of the fixed world below a point, within `reach`.
    pub fn ground_below(&self, from: Vec3, reach: f32) -> Option<f32> {
        self.raycast(from, -Vec3::Y, reach, WORLD)
            .map(|hit| hit.point.y)
    }

    /// Sweeps a ball along a path and says how far it gets before touching the fixed world, as a
    /// fraction of the way: for keeping the weapon out of walls, and the camera out of them.
    pub fn sweep_ball(&self, from: Vec3, to: Vec3, radius: f32) -> f32 {
        let span = to - from;
        if span.length_squared() < 1.0e-8 {
            return 1.0;
        }
        let queries = self.broad_phase.as_query_pipeline(
            self.narrow_phase.query_dispatcher(),
            &self.bodies,
            &self.colliders,
            Self::ray_filter(WORLD),
        );
        let options = ShapeCastOptions {
            max_time_of_impact: 1.0,
            target_distance: 0.0,
            stop_at_penetration: false,
            compute_impact_geometry_on_penetration: false,
        };
        queries
            .cast_shape(
                &to_pose(from, Quat::IDENTITY),
                to_vector(span),
                &Ball::new(radius),
                options,
            )
            .map_or(1.0, |(_, hit)| hit.time_of_impact.clamp(0.0, 1.0))
    }

    /// Throws a loose ball into the world: a grenade.
    pub fn add_loose_ball(
        &mut self,
        position: Vec3,
        velocity: Vec3,
        spin: Vec3,
        radius: f32,
        mass: f32,
        bounce: f32,
    ) -> Loose {
        let body = self.bodies.insert(
            RigidBodyBuilder::dynamic()
                .translation(to_vector(position))
                .linvel(to_vector(velocity))
                .angvel(to_vector(spin))
                .linear_damping(0.05)
                .angular_damping(0.6)
                .ccd_enabled(true),
        );
        self.colliders.insert_with_parent(
            ColliderBuilder::ball(radius)
                .mass(mass)
                .restitution(bounce)
                .friction(0.9)
                .collision_groups(groups(DEBRIS, WORLD | DEBRIS)),
            body,
            &mut self.bodies,
        );
        Loose(body)
    }

    /// Adds a loose box: a crate, a barrel standing in for one, a dropped weapon.
    pub fn add_loose_box(
        &mut self,
        position: Vec3,
        rotation: Quat,
        half: Vec3,
        velocity: Vec3,
        spin: Vec3,
        mass: f32,
    ) -> Loose {
        let body = self.bodies.insert(
            RigidBodyBuilder::dynamic()
                .pose(to_pose(position, rotation))
                .linvel(to_vector(velocity))
                .angvel(to_vector(spin))
                .linear_damping(0.1)
                .angular_damping(0.8),
        );
        self.colliders.insert_with_parent(
            ColliderBuilder::cuboid(half.x, half.y, half.z)
                .mass(mass)
                .restitution(0.25)
                .friction(0.8)
                .collision_groups(groups(DEBRIS, WORLD | DEBRIS | BODIES)),
            body,
            &mut self.bodies,
        );
        Loose(body)
    }

    pub fn loose_transform(&self, loose: Loose) -> Option<(Vec3, Quat)> {
        let body = self.bodies.get(loose.0)?;
        let rotation = body.rotation();
        Some((
            from_vector(body.translation()),
            Quat::from_xyzw(rotation.x, rotation.y, rotation.z, rotation.w),
        ))
    }

    pub fn loose_velocity(&self, loose: Loose) -> Vec3 {
        self.bodies
            .get(loose.0)
            .map_or(Vec3::ZERO, |b| from_vector(b.linvel()))
    }

    pub fn push_loose(&mut self, loose: Loose, impulse: Vec3) {
        if let Some(body) = self.bodies.get_mut(loose.0) {
            body.apply_impulse(to_vector(impulse), true);
        }
    }

    pub fn remove_loose(&mut self, loose: Loose) {
        self.bodies.remove(
            loose.0,
            &mut self.islands,
            &mut self.colliders,
            &mut self.impulse_joints,
            &mut self.multibody_joints,
            &mut self.soft_bodies,
            true,
        );
    }

    /// Moves the simulation on by `dt`, and brings the rays' view of the world up to date.
    pub fn step(&mut self, dt: f32) {
        self.params.dt = dt.clamp(1.0 / 480.0, 1.0 / 20.0);
        self.pipeline.step(
            to_vector(Vec3::new(0.0, -GRAVITY, 0.0)),
            &self.params,
            &mut self.islands,
            &mut self.broad_phase,
            &mut self.narrow_phase,
            &mut self.bodies,
            &mut self.colliders,
            &mut self.impulse_joints,
            &mut self.multibody_joints,
            &mut self.soft_bodies,
            &mut self.ccd,
            &(),
            &(),
        );
    }

    pub fn collider_count(&self) -> usize {
        self.colliders.len()
    }
}

/// The same for a scale at any turn, and different for sizes that differ by more than a part in
/// a few thousand.
fn scale_key(scale: Vec3) -> [u32; 3] {
    const IGNORED: u32 = 11;
    scale
        .to_array()
        .map(|s| s.to_bits().wrapping_add(1 << (IGNORED - 1)) >> IGNORED)
}

fn build_shape(
    shape: &CollisionShape,
    scale: Vec3,
    warnings: &mut Vec<String>,
) -> Option<SharedShape> {
    let vertices: Vec<Vector> = shape
        .vertices
        .iter()
        .map(|v| to_vector(Vec3::from_array(*v) * scale))
        .collect();
    if vertices.iter().any(|v| !v.is_finite()) {
        warnings.push("a collision shape has a vertex that isn't a number".to_owned());
        return None;
    }
    if shape.hull {
        let built = SharedShape::convex_hull(&vertices);
        if built.is_none() {
            warnings.push(format!("no convex hull of {} points", vertices.len()));
        }
        return built;
    }
    if shape.triangles.is_empty() {
        return None;
    }
    match SharedShape::trimesh_with_flags(
        vertices,
        shape.triangles.clone(),
        TriMeshFlags::FIX_INTERNAL_EDGES_TWO_SIDED,
    ) {
        Ok(built) => Some(built),
        Err(error) => {
            warnings.push(format!("a collision mesh was refused: {error:?}"));
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn floor() -> Physics {
        let mut physics = Physics::new();
        physics.add_blocker(Vec3::new(0.0, -0.5, 0.0), Vec3::new(40.0, 1.0, 40.0), 0.0);
        physics.step(1.0 / 60.0);
        physics
    }

    #[test]
    fn a_ray_finds_the_floor_and_its_normal() {
        let physics = floor();
        let hit = physics
            .raycast(Vec3::new(1.0, 3.0, 2.0), -Vec3::Y, 10.0, WORLD)
            .expect("the floor is below");
        assert!((hit.distance - 3.0).abs() < 1.0e-3);
        assert!(hit.normal.dot(Vec3::Y) > 0.99);
        assert!(physics.clear_line(Vec3::new(0.0, 1.0, 0.0), Vec3::new(5.0, 1.0, 0.0)));
        assert!(!physics.clear_line(Vec3::new(0.0, 1.0, 0.0), Vec3::new(0.0, -2.0, 0.0)));
    }

    #[test]
    fn a_walker_falls_to_the_floor_walks_and_is_stopped_by_a_wall() {
        let mut physics = floor();
        physics.add_blocker(Vec3::new(3.0, 1.5, 0.0), Vec3::new(0.4, 3.0, 10.0), 0.0);
        let walker = physics.add_walker(Vec3::new(0.0, 1.0, 0.0), 0.35, 1.8);
        physics.step(1.0 / 60.0);
        let mut walked = Walked::default();
        for _ in 0..90 {
            walked = physics.walk(walker, Vec3::ZERO, walked.vertical, 1.0 / 60.0);
            physics.step(1.0 / 60.0);
        }
        assert!(walked.grounded, "it lands");
        assert!(walked.feet.y.abs() < 0.05, "feet at {}", walked.feet.y);
        for _ in 0..240 {
            walked = physics.walk(walker, Vec3::X * 4.0, walked.vertical, 1.0 / 60.0);
            physics.step(1.0 / 60.0);
        }
        assert!(
            walked.feet.x > 2.0 && walked.feet.x < 2.8 - 0.3,
            "stopped at the wall: {}",
            walked.feet.x
        );
    }

    #[test]
    fn a_thrown_ball_lands_and_rests() {
        let mut physics = floor();
        let ball = physics.add_loose_ball(
            Vec3::new(0.0, 1.5, 0.0),
            Vec3::new(4.0, 2.0, 0.0),
            Vec3::ZERO,
            0.05,
            0.4,
            0.3,
        );
        for _ in 0..360 {
            physics.step(1.0 / 60.0);
        }
        let (position, _) = physics.loose_transform(ball).unwrap();
        assert!(position.y < 0.2 && position.y > 0.0, "resting at {position}");
        assert!(position.x > 1.0, "it flew forward: {position}");
    }
}
