//! What the game wants heard. The game only says what happened and where; the page (or a
//! desktop build with a sound device) makes the sounds.

use glam::Vec3;

/// One sound to play.
#[derive(Clone, Debug, PartialEq)]
pub struct Sound {
    /// Which sound: `rifle_shot`, `footstep_concrete`, `impact_metal`…
    pub name: &'static str,
    /// Where it is in the world, or `None` for one heard inside the player's own head: their
    /// own weapon, the interface, the radio.
    pub position: Option<Vec3>,
    /// How loud, 1 being the sound's own level.
    pub volume: f32,
    /// How fast it plays, 1 being its own speed: small changes keep repeats from sounding
    /// stamped out.
    pub pitch: f32,
}

/// The frame's sounds, and where they are heard from.
#[derive(Clone, Debug, Default)]
pub struct Audio {
    pub sounds: Vec<Sound>,
    pub listener: Vec3,
    pub listener_forward: Vec3,
    /// A slowly changing value from 0 to 1 the page uses to drive music: how hot the fight is.
    pub intensity: f32,
    seed: u32,
}

impl Audio {
    /// A small random number from -1 to 1, for varying pitch.
    fn jitter(&mut self) -> f32 {
        self.seed = self.seed.wrapping_mul(1_664_525).wrapping_add(1_013_904_223);
        (self.seed >> 8) as f32 / (1u32 << 23) as f32 - 1.0
    }

    /// Plays a sound in the world.
    pub fn at(&mut self, name: &'static str, position: Vec3, volume: f32) {
        let pitch = 1.0 + self.jitter() * 0.06;
        self.sounds.push(Sound {
            name,
            position: Some(position),
            volume,
            pitch,
        });
    }

    /// Plays a sound in the player's own head.
    pub fn own(&mut self, name: &'static str, volume: f32) {
        let pitch = 1.0 + self.jitter() * 0.04;
        self.sounds.push(Sound {
            name,
            position: None,
            volume,
            pitch,
        });
    }

    /// Takes the frame's sounds, leaving none.
    pub fn take(&mut self) -> Vec<Sound> {
        std::mem::take(&mut self.sounds)
    }
}
