//! What the level compiler tells the game about a scene: which instances each tag became,
//! light slots, tree trunks, clips, and the markers the level's author placed.
//!
//! It rides inside the scene file as the gameplay file `holdout.level`, one record a line.

use glam::{Mat4, Vec3};
use std::collections::HashMap;

/// The name of the gameplay file the level compiler writes.
pub const LEVEL_FILE: &str = "holdout.level";

/// One tagged placement: a run of renderer instances, and its pose if it is skinned.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Placed {
    pub first: u32,
    pub count: u32,
    pub pose: Option<u32>,
    /// Where the level put it. Each of its instances stands at this times its own place in
    /// the model.
    pub transform: Mat4,
}

impl Placed {
    pub fn instances(&self) -> std::ops::Range<u32> {
        self.first..self.first + self.count
    }
}

/// A marker the level's author placed: a spawn point, a trigger, a piece of cover.
#[derive(Clone, Debug, PartialEq)]
pub struct Marker {
    pub kind: String,
    pub name: String,
    pub position: Vec3,
    /// Radians about Y; zero faces -Z, as the camera does.
    pub yaw: f32,
    pub options: Vec<(String, String)>,
}

impl Marker {
    pub fn option(&self, key: &str) -> Option<&str> {
        self.options
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v.as_str())
    }

    pub fn number(&self, key: &str, default: f32) -> f32 {
        self.option(key)
            .and_then(|v| v.parse().ok())
            .unwrap_or(default)
    }

    /// The direction the marker faces, flat on the ground.
    pub fn forward(&self) -> Vec3 {
        Vec3::new(-self.yaw.sin(), 0.0, -self.yaw.cos())
    }
}

/// A box of this full size, centred here, turned about Y. With no surface it is an invisible
/// wall that stops people and nothing else; with one, it is solid, standing in for something
/// drawn whose own shape would be costly to collide with, and made of that.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Blocker {
    pub centre: Vec3,
    pub size: Vec3,
    pub yaw: f32,
    pub surface: Option<Surface>,
}

/// What a ray reports as the instance of a solid box: this, and what it is made of.
pub const SOLID_BASE: u32 = 0xFFFF_FF00;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Trunk {
    pub position: Vec3,
    pub radius: f32,
}

/// What something is made of, which decides how a bullet strikes it and a boot sounds on it.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub enum Surface {
    #[default]
    Concrete,
    Asphalt,
    Dirt,
    Grass,
    Wood,
    Metal,
    Brick,
    Glass,
    Cloth,
    Flesh,
}

impl Surface {
    const ALL: [Self; 10] = [
        Self::Concrete,
        Self::Asphalt,
        Self::Dirt,
        Self::Grass,
        Self::Wood,
        Self::Metal,
        Self::Brick,
        Self::Glass,
        Self::Cloth,
        Self::Flesh,
    ];

    /// The instance a solid box of this surface reports to a ray.
    pub fn solid_id(self) -> u32 {
        SOLID_BASE + Self::ALL.iter().position(|kind| *kind == self).unwrap_or(0) as u32
    }

    pub fn from_name(name: &str) -> Option<Self> {
        Some(match name {
            "concrete" => Self::Concrete,
            "asphalt" => Self::Asphalt,
            "dirt" => Self::Dirt,
            "grass" => Self::Grass,
            "wood" => Self::Wood,
            "metal" => Self::Metal,
            "brick" => Self::Brick,
            "glass" => Self::Glass,
            "cloth" => Self::Cloth,
            "flesh" => Self::Flesh,
            _ => return None,
        })
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::Concrete => "concrete",
            Self::Asphalt => "asphalt",
            Self::Dirt => "dirt",
            Self::Grass => "grass",
            Self::Wood => "wood",
            Self::Metal => "metal",
            Self::Brick => "brick",
            Self::Glass => "glass",
            Self::Cloth => "cloth",
            Self::Flesh => "flesh",
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct Level {
    /// What runs of instances are made of: first instance, count, kind.
    surfaces: Vec<(u32, u32, Surface)>,
    /// Every placement of each tag, in the order placed.
    pub placed: HashMap<String, Vec<Placed>>,
    /// Light slots by name.
    pub lights: HashMap<String, Vec<u32>>,
    /// Each skinned kit's skeleton.
    pub skeletons: HashMap<String, u32>,
    pub trunks: Vec<Trunk>,
    pub blockers: Vec<Blocker>,
    pub markers: Vec<Marker>,
    /// Loose settings: `set KEY VALUE...` lines.
    pub settings: HashMap<String, String>,
}

fn number(words: &[&str], index: usize) -> Result<f32, String> {
    let text = words
        .get(index)
        .ok_or_else(|| format!("missing value {index}"))?;
    text.parse::<f32>()
        .map_err(|_| format!("'{text}' is not a number"))
}

fn vec3(words: &[&str], index: usize) -> Result<Vec3, String> {
    Ok(Vec3::new(
        number(words, index)?,
        number(words, index + 1)?,
        number(words, index + 2)?,
    ))
}

impl Level {
    pub fn parse(text: &str) -> Result<Self, String> {
        let mut level = Level::default();
        for (index, line) in text.lines().enumerate() {
            let words: Vec<&str> = line.split_whitespace().collect();
            let Some(&keyword) = words.first() else {
                continue;
            };
            let at = |e: String| format!("{LEVEL_FILE}:{}: {e}", index + 1);
            match keyword {
                "inst" => {
                    let name = words.get(1).ok_or_else(|| at("inst needs a tag".into()))?;
                    let first = number(&words, 2).map_err(at)? as u32;
                    let count = number(&words, 3).map_err(at)? as u32;
                    let pose = number(&words, 4).map_err(at)?;
                    let mut cells = [0.0f32; 16];
                    if words.len() >= 21 {
                        for (index, cell) in cells.iter_mut().enumerate() {
                            *cell = number(&words, 5 + index).map_err(at)?;
                        }
                    } else {
                        cells = Mat4::IDENTITY.to_cols_array();
                    }
                    level
                        .placed
                        .entry((*name).to_owned())
                        .or_default()
                        .push(Placed {
                            first,
                            count,
                            pose: (pose >= 0.0).then_some(pose as u32),
                            transform: Mat4::from_cols_array(&cells),
                        });
                }
                "light" => {
                    let name = words.get(1).ok_or_else(|| at("light needs a name".into()))?;
                    let slot = number(&words, 2).map_err(at)? as u32;
                    level
                        .lights
                        .entry((*name).to_owned())
                        .or_default()
                        .push(slot);
                }
                "surf" => {
                    let first = number(&words, 1).map_err(at)? as u32;
                    let count = number(&words, 2).map_err(at)? as u32;
                    let kind = words
                        .get(3)
                        .and_then(|name| Surface::from_name(name))
                        .ok_or_else(|| at("surf needs a kind of surface".into()))?;
                    level.surfaces.push((first, count, kind));
                }
                "skeleton" => {
                    let name = words
                        .get(1)
                        .ok_or_else(|| at("skeleton needs a name".into()))?;
                    level
                        .skeletons
                        .insert((*name).to_owned(), number(&words, 2).map_err(at)? as u32);
                }
                "trunk" => level.trunks.push(Trunk {
                    position: vec3(&words, 1).map_err(at)?,
                    radius: number(&words, 4).map_err(at)?,
                }),
                "blocker" => level.blockers.push(Blocker {
                    centre: vec3(&words, 1).map_err(at)?,
                    size: vec3(&words, 4).map_err(at)?,
                    yaw: number(&words, 7).map_err(at)?.to_radians(),
                    surface: words.get(8).and_then(|name| Surface::from_name(name)),
                }),
                "marker" => {
                    let kind = words.get(1).ok_or_else(|| at("marker needs a kind".into()))?;
                    let name = words.get(2).ok_or_else(|| at("marker needs a name".into()))?;
                    let options = words[7.min(words.len())..]
                        .iter()
                        .filter_map(|word| word.split_once('='))
                        .map(|(k, v)| (k.to_owned(), v.to_owned()))
                        .collect();
                    level.markers.push(Marker {
                        kind: (*kind).to_owned(),
                        name: (*name).to_owned(),
                        position: vec3(&words, 3).map_err(at)?,
                        yaw: number(&words, 6).map_err(at)?.to_radians(),
                        options,
                    });
                }
                "set" => {
                    let key = words.get(1).ok_or_else(|| at("set needs a key".into()))?;
                    level
                        .settings
                        .insert((*key).to_owned(), words[2..].join(" "));
                }
                // Clips are found in the scene itself; the line is for people.
                "clip" => {}
                other => return Err(at(format!("unknown record '{other}'"))),
            }
        }
        Ok(level)
    }

    /// What an instance is made of: concrete, unless the level says otherwise.
    pub fn surface_of(&self, instance: Option<u32>) -> Surface {
        let Some(instance) = instance else {
            return Surface::Concrete;
        };
        if instance >= SOLID_BASE {
            let kind = (instance - SOLID_BASE) as usize;
            return Surface::ALL.get(kind).copied().unwrap_or_default();
        }
        self.surfaces
            .iter()
            .find(|(first, count, _)| instance >= *first && instance < first + count)
            .map_or(Surface::Concrete, |(_, _, kind)| *kind)
    }

    /// Every placement of a tag, or none.
    pub fn all(&self, tag: &str) -> &[Placed] {
        self.placed.get(tag).map_or(&[], Vec::as_slice)
    }

    /// The one placement of a tag, if it has exactly one... or its first.
    pub fn one(&self, tag: &str) -> Option<Placed> {
        self.all(tag).first().copied()
    }

    pub fn markers_of<'a>(&'a self, kind: &'a str) -> impl Iterator<Item = &'a Marker> + 'a {
        self.markers.iter().filter(move |m| m.kind == kind)
    }

    pub fn marker(&self, kind: &str, name: &str) -> Option<&Marker> {
        self.markers
            .iter()
            .find(|m| m.kind == kind && m.name == name)
    }

    pub fn setting(&self, key: &str) -> Option<&str> {
        self.settings.get(key).map(String::as_str)
    }

    pub fn setting_number(&self, key: &str, default: f32) -> f32 {
        self.setting(key)
            .and_then(|v| v.parse().ok())
            .unwrap_or(default)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn records_are_read() {
        let level = Level::parse(
            "inst rifle 10 3 -1\ninst guard 20 12 4\ninst guard 32 12 5\nlight muzzle 7\n\
             trunk 1 0 2 0.3\nblocker 0 1 0 2 2 0.2 90\n\
             marker spawn alpha 1 2 3 180 squad=a count=3\nset time 18.5\nskeleton guard 0\n",
        )
        .unwrap();
        assert_eq!(level.all("guard").len(), 2);
        assert_eq!(level.all("guard")[1].pose, Some(5));
        assert_eq!(level.one("rifle").unwrap().pose, None);
        assert_eq!(level.lights["muzzle"], vec![7]);
        assert_eq!(level.trunks[0].radius, 0.3);
        let marker = level.marker("spawn", "alpha").unwrap();
        assert_eq!(marker.option("squad"), Some("a"));
        assert_eq!(marker.number("count", 0.0), 3.0);
        assert!((marker.forward() - Vec3::Z).length() < 1.0e-5);
        assert_eq!(level.setting_number("time", 0.0), 18.5);
    }

    #[test]
    fn a_bad_line_is_named() {
        let error = Level::parse("inst a 1 2 3\nwhat\n").unwrap_err();
        assert!(error.contains(":2:"), "{error}");
    }
}
