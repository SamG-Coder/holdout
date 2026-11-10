//! How people move: a skeleton with its clips, walking and running blended by speed, one-off
//! actions faded over them, and a layer on top that is worked out rather than played back, so
//! that a soldier shoulders a rifle and points it exactly where they are aiming.
//!
//! A character's mesh faces +Z in its own space, with +Y up and +X to its left.

use crate::ik::{self, Limb, Posed};
use glam::{Mat4, Quat, Vec3};
use solstice_anim::{blend, duration, sample, Pose};
use solstice_asset::{Clip, Skeleton};
use std::collections::HashMap;

/// One arm's bones, and how its hand lies at rest.
#[derive(Clone, Debug)]
pub struct Arm {
    pub clavicle: usize,
    pub upper: usize,
    pub lower: usize,
    pub hand: usize,
    /// Index, middle, ring and little finger, each from its knuckle out.
    pub fingers: [[usize; 3]; 4],
    pub thumb: [usize; 3],
    /// In the rest pose, in the mesh's space: the way the fingers point, and the way the palm
    /// faces.
    pub finger_direction: Vec3,
    pub palm: Vec3,
    /// The axis each finger joint curls about, in that joint's own space.
    curl_axes: [[Vec3; 3]; 4],
    thumb_axes: [Vec3; 3],
}

impl Arm {
    pub fn limb(&self) -> Limb {
        Limb {
            upper: self.upper,
            lower: self.lower,
            end: self.hand,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Leg {
    pub thigh: usize,
    pub calf: usize,
    pub foot: usize,
}

/// The bones of a person, by what they do.
#[derive(Clone, Debug)]
pub struct Human {
    pub pelvis: usize,
    pub spine: [usize; 3],
    pub neck: usize,
    pub head: usize,
    /// Left, then right.
    pub arms: [Arm; 2],
    pub legs: [Leg; 2],
}

pub const LEFT: usize = 0;
pub const RIGHT: usize = 1;

/// A kind of character: its skeleton, its clips, and which bone is which.
pub struct Rig {
    pub skeleton: Skeleton,
    pub rest: Pose,
    pub rest_model: Vec<Mat4>,
    names: HashMap<String, usize>,
    clips: HashMap<String, Clip>,
    pub human: Human,
}

impl Rig {
    /// Gathers a character kit's skeleton and the clips fitted to it, named `ALIAS:CLIP` in the
    /// scene.
    pub fn new(
        alias: &str,
        skeleton_index: u32,
        skeletons: &[Skeleton],
        clips: &[Clip],
    ) -> Result<Self, String> {
        let skeleton = skeletons
            .get(skeleton_index as usize)
            .ok_or_else(|| format!("{alias}: the scene has no skeleton {skeleton_index}"))?
            .clone();
        let names: HashMap<String, usize> = skeleton
            .bones
            .iter()
            .enumerate()
            .map(|(index, bone)| (bone.name.clone(), index))
            .collect();
        let prefix = format!("{alias}:");
        let clips = clips
            .iter()
            .filter(|clip| clip.skeleton == skeleton_index)
            .filter_map(|clip| {
                clip.name
                    .strip_prefix(&prefix)
                    .map(|name| (name.to_owned(), clip.clone()))
            })
            .collect();
        let rest = Pose::rest(&skeleton);
        let rest_model = skeleton.rest();
        let human = find_human(&names, &rest_model, alias)?;
        Ok(Self {
            skeleton,
            rest,
            rest_model,
            names,
            clips,
            human,
        })
    }

    pub fn bone(&self, name: &str) -> Option<usize> {
        self.names.get(name).copied()
    }

    pub fn clip(&self, name: &str) -> Option<&Clip> {
        self.clips.get(name)
    }

    pub fn has_clip(&self, name: &str) -> bool {
        self.clips.contains_key(name)
    }

    pub fn clip_seconds(&self, name: &str) -> f32 {
        self.clip(name).map_or(0.0, duration)
    }

    pub fn bones(&self) -> usize {
        self.skeleton.bones.len()
    }
}

fn find_human(
    names: &HashMap<String, usize>,
    rest: &[Mat4],
    alias: &str,
) -> Result<Human, String> {
    let get = |name: &str| -> Result<usize, String> {
        names
            .get(name)
            .or_else(|| names.get(&name.to_lowercase()))
            .copied()
            .ok_or_else(|| format!("{alias}: the skeleton has no bone `{name}`"))
    };
    let at = |bone: usize| rest[bone].w_axis.truncate();
    let arm = |side: &str| -> Result<Arm, String> {
        let hand = get(&format!("hand_{side}"))?;
        let finger = |name: &str| -> Result<[usize; 3], String> {
            Ok([
                get(&format!("{name}_01_{side}"))?,
                get(&format!("{name}_02_{side}"))?,
                get(&format!("{name}_03_{side}"))?,
            ])
        };
        let fingers = [
            finger("index")?,
            finger("middle")?,
            finger("ring")?,
            finger("pinky")?,
        ];
        let thumb = finger("thumb")?;
        let finger_direction = (at(fingers[1][0]) - at(hand)).normalize_or(Vec3::NEG_Y);
        let across = at(fingers[3][0]) - at(fingers[0][0]);
        let mut palm = finger_direction.cross(across).normalize_or(Vec3::NEG_Y);
        // At rest the arms hang out and down, palms turned in and down: towards the ground and
        // the body.
        let inward = Vec3::new(-at(hand).x.signum(), -1.0, 0.0);
        if palm.dot(inward) < 0.0 {
            palm = -palm;
        }
        let curl_axis = |joint: usize, next: Vec3| -> Vec3 {
            let along = (next - at(joint)).normalize_or(finger_direction);
            let axis = along.cross(palm).normalize_or(Vec3::X);
            (Quat::from_mat4(&rest[joint]).inverse() * axis).normalize_or(Vec3::X)
        };
        let mut curl_axes = [[Vec3::X; 3]; 4];
        for (f, joints) in fingers.iter().enumerate() {
            for j in 0..3 {
                let next = if j < 2 {
                    at(joints[j + 1])
                } else {
                    at(joints[2]) + (at(joints[2]) - at(joints[1]))
                };
                curl_axes[f][j] = curl_axis(joints[j], next);
            }
        }
        // The thumb closes across the palm, towards the first finger.
        let mut thumb_axes = [Vec3::X; 3];
        for j in 0..3 {
            let next = if j < 2 {
                at(thumb[j + 1])
            } else {
                at(thumb[2]) + (at(thumb[2]) - at(thumb[1]))
            };
            let along = (next - at(thumb[j])).normalize_or(finger_direction);
            let towards = (palm * 0.75 + finger_direction * 0.25).normalize();
            let axis = along.cross(towards).normalize_or(Vec3::X);
            thumb_axes[j] = (Quat::from_mat4(&rest[thumb[j]]).inverse() * axis).normalize_or(Vec3::X);
        }
        Ok(Arm {
            clavicle: get(&format!("clavicle_{side}"))?,
            upper: get(&format!("upperarm_{side}"))?,
            lower: get(&format!("lowerarm_{side}"))?,
            hand,
            fingers,
            thumb,
            finger_direction,
            palm,
            curl_axes,
            thumb_axes,
        })
    };
    let leg = |side: &str| -> Result<Leg, String> {
        Ok(Leg {
            thigh: get(&format!("thigh_{side}"))?,
            calf: get(&format!("calf_{side}"))?,
            foot: get(&format!("foot_{side}"))?,
        })
    };
    Ok(Human {
        pelvis: get("pelvis")?,
        spine: [get("spine_01")?, get("spine_02")?, get("spine_03")?],
        neck: get("neck_01")?,
        head: get("head")?,
        arms: [arm("l")?, arm("r")?],
        legs: [leg("l")?, leg("r")?],
    })
}

/// A one-off clip playing over the walk: a flinch, a throw, a death.
#[derive(Clone, Debug)]
struct Action {
    clip: String,
    time: f32,
    speed: f32,
    fade_in: f32,
    fade_out: f32,
    /// Stays on its last frame when it ends, as a death does.
    hold: bool,
    /// Plays from its end to its start.
    reversed: bool,
    /// Only the bones above the waist.
    upper_body: bool,
}

/// What plays on one character's skeleton.
pub struct Animator {
    /// How far through a stride, 0..1.
    phase: f32,
    idle_time: f32,
    /// Eased towards how fast the character is really going.
    speed: f32,
    /// 0 standing, 1 crouched.
    crouch: f32,
    action: Option<Action>,
    /// The pose the last action left, held while the next fades in.
    scratch: Pose,
    upper_mask: Option<solstice_anim::BoneMask>,
}

/// How fast each clip's feet go, in metres a second: what speed it suits without sliding.
const WALK_PACE: f32 = 1.05;
const JOG_PACE: f32 = 4.6;
const SPRINT_PACE: f32 = 7.0;
const CROUCH_PACE: f32 = 1.2;

impl Animator {
    pub fn new(rig: &Rig) -> Self {
        Self {
            phase: 0.0,
            idle_time: 0.0,
            speed: 0.0,
            crouch: 0.0,
            action: None,
            scratch: rig.rest.clone(),
            upper_mask: None,
        }
    }

    /// Starts a one-off clip, fading in over `fade_in` seconds.
    pub fn play(&mut self, clip: &str, fade_in: f32, fade_out: f32, speed: f32, hold: bool) {
        self.action = Some(Action {
            clip: clip.to_owned(),
            time: 0.0,
            speed,
            fade_in,
            fade_out,
            hold,
            reversed: false,
            upper_body: false,
        });
    }

    /// The same, played backwards: getting up, reversed, is a way of going down.
    pub fn play_reversed(&mut self, clip: &str, fade_in: f32, speed: f32, hold: bool) {
        self.play(clip, fade_in, 0.2, speed, hold);
        if let Some(action) = &mut self.action {
            action.reversed = true;
        }
    }

    /// The same as `play`, on the bones above the waist only, so the legs keep walking.
    pub fn play_upper(&mut self, clip: &str, fade_in: f32, fade_out: f32, speed: f32) {
        self.play(clip, fade_in, fade_out, speed, false);
        if let Some(action) = &mut self.action {
            action.upper_body = true;
        }
    }

    pub fn stop_action(&mut self) {
        self.action = None;
    }

    /// The clip of the action playing, and how far through it is, 0..1.
    pub fn action(&self, rig: &Rig) -> Option<(&str, f32)> {
        let action = self.action.as_ref()?;
        let length = rig.clip_seconds(&action.clip).max(1.0e-3);
        Some((action.clip.as_str(), (action.time / length).min(1.0)))
    }

    /// Whether a whole-body action has the character: it shouldn't steer or shoot.
    pub fn busy(&self) -> bool {
        self.action.as_ref().is_some_and(|a| !a.upper_body)
    }

    /// Moves the animation on by `dt`: `speed` is how fast the character is going across the
    /// ground, `crouched` whether it keeps low.
    pub fn advance(&mut self, rig: &Rig, dt: f32, speed: f32, crouched: bool) {
        self.speed += (speed - self.speed) * (1.0 - (-dt * 10.0).exp());
        let target = if crouched { 1.0 } else { 0.0 };
        self.crouch += (target - self.crouch) * (1.0 - (-dt * 7.0).exp());
        self.idle_time += dt;
        let (stride_seconds, pace) = self.timing(rig);
        // Feet keep pace with the ground: a clip made for one speed plays faster or slower.
        let rate = if pace > 0.05 {
            (self.speed / pace).clamp(0.6, 1.5)
        } else {
            1.0
        };
        if stride_seconds > 1.0e-3 && self.speed > 0.05 {
            self.phase = (self.phase + dt * rate / stride_seconds).fract();
        }
        if let Some(action) = &mut self.action {
            action.time += dt * action.speed;
            let length = rig.clip_seconds(&action.clip);
            if action.time >= length && !action.hold {
                self.action = None;
            }
        }
    }

    /// How long the stride lasts at this speed, in seconds, and the speed its clips suit.
    fn timing(&self, rig: &Rig) -> (f32, f32) {
        let speed = self.speed;
        let length = |name: &str| rig.clip(name).map_or(1.0, duration);
        let (mut stride, mut pace) = if speed < WALK_PACE {
            (length("walk"), WALK_PACE)
        } else if speed < JOG_PACE {
            let w = (speed - WALK_PACE) / (JOG_PACE - WALK_PACE);
            (
                length("walk") + (length("jog") - length("walk")) * w,
                WALK_PACE + (JOG_PACE - WALK_PACE) * w,
            )
        } else {
            let w = ((speed - JOG_PACE) / (SPRINT_PACE - JOG_PACE)).clamp(0.0, 1.0);
            (
                length("jog") + (length("sprint") - length("jog")) * w,
                JOG_PACE + (SPRINT_PACE - JOG_PACE) * w,
            )
        };
        if self.crouch > 0.001 {
            stride += (length("crouch_walk") - stride) * self.crouch;
            pace += (CROUCH_PACE - pace) * self.crouch;
        }
        (stride, pace)
    }

    fn sample_gait(&self, rig: &Rig, out: &mut Pose, scratch: &mut Pose) -> (f32, f32) {
        let speed = self.speed;
        let lookup = |name: &str| rig.clip(name);
        // Standing clips, by speed.
        let (low, high, weight, pace) = if speed < WALK_PACE {
            ("idle", "walk", (speed / WALK_PACE).clamp(0.0, 1.0), WALK_PACE)
        } else if speed < JOG_PACE {
            let w = (speed - WALK_PACE) / (JOG_PACE - WALK_PACE);
            ("walk", "jog", w, WALK_PACE + (JOG_PACE - WALK_PACE) * w)
        } else {
            let w = ((speed - JOG_PACE) / (SPRINT_PACE - JOG_PACE)).clamp(0.0, 1.0);
            ("jog", "sprint", w, JOG_PACE + (SPRINT_PACE - JOG_PACE) * w)
        };
        let mut stride = 1.0;
        let sample_at = |name: &str, pose: &mut Pose| -> f32 {
            match lookup(name) {
                Some(clip) => {
                    let length = duration(clip);
                    let time = if name == "idle" || name == "crouch_idle" {
                        self.idle_time
                    } else {
                        self.phase * length
                    };
                    sample(clip, time, pose);
                    length
                }
                None => {
                    pose.copy_from(&rig.rest);
                    1.0
                }
            }
        };
        let low_length = sample_at(low, out);
        if weight > 0.001 {
            let high_length = sample_at(high, scratch);
            blend(out, scratch, weight, None);
            stride = if low == "idle" {
                high_length
            } else {
                low_length + (high_length - low_length) * weight
            };
        } else if low != "idle" {
            stride = low_length;
        }
        let mut pace = pace;
        if self.crouch > 0.001 {
            let moving = (speed / CROUCH_PACE).clamp(0.0, 1.0);
            let mut crouched = scratch.clone();
            sample_at("crouch_idle", &mut crouched);
            if moving > 0.001 {
                let mut walking = scratch.clone();
                let length = sample_at("crouch_walk", &mut walking);
                blend(&mut crouched, &walking, moving, None);
                stride += (length - stride) * self.crouch;
                pace += (CROUCH_PACE - pace) * self.crouch;
            }
            blend(out, &crouched, self.crouch, None);
        }
        (stride, pace)
    }

    /// The pose to draw now, before anything is worked out on top of it.
    pub fn evaluate(&mut self, rig: &Rig) -> Pose {
        let mut pose = rig.rest.clone();
        let mut scratch = std::mem::replace(&mut self.scratch, rig.rest.clone());
        let _ = self.sample_gait(rig, &mut pose, &mut scratch);
        if let Some(action) = &self.action {
            if let Some(clip) = rig.clip(&action.clip) {
                let length = duration(clip).max(1.0e-3);
                let time = action.time.min(length);
                let at = if action.reversed { length - time } else { time };
                sample(clip, at, &mut scratch);
                let mut weight = if action.fade_in > 0.0 {
                    (action.time / action.fade_in).clamp(0.0, 1.0)
                } else {
                    1.0
                };
                if !action.hold && action.fade_out > 0.0 {
                    weight = weight.min(((length - action.time) / action.fade_out).clamp(0.0, 1.0));
                }
                let weight = weight * weight * (3.0 - 2.0 * weight);
                if action.upper_body {
                    let mask = self.upper_mask.get_or_insert_with(|| {
                        solstice_anim::BoneMask::branches(
                            &rig.skeleton,
                            &[rig.skeleton.bones[rig.human.spine[0]].name.as_str()],
                        )
                    });
                    blend(&mut pose, &scratch, weight, Some(mask));
                } else {
                    blend(&mut pose, &scratch, weight, None);
                }
            }
        }
        self.scratch = scratch;
        pose
    }

    /// The stride's length in seconds and the speed it suits, for callers that time footsteps.
    pub fn stride(&self, rig: &Rig) -> (f32, f32) {
        self.timing(rig)
    }

    pub fn phase(&self) -> f32 {
        self.phase
    }
}

/// Where a rifle sits in two hands: points on the weapon, in its own space (forward is -Z, up
/// +Y, right +X), and how the hands close on them.
#[derive(Clone, Copy, Debug)]
pub struct RifleHold {
    /// The middle of the pistol grip.
    pub grip: Vec3,
    /// Where the other hand holds the fore-end.
    pub support: Vec3,
    /// The end of the stock, which goes to the shoulder.
    pub butt: Vec3,
    pub muzzle: Vec3,
    /// How the other hand lies there: the way its fingers point and its palm faces. Under a
    /// rifle's fore-end the palm is up; round a pistol's grip it faces the pistol.
    pub support_fingers: Vec3,
    pub support_palm: Vec3,
}

/// The other hand under a fore-end: fingers across and forward, palm up.
pub const UNDER_FINGERS: Vec3 = Vec3::new(0.62, 0.3, -0.72);
pub const UNDER_PALM: Vec3 = Vec3::new(0.3, 0.93, 0.2);

impl Default for RifleHold {
    fn default() -> Self {
        Self {
            grip: Vec3::new(0.0, -0.055, 0.035),
            support: Vec3::new(0.0, -0.01, -0.27),
            butt: Vec3::new(0.0, 0.0, 0.31),
            muzzle: Vec3::new(0.0, 0.035, -0.62),
            support_fingers: UNDER_FINGERS,
            support_palm: UNDER_PALM,
        }
    }
}

/// What a soldier is doing with their upper body, for the worked-out layer.
#[derive(Clone, Copy, Debug)]
pub struct Stance {
    /// How far to the left of the way the body faces the aim is, in radians.
    pub aim_yaw: f32,
    /// How far above level.
    pub aim_pitch: f32,
    /// 0 with the rifle carried low across the body, 1 shouldered and sighted.
    pub shouldered: f32,
    /// 0 lets the clips move the arms; 1 has both hands on the rifle.
    pub armed: f32,
    /// A shot's kick, 1 at the moment of firing, falling away.
    pub recoil: f32,
    /// 0..1 through a reload, or negative when not reloading.
    pub reload: f32,
}

impl Default for Stance {
    fn default() -> Self {
        Self {
            aim_yaw: 0.0,
            aim_pitch: 0.0,
            shouldered: 0.0,
            armed: 1.0,
            recoil: 0.0,
            reload: -1.0,
        }
    }
}

/// A character posed, in its mesh's own space.
pub struct Figure {
    pub bones: Vec<Mat4>,
    /// Where the rifle is.
    pub weapon: Mat4,
    pub muzzle: Vec3,
    /// The way the muzzle points.
    pub muzzle_direction: Vec3,
    pub head: Vec3,
    pub chest: Vec3,
}

fn smooth(t: f32) -> f32 {
    let t = t.clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

/// Closes a hand's fingers by `curl` (0 open, 1 a fist), the first finger by its own amount.
fn close_hand(pose: &mut Pose, rig: &Rig, arm: &Arm, curl: f32, index_curl: f32, thumb_curl: f32) {
    const JOINT_ANGLES: [f32; 3] = [1.05, 1.35, 0.85];
    for (finger, joints) in arm.fingers.iter().enumerate() {
        let amount = if finger == 0 { index_curl } else { curl };
        // The outer fingers close a little further, as they do round a grip.
        let amount = amount * (1.0 + 0.06 * finger as f32);
        for (j, &bone) in joints.iter().enumerate() {
            pose.rotations[bone] = (rig.rest.rotations[bone]
                * Quat::from_axis_angle(arm.curl_axes[finger][j], JOINT_ANGLES[j] * amount))
            .normalize();
        }
    }
    const THUMB_ANGLES: [f32; 3] = [0.55, 0.35, 0.6];
    for (j, &bone) in arm.thumb.iter().enumerate() {
        pose.rotations[bone] = (rig.rest.rotations[bone]
            * Quat::from_axis_angle(arm.thumb_axes[j], THUMB_ANGLES[j] * thumb_curl))
        .normalize();
    }
}

/// The turn that takes a hand from its rest attitude to one whose fingers point along
/// `fingers` and whose palm faces `palm`, as a rotation of the hand bone in the mesh's space.
fn hand_rotation(rig: &Rig, arm: &Arm, fingers: Vec3, palm: Vec3) -> Quat {
    let frame = |forward: Vec3, facing: Vec3| -> Quat {
        let forward = forward.normalize_or(Vec3::Z);
        let side = forward.cross(facing).normalize_or(Vec3::X);
        let facing = side.cross(forward);
        Quat::from_mat3(&glam::Mat3::from_cols(side, forward, facing)).normalize()
    };
    let rest = frame(arm.finger_direction, arm.palm);
    let wanted = frame(fingers, palm);
    (wanted * rest.inverse() * Quat::from_mat4(&rig.rest_model[arm.hand])).normalize()
}

/// Where a hand should be: its wrist, the way its fingers point, the way its palm faces, and
/// how far its fingers close, all in the mesh's space.
#[derive(Clone, Copy, Debug)]
pub struct HandTarget {
    pub wrist: Vec3,
    pub fingers: Vec3,
    pub palm: Vec3,
    /// 0 open, 1 a fist: the three outer fingers, the first finger, and the thumb.
    pub curl: f32,
    pub index_curl: f32,
    pub thumb_curl: f32,
}

/// Where the two hands hold a rifle that is at `origin`, turned by `rotation`: the firing hand
/// round the pistol grip, the other under the fore-end.
pub fn rifle_hands(rotation: Quat, origin: Vec3, hold: &RifleHold) -> (HandTarget, HandTarget) {
    let on_weapon = |point: Vec3| origin + rotation * point;
    let fingers = rotation * Vec3::new(-0.25, 0.42, -0.87).normalize();
    let palm = rotation * Vec3::new(-0.88, -0.32, 0.34).normalize();
    let grip = HandTarget {
        wrist: on_weapon(hold.grip) - fingers * 0.075 - palm * 0.028,
        fingers,
        palm,
        curl: 0.95,
        index_curl: 0.42,
        thumb_curl: 0.7,
    };
    let fingers = rotation * hold.support_fingers.normalize();
    let palm = rotation * hold.support_palm.normalize();
    let support = HandTarget {
        wrist: on_weapon(hold.support) - fingers * 0.07 - palm * 0.032,
        fingers,
        palm,
        curl: 0.92,
        index_curl: 0.86,
        thumb_curl: 0.6,
    };
    (grip, support)
}

/// Brings the hands to their targets, by `weight` of the way from where the clips left them,
/// bending the arms with elbows down and out. `right` and `forward` are the body's own, in
/// the mesh's space.
pub fn place_hands(
    rig: &Rig,
    posed: &mut Posed<'_>,
    right_hand: Option<&HandTarget>,
    left_hand: Option<&HandTarget>,
    right: Vec3,
    forward: Vec3,
    weight: f32,
) {
    let human = &rig.human;
    let sides = [
        (LEFT, left_hand, right * -0.55 + Vec3::Y * -0.8 + forward * 0.1),
        (RIGHT, right_hand, right * 0.75 + Vec3::Y * -0.6 + forward * -0.25),
    ];
    for (side, target, pole) in sides {
        let Some(target) = target else {
            continue;
        };
        let arm = &human.arms[side];
        let hand = hand_rotation(rig, arm, target.fingers, target.palm);
        let wrist = posed.position(arm.hand).lerp(target.wrist, weight);
        let hand = posed.rotation(arm.hand).slerp(hand, weight);
        ik::reach(posed, arm.limb(), wrist, pole, Some(hand), 0.55);
    }
    for (side, target, _) in sides {
        if let Some(target) = target {
            close_hand(
                &mut posed.pose,
                rig,
                &human.arms[side],
                target.curl * weight,
                target.index_curl * weight,
                target.thumb_curl * weight,
            );
        }
    }
    posed.refresh();
}

/// Poses a soldier: the clips' pose, then the upper body leaned into the aim and both hands
/// brought to the rifle wherever that points.
pub fn pose_soldier(rig: &Rig, base: Pose, stance: &Stance, hold: &RifleHold) -> Figure {
    let human = &rig.human;
    let mut posed = Posed::new(&rig.skeleton, base);
    let armed = smooth(stance.armed);

    // The spine carries most of the aim, each bone a share, so the hips can go another way.
    let sighted = smooth(stance.shouldered);
    let yaw = stance.aim_yaw.clamp(-1.5, 1.5) * armed;
    let pitch = stance.aim_pitch.clamp(-1.2, 1.2) * armed;
    // Shouldered, the body stands bladed to the target: the firing shoulder drawn back.
    let blade = -0.42 * sighted * armed;
    const YAW_SHARE: [f32; 3] = [0.25, 0.3, 0.3];
    const PITCH_SHARE: [f32; 3] = [0.12, 0.2, 0.26];
    let mut turned = 0.0;
    for (index, &bone) in human.spine.iter().enumerate() {
        turned += yaw * YAW_SHARE[index];
        let right = Quat::from_rotation_y(turned) * Vec3::NEG_X;
        let delta = Quat::from_axis_angle(right, pitch * PITCH_SHARE[index])
            * Quat::from_rotation_y(yaw * YAW_SHARE[index] + blade / 3.0);
        posed.rotate(bone, delta);
    }
    // The head looks where the rifle points, and lies over to the stock.
    let look = Quat::from_rotation_y(yaw);
    let head_delta = Quat::from_axis_angle(look * Vec3::Z, -0.2 * sighted * armed)
        * Quat::from_axis_angle(look * Vec3::NEG_X, pitch * 0.4 - 0.1 * sighted * armed)
        * Quat::from_rotation_y(yaw * 0.15 - blade * 0.85);
    posed.rotate(human.neck, Quat::IDENTITY.slerp(head_delta, 0.5));
    posed.rotate(human.head, Quat::IDENTITY.slerp(head_delta, 0.5));

    let aim = Vec3::new(
        stance.aim_yaw.sin() * stance.aim_pitch.cos(),
        stance.aim_pitch.sin(),
        stance.aim_yaw.cos() * stance.aim_pitch.cos(),
    );
    let facing = Quat::from_rotation_y(yaw);
    let (right, forward) = (facing * Vec3::NEG_X, facing * Vec3::Z);

    // Where the rifle is: shouldered and sighted along the aim, or carried low across the body
    // with its muzzle down and to the left.
    let shoulder = posed.position(human.arms[RIGHT].upper);
    let chest = posed.position(human.spine[2]);
    let kick = stance.recoil.clamp(0.0, 1.5);
    let aimed_rotation = ik::basis(aim, Vec3::Y)
        * Quat::from_rotation_x(kick * 0.035)
        * Quat::from_rotation_z(-0.06);
    let pocket = shoulder + right * -0.05 + Vec3::Y * 0.005 + forward * 0.05;
    let aimed_butt = pocket - aim * (kick * 0.025);
    let low_direction = (forward * 0.72 + Vec3::Y * -0.52 + right * -0.46).normalize();
    let low_rotation = ik::basis(low_direction, Vec3::Y) * Quat::from_rotation_z(-0.5);
    let low_butt = shoulder + right * -0.02 + Vec3::Y * -0.13 + forward * 0.1;
    let rotation = low_rotation.slerp(aimed_rotation, sighted);
    let butt = low_butt.lerp(aimed_butt, sighted);
    let origin = butt - rotation * hold.butt;
    let weapon = Mat4::from_rotation_translation(rotation, origin);
    let on_weapon = |point: Vec3| origin + rotation * point;

    if armed > 0.001 {
        let (grip, mut support) = rifle_hands(rotation, origin, hold);
        if stance.reload >= 0.0 {
            // Down to the magazine, away to the belt for a fresh one, and back.
            let magazine = on_weapon(hold.grip + Vec3::new(0.0, -0.13, -0.11));
            let belt = posed.position(human.pelvis) + right * -0.2 + Vec3::Y * 0.02 + forward * 0.12;
            let t = stance.reload.clamp(0.0, 1.0);
            let to_magazine = smooth(t / 0.2) - smooth((t - 0.85) / 0.15);
            let to_belt = smooth((t - 0.3) / 0.15) - smooth((t - 0.55) / 0.15);
            support.wrist = support.wrist.lerp(magazine - support.fingers * 0.05, to_magazine);
            support.wrist = support.wrist.lerp(belt, to_belt);
        }
        place_hands(rig, &mut posed, Some(&grip), Some(&support), right, forward, armed);
    }

    Figure {
        muzzle: on_weapon(hold.muzzle),
        muzzle_direction: rotation * Vec3::NEG_Z,
        head: posed.position(human.head),
        chest,
        weapon,
        bones: posed.model,
    }
}

/// Poses someone with nothing in their hands: the clips' pose as it is.
pub fn pose_plain(rig: &Rig, base: Pose) -> Figure {
    let posed = Posed::new(&rig.skeleton, base);
    Figure {
        muzzle: Vec3::ZERO,
        muzzle_direction: Vec3::Z,
        head: posed.position(rig.human.head),
        chest: posed.position(rig.human.spine[2]),
        weapon: Mat4::IDENTITY,
        bones: posed.model,
    }
}
