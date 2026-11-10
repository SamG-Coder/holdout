//! Things the game moves about: a tagged placement's renderer instances kept together, so that
//! a rifle of several materials, or a character of a dozen meshes, is placed with one call.

use crate::level::{Level, Placed};
use glam::Mat4;
use solstice_render::Renderer;

/// The renderer instances of one placed thing, each with where it sits within the thing.
#[derive(Clone, Debug)]
pub struct Group {
    instances: Vec<(u32, Mat4)>,
    /// The character's pose, if the thing is skinned.
    pub pose: Option<u32>,
    hidden: bool,
    /// Somewhere it has been asked to go, by something that had no renderer to hand.
    pub waiting_place: Option<Mat4>,
}

impl Group {
    /// Gathers a placement's instances, and makes them movable.
    pub fn new(placed: &Placed, renderer: &mut Renderer) -> Self {
        let inverse = placed.transform.inverse();
        let instances = placed
            .instances()
            .filter_map(|id| {
                let world = renderer.instance_transform(id)?;
                renderer.set_instance_movable(id, true);
                Some((id, inverse * world))
            })
            .collect();
        Self {
            instances,
            pose: placed.pose,
            hidden: false,
            waiting_place: None,
        }
    }

    /// Every placement of a tag, as groups.
    pub fn all(level: &Level, tag: &str, renderer: &mut Renderer) -> Vec<Self> {
        level
            .all(tag)
            .iter()
            .map(|placed| Self::new(placed, renderer))
            .collect()
    }

    pub fn is_empty(&self) -> bool {
        self.instances.is_empty()
    }

    /// Moves the thing to `world`, as motion over the frame.
    pub fn move_to(&self, renderer: &mut Renderer, world: Mat4) {
        for (id, local) in &self.instances {
            renderer.move_instance(*id, world * *local);
        }
    }

    /// Puts the thing at `world` at once, with no motion shown getting there.
    pub fn place(&self, renderer: &mut Renderer, world: Mat4) {
        for (id, local) in &self.instances {
            renderer.place_instance(*id, world * *local);
        }
    }

    pub fn set_hidden(&mut self, renderer: &mut Renderer, hidden: bool) {
        if self.hidden == hidden {
            return;
        }
        self.hidden = hidden;
        for (id, _) in &self.instances {
            renderer.set_instance_hidden(*id, hidden);
        }
    }

    pub fn hidden(&self) -> bool {
        self.hidden
    }

    pub fn set_glow(&self, renderer: &mut Renderer, glow: f32) {
        for (id, _) in &self.instances {
            renderer.set_instance_glow(*id, glow);
        }
    }

    pub fn ids(&self) -> impl Iterator<Item = u32> + '_ {
        self.instances.iter().map(|(id, _)| *id)
    }
}
