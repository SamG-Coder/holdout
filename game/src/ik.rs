//! Posing bones by where they should reach rather than by how they turn: arms that hold a
//! rifle wherever it points, spines that lean into an aim, fingers that close round a grip.
//!
//! Everything here works on a [`Posed`]: a pose together with each bone's place in the mesh's
//! own space, kept in step as bones are turned.

use glam::{Mat4, Quat, Vec3};
use solstice_anim::Pose;
use solstice_asset::Skeleton;

/// A pose and where it puts each bone in the mesh's space.
pub struct Posed<'a> {
    pub skeleton: &'a Skeleton,
    pub pose: Pose,
    pub model: Vec<Mat4>,
}

impl<'a> Posed<'a> {
    pub fn new(skeleton: &'a Skeleton, pose: Pose) -> Self {
        let mut posed = Self {
            skeleton,
            pose,
            model: Vec::with_capacity(skeleton.bones.len()),
        };
        posed.refresh();
        posed
    }

    /// Works out every bone's place again from the pose.
    pub fn refresh(&mut self) {
        self.pose.to_model(self.skeleton, &mut self.model);
    }

    pub fn position(&self, bone: usize) -> Vec3 {
        self.model[bone].w_axis.truncate()
    }

    pub fn rotation(&self, bone: usize) -> Quat {
        Quat::from_mat4(&self.model[bone]).normalize()
    }

    fn parent_rotation(&self, bone: usize) -> Quat {
        self.skeleton.bones[bone]
            .parent
            .map_or(Quat::IDENTITY, |p| self.rotation(p as usize))
    }

    /// Turns a bone to `rotation` in the mesh's space, and carries what hangs from it along.
    pub fn set_rotation(&mut self, bone: usize, rotation: Quat) {
        self.pose.rotations[bone] = (self.parent_rotation(bone).inverse() * rotation).normalize();
        self.refresh();
    }

    /// Turns a bone by `delta`, a rotation in the mesh's space, about its own joint.
    pub fn rotate(&mut self, bone: usize, delta: Quat) {
        let rotation = delta * self.rotation(bone);
        self.set_rotation(bone, rotation);
    }

    /// Moves a bone to `position` in the mesh's space, keeping how it is turned.
    pub fn set_position(&mut self, bone: usize, position: Vec3) {
        let parent = self.skeleton.bones[bone]
            .parent
            .map_or(Mat4::IDENTITY, |p| self.model[p as usize]);
        self.pose.translations[bone] = parent.inverse().transform_point3(position);
        self.refresh();
    }
}

/// The rotation that turns direction `from` to direction `to` by the shortest way.
pub fn arc(from: Vec3, to: Vec3) -> Quat {
    let (from, to) = (from.normalize_or_zero(), to.normalize_or_zero());
    if from == Vec3::ZERO || to == Vec3::ZERO {
        return Quat::IDENTITY;
    }
    Quat::from_rotation_arc(from, to)
}

/// The rotation whose forward and up are these, forward being exact: its X is their cross.
pub fn basis(forward: Vec3, up: Vec3) -> Quat {
    let forward = forward.normalize_or(Vec3::NEG_Z);
    let right = forward.cross(up).normalize_or(Vec3::X);
    let up = right.cross(forward);
    Quat::from_mat3(&glam::Mat3::from_cols(right, up, -forward)).normalize()
}

/// The part of `rotation` that turns about `axis`: its twist.
pub fn twist_about(rotation: Quat, axis: Vec3) -> Quat {
    let axis = axis.normalize_or(Vec3::Y);
    let projected = axis * Vec3::new(rotation.x, rotation.y, rotation.z).dot(axis);
    let twist = Quat::from_xyzw(projected.x, projected.y, projected.z, rotation.w);
    if twist.length_squared() < 1.0e-10 {
        Quat::IDENTITY
    } else {
        twist.normalize()
    }
}

/// A limb of two bones and what it ends in: an arm to its hand, a leg to its foot.
#[derive(Clone, Copy, Debug)]
pub struct Limb {
    pub upper: usize,
    pub lower: usize,
    pub end: usize,
}

/// Bends a limb so that its end reaches `target`, as far as its length allows, with the middle
/// joint pushed towards `pole` (a direction in the mesh's space). `end_rotation` turns the end
/// bone too, and then `twist_share` of the end's twist about the lower bone is given to the
/// lower bone, as a forearm turns with its hand.
pub fn reach(
    posed: &mut Posed<'_>,
    limb: Limb,
    target: Vec3,
    pole: Vec3,
    end_rotation: Option<Quat>,
    twist_share: f32,
) {
    let a = posed.position(limb.upper);
    let b = posed.position(limb.lower);
    let c = posed.position(limb.end);
    let (upper_length, lower_length) = ((b - a).length(), (c - b).length());
    if upper_length < 1.0e-5 || lower_length < 1.0e-5 {
        return;
    }
    let span = target - a;
    let reach = span
        .length()
        .clamp((upper_length - lower_length).abs() + 1.0e-3, upper_length + lower_length - 1.0e-3);
    let direction = span.normalize_or(Vec3::NEG_Y);
    // The middle joint lies on a circle about the line to the target: the pole picks where.
    let cos_at_root = ((upper_length * upper_length + reach * reach - lower_length * lower_length)
        / (2.0 * upper_length * reach))
        .clamp(-1.0, 1.0);
    let sin_at_root = (1.0 - cos_at_root * cos_at_root).max(0.0).sqrt();
    let mut aside = pole - direction * pole.dot(direction);
    if aside.length_squared() < 1.0e-8 {
        aside = (b - a) - direction * (b - a).dot(direction);
    }
    let aside = aside.normalize_or(Vec3::X);
    let middle = a + direction * (upper_length * cos_at_root) + aside * (upper_length * sin_at_root);
    let end = a + direction * reach;

    let swing_upper = arc(b - a, middle - a);
    posed.rotate(limb.upper, swing_upper);
    let now_b = posed.position(limb.lower);
    let now_c = posed.position(limb.end);
    let swing_lower = arc(now_c - now_b, end - now_b);
    posed.rotate(limb.lower, swing_lower);

    if let Some(rotation) = end_rotation {
        if twist_share > 0.0 {
            let lower_rotation = posed.rotation(limb.lower);
            let along = posed.position(limb.end) - posed.position(limb.lower);
            // How far the end is turned about the lower bone, relative to how it sat before.
            let before = posed.rotation(limb.end);
            let turned = rotation * before.inverse();
            let twist = twist_about(turned, along);
            let share = Quat::IDENTITY.slerp(twist, twist_share.clamp(0.0, 1.0));
            posed.set_rotation(limb.lower, share * lower_rotation);
        }
        posed.set_rotation(limb.end, rotation);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use solstice_asset::Bone;

    /// A shoulder at the origin, an elbow 0.3 along X and a wrist 0.25 further.
    fn arm() -> Skeleton {
        let bone = |parent: Option<u32>, x: f32| Bone {
            name: String::new(),
            parent,
            translation: Vec3::new(x, 0.0, 0.0),
            rotation: Quat::IDENTITY,
            ..Default::default()
        };
        Skeleton {
            bones: vec![bone(None, 0.0), bone(Some(0), 0.3), bone(Some(1), 0.25)],
        }
    }

    const LIMB: Limb = Limb {
        upper: 0,
        lower: 1,
        end: 2,
    };

    #[test]
    fn a_limb_reaches_a_target_within_its_length() {
        let skeleton = arm();
        let mut posed = Posed::new(&skeleton, Pose::rest(&skeleton));
        let target = Vec3::new(0.2, 0.3, -0.1);
        reach(&mut posed, LIMB, target, Vec3::NEG_Y, None, 0.0);
        assert!(posed.position(2).distance(target) < 1.0e-3, "{}", posed.position(2));
        // Bone lengths are kept.
        assert!((posed.position(1).length() - 0.3).abs() < 1.0e-4);
        assert!((posed.position(2).distance(posed.position(1)) - 0.25).abs() < 1.0e-4);
        // The elbow goes to the pole's side.
        assert!(posed.position(1).y < 0.15 * 0.3 / 0.2, "elbow {}", posed.position(1));
    }

    #[test]
    fn a_target_out_of_reach_is_reached_towards() {
        let skeleton = arm();
        let mut posed = Posed::new(&skeleton, Pose::rest(&skeleton));
        reach(&mut posed, LIMB, Vec3::new(0.0, 3.0, 0.0), Vec3::X, None, 0.0);
        let end = posed.position(2);
        assert!(end.y > 0.54 && end.x.abs() < 0.03, "straight up: {end}");
    }

    #[test]
    fn the_end_takes_the_rotation_given_and_shares_its_twist() {
        let skeleton = arm();
        let mut posed = Posed::new(&skeleton, Pose::rest(&skeleton));
        let turned = Quat::from_rotation_x(1.0);
        // At full stretch the arm stays along X, so the twist is about X alone.
        reach(&mut posed, LIMB, Vec3::new(0.5495, 0.0, 0.0), Vec3::NEG_Y, Some(turned), 0.5);
        assert!(posed.rotation(2).angle_between(turned) < 1.0e-3);
        let forearm = posed.rotation(1);
        assert!((forearm.angle_between(Quat::IDENTITY) - 0.5).abs() < 0.12, "half the twist");
    }

    #[test]
    fn a_basis_looks_where_it_is_told() {
        let rotation = basis(Vec3::X, Vec3::Y);
        assert!((rotation * Vec3::NEG_Z - Vec3::X).length() < 1.0e-5);
        assert!((rotation * Vec3::Y - Vec3::Y).length() < 1.0e-5);
    }
}
