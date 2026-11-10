//! Compiles a HOLDOUT level description into a Solstice scene file.
//!
//! ```text
//! levelc LEVEL.txt --output OUT.solstice [--texture-size N] [--raw-textures]
//! ```
//!
//! A level file has one command a line; `#` begins a comment. Paths are relative to the file.
//!
//! ```text
//! texture_size 1024
//! camera X Y Z YAW PITCH
//! light X Y Z RANGE R G B [name=NAME]        # a fixed light; a name lets the game drive it
//! dlight NAME COUNT                          # light slots the game moves about (muzzle flashes)
//! kit ALIAS PATH.glb [skinned] [roles=FILE]  # a model file; roles are for retargeting clips
//! place ALIAS[:PART] X Y Z YAW [scale=S] [sx= sy= sz=] [pitch=DEG] [roll=DEG]
//!       [collide=auto|none|hull|coarse] [tag=NAME] [surface=KIND]
//! pool NAME ALIAS[:PART] COUNT               # hidden copies the game shows and moves
//! clip ALIAS NAME SOURCE.glb SOURCE_CLIP [loop] [roles=FILE]
//! species NAME FILE.species                  # a tree of the level's own
//! breed NAME FILE.grass                      # a grass of the level's own
//! tree SPECIES X Y Z [yaw=DEG] [scale=S] [variant=N] [tint=R,G,B]
//! grass BREED X Y Z [turn=0..3] [variant=N] [tint=R,G,B]  # one patch, centred here
//! meta ANYTHING...                           # carried to the game untouched
//! ```
//!
//! What the game needs to know rides inside the scene as a gameplay file, `holdout.level`:
//! which instances each tag and pool became, the poses of skinned ones, light slots, tree
//! trunks to collide with, and every `meta` line.

use glam::{EulerRot, Mat4, Quat, Vec3};
use solstice_asset::scene::Viewpoint;
use solstice_asset::{Collide, GameFile, Instance, Light, Material, SceneAsset, NO_POSE};
use solstice_builder::{build_virtual_mesh, BuildOptions};
use solstice_import::animation::{by_name, read_clips, retarget, ClipFile};
use solstice_import::character::Roles;
use solstice_import::{append_model, import_gltf, ImportOptions, ModelPlacements};
use solstice_procgen::foliage::bark::BARK_TILE_METRES;
use solstice_procgen::foliage::grass::Meadow;
use solstice_procgen::foliage::tree::Species;
use std::collections::{HashMap, HashSet};
use std::fmt::Write as _;
use std::path::{Path, PathBuf};
use std::time::Instant;

/// The name of the gameplay file the game reads.
pub const LEVEL_FILE: &str = "holdout.level";
/// Where pooled copies wait, out of sight, until the game places them.
const POOL_DEPTH: f32 = -400.0;

/// What is known about one placement besides where it is.
#[derive(Clone, Default)]
struct Meta {
    collide: Collide,
    tag: Option<String>,
    /// What it is made of: `surface=wood`.
    surface: Option<String>,
}

#[derive(Default)]
struct Kit {
    path: PathBuf,
    skinned: bool,
    roles: Option<PathBuf>,
    placements: ModelPlacements,
    whole_meta: Vec<Meta>,
    parts_meta: Vec<Meta>,
    /// Clips to fit to this kit's skeleton: name, source file, source clip, loops, source roles.
    clips: Vec<(String, PathBuf, String, bool, Option<PathBuf>)>,
}

struct TreeLine {
    species: String,
    position: Vec3,
    yaw: f32,
    scale: f32,
    variant: u32,
    /// Multiplies the colour of its leaves: autumn, or drought.
    tint: [u8; 3],
}

struct GrassLine {
    breed: String,
    position: Vec3,
    turn: u32,
    variant: u32,
    tint: [u8; 3],
}

/// Reads a tint written `r,g,b`, each from 0 to 2, kept to a hundredth so that equal tints share
/// a material.
fn parse_tint(words: &Words<'_>) -> Result<[u8; 3], String> {
    let Some(text) = words.option("tint") else {
        return Ok([100; 3]);
    };
    let parts: Vec<f32> = text.split(',').filter_map(|part| part.parse().ok()).collect();
    if parts.len() != 3 {
        return Err(format!("tint={text}: a tint is r,g,b"));
    }
    Ok([0, 1, 2].map(|i| (parts[i].clamp(0.0, 2.5) * 100.0).round() as u8))
}

/// The words of a line after its keyword, split into plain values and `key=value` options.
struct Words<'a> {
    keyword: &'a str,
    plain: Vec<&'a str>,
    options: Vec<(&'a str, &'a str)>,
}

impl<'a> Words<'a> {
    fn parse(line: &'a str) -> Option<Self> {
        let line = line.split('#').next().unwrap_or("").trim();
        let mut words = line.split_whitespace();
        let keyword = words.next()?;
        let mut plain = Vec::new();
        let mut options = Vec::new();
        for word in words {
            match word.split_once('=') {
                Some((key, value)) if !key.is_empty() && !key.starts_with('-') => {
                    options.push((key, value));
                }
                _ => plain.push(word),
            }
        }
        Some(Self {
            keyword,
            plain,
            options,
        })
    }

    fn text(&self, index: usize) -> Result<&'a str, String> {
        self.plain
            .get(index)
            .copied()
            .ok_or_else(|| format!("'{}' is missing value {}", self.keyword, index + 1))
    }

    fn number(&self, index: usize) -> Result<f32, String> {
        let text = self.text(index)?;
        text.parse::<f32>()
            .ok()
            .filter(|n| n.is_finite())
            .ok_or_else(|| format!("'{text}' is not a number"))
    }

    fn vec3(&self, index: usize) -> Result<Vec3, String> {
        Ok(Vec3::new(
            self.number(index)?,
            self.number(index + 1)?,
            self.number(index + 2)?,
        ))
    }

    fn option(&self, key: &str) -> Option<&'a str> {
        self.options
            .iter()
            .find(|(k, _)| *k == key)
            .map(|(_, v)| *v)
    }

    fn option_number(&self, key: &str, default: f32) -> Result<f32, String> {
        match self.option(key) {
            None => Ok(default),
            Some(text) => text
                .parse::<f32>()
                .ok()
                .filter(|n| n.is_finite())
                .ok_or_else(|| format!("{key}='{text}' is not a number")),
        }
    }

    fn flag(&self, name: &str) -> bool {
        self.plain.contains(&name)
    }

    fn known_options(&self, known: &[&str]) -> Result<(), String> {
        for (key, _) in &self.options {
            if !known.contains(key) {
                return Err(format!("'{}' has no option '{key}'", self.keyword));
            }
        }
        Ok(())
    }
}

fn parse_collide(words: &Words<'_>) -> Result<Collide, String> {
    Ok(match words.option("collide") {
        None | Some("auto") => Collide::Auto,
        Some("none") => Collide::None,
        Some("hull") => Collide::Hull,
        Some("coarse") => Collide::Coarse,
        Some(other) => return Err(format!("collide={other}: use auto, none, hull or coarse")),
    })
}

/// A placement's transform: where, turned about Y, tilted, and scaled.
fn placement(words: &Words<'_>, first: usize) -> Result<Mat4, String> {
    let position = words.vec3(first)?;
    let yaw = words.number(first + 3)?.to_radians();
    let pitch = words.option_number("pitch", 0.0)?.to_radians();
    let roll = words.option_number("roll", 0.0)?.to_radians();
    let uniform = words.option_number("scale", 1.0)?;
    let scale = Vec3::new(
        words.option_number("sx", uniform)?,
        words.option_number("sy", uniform)?,
        words.option_number("sz", uniform)?,
    );
    let rotation = Quat::from_euler(EulerRot::YXZ, yaw, pitch, roll);
    Ok(Mat4::from_scale_rotation_translation(
        scale, rotation, position,
    ))
}

fn split_part(text: &str) -> (&str, Option<&str>) {
    match text.split_once(':') {
        Some((kit, part)) => (kit, Some(part)),
        None => (text, None),
    }
}

/// Texture layers made so far by name, so that each bark and leaf atlas is baked once.
struct Layers {
    names: Vec<String>,
    first: usize,
}

struct Level {
    scene: SceneAsset,
    kits: Vec<(String, Kit)>,
    trees: Vec<TreeLine>,
    grass: Vec<GrassLine>,
    species: HashMap<String, Species>,
    breeds: HashMap<String, Meadow>,
    manifest: String,
    named_lights: Vec<(String, u32)>,
}

impl Level {
    fn kit(&mut self, alias: &str) -> Result<&mut Kit, String> {
        self.kits
            .iter_mut()
            .find(|(name, _)| name == alias)
            .map(|(_, kit)| kit)
            .ok_or_else(|| format!("no kit named '{alias}': declare it with a `kit` line first"))
    }

    fn add_placement(
        &mut self,
        target: &str,
        transform: Mat4,
        meta: Meta,
    ) -> Result<(), String> {
        let (alias, part) = split_part(target);
        let kit = self.kit(alias)?;
        match part {
            Some(part) => {
                kit.placements.parts.push((part.to_owned(), transform));
                kit.parts_meta.push(meta);
            }
            None => {
                kit.placements.whole.push(transform);
                kit.whole_meta.push(meta);
            }
        }
        Ok(())
    }

    fn command(&mut self, base: &Path, words: &Words<'_>) -> Result<(), String> {
        match words.keyword {
            "texture_size" => {
                let size = words.number(0)? as u32;
                if !size.is_power_of_two() {
                    return Err(format!("texture_size {size} is not a power of two"));
                }
                self.scene.texture_size = size;
            }
            "camera" => {
                let position = words.vec3(0)?;
                self.scene.viewpoint = Some(Viewpoint {
                    position: position.to_array(),
                    yaw: words.number(3)?,
                    pitch: words.number(4)?,
                });
            }
            "light" => {
                words.known_options(&["name"])?;
                let position = words.vec3(0)?;
                let index = self.scene.lights.len() as u32;
                self.scene.lights.push(Light {
                    position: position.to_array(),
                    range: words.number(3)?,
                    intensity: words.vec3(4)?.to_array(),
                    _pad: 0,
                });
                if let Some(name) = words.option("name") {
                    self.named_lights.push((name.to_owned(), index));
                }
            }
            "dlight" => {
                let name = words.text(0)?;
                let count = words.number(1)? as u32;
                for _ in 0..count {
                    let index = self.scene.lights.len() as u32;
                    // Dark and out of the way until the game uses it.
                    self.scene.lights.push(Light {
                        position: [0.0, POOL_DEPTH, 0.0],
                        range: 0.01,
                        intensity: [0.0; 3],
                        _pad: 0,
                    });
                    self.named_lights.push((name.to_owned(), index));
                }
            }
            "kit" => {
                words.known_options(&["roles"])?;
                let alias = words.text(0)?.to_owned();
                if self.kits.iter().any(|(name, _)| *name == alias) {
                    return Err(format!("kit '{alias}' is declared twice"));
                }
                let kit = Kit {
                    path: base.join(words.text(1)?),
                    skinned: words.flag("skinned"),
                    roles: words.option("roles").map(|p| base.join(p)),
                    ..Default::default()
                };
                self.kits.push((alias, kit));
            }
            "place" => {
                words.known_options(&[
                    "scale", "sx", "sy", "sz", "pitch", "roll", "collide", "tag", "surface",
                ])?;
                let transform = placement(words, 1)?;
                let meta = Meta {
                    collide: parse_collide(words)?,
                    tag: words.option("tag").map(str::to_owned),
                    surface: words.option("surface").map(str::to_owned),
                };
                self.add_placement(words.text(0)?, transform, meta)?;
            }
            "pool" => {
                words.known_options(&["scale"])?;
                let name = words.text(0)?.to_owned();
                let target = words.text(1)?;
                let count = words.number(2)? as usize;
                let scale = words.option_number("scale", 1.0)?;
                for _ in 0..count {
                    let transform = Mat4::from_scale_rotation_translation(
                        Vec3::splat(scale),
                        Quat::IDENTITY,
                        Vec3::new(0.0, POOL_DEPTH, 0.0),
                    );
                    let meta = Meta {
                        collide: Collide::None,
                        tag: Some(name.clone()),
                        surface: None,
                    };
                    self.add_placement(target, transform, meta)?;
                }
            }
            "clip" => {
                words.known_options(&["roles"])?;
                let name = words.text(1)?.to_owned();
                let source = base.join(words.text(2)?);
                let source_clip = words.text(3)?.to_owned();
                let looping = words.flag("loop");
                let roles = words.option("roles").map(|p| base.join(p));
                self.kit(words.text(0)?)?
                    .clips
                    .push((name, source, source_clip, looping, roles));
            }
            "species" => {
                let path = base.join(words.text(1)?);
                let text = std::fs::read_to_string(&path)
                    .map_err(|e| format!("{}: {e}", path.display()))?;
                let species =
                    Species::parse(&text).map_err(|e| format!("{}: {e}", path.display()))?;
                self.species.insert(words.text(0)?.to_owned(), species);
            }
            "breed" => {
                let path = base.join(words.text(1)?);
                let text = std::fs::read_to_string(&path)
                    .map_err(|e| format!("{}: {e}", path.display()))?;
                let breed = Meadow::parse(&text).map_err(|e| format!("{}: {e}", path.display()))?;
                self.breeds.insert(words.text(0)?.to_owned(), breed);
            }
            "tree" => {
                words.known_options(&["yaw", "scale", "variant", "tint"])?;
                self.trees.push(TreeLine {
                    species: words.text(0)?.to_owned(),
                    position: words.vec3(1)?,
                    yaw: words.option_number("yaw", 0.0)?.to_radians(),
                    scale: words.option_number("scale", 1.0)?,
                    variant: words.option_number("variant", 0.0)? as u32,
                    tint: parse_tint(words)?,
                });
            }
            "grass" => {
                words.known_options(&["turn", "variant", "tint"])?;
                self.grass.push(GrassLine {
                    breed: words.text(0)?.to_owned(),
                    position: words.vec3(1)?,
                    turn: words.option_number("turn", 0.0)? as u32,
                    variant: words.option_number("variant", 0.0)? as u32,
                    tint: parse_tint(words)?,
                });
            }
            other => return Err(format!("unknown command '{other}'")),
        }
        Ok(())
    }
}

/// Reads the clips every kit asks for from one source file, once.
fn clip_files(kits: &[(String, Kit)]) -> Result<HashMap<PathBuf, ClipFile>, String> {
    let mut looping: HashMap<PathBuf, HashSet<String>> = HashMap::new();
    for (_, kit) in kits {
        for (_, source, clip, loops, _) in &kit.clips {
            let set = looping.entry(source.clone()).or_default();
            if *loops {
                set.insert(clip.clone());
            }
        }
    }
    let mut files = HashMap::new();
    for (path, loops) in looping {
        println!("reading clips from {}...", path.display());
        let file = read_clips(&path, |name| loops.contains(name))
            .map_err(|e| format!("{}: {e}", path.display()))?;
        files.insert(path, file);
    }
    Ok(files)
}

/// Makes the texture layers a kit just added share with any identical layer already in the
/// scene: kits are built apart but draw on one library of materials, and each layer costs
/// megabytes. Returns how many were shared.
fn share_layers(
    scene: &mut SceneAsset,
    seen: &mut HashMap<u64, i32>,
    layers_before: usize,
    materials_before: usize,
) -> usize {
    use std::hash::{Hash, Hasher};
    let added: Vec<_> = scene.textures.drain(layers_before..).collect();
    let mut remap: Vec<i32> = Vec::with_capacity(added.len());
    let mut shared = 0;
    for layer in added {
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        for mips in [&layer.color_mips, &layer.normal_mips, &layer.material_mips] {
            mips.first().map(Vec::as_slice).unwrap_or(&[]).hash(&mut hasher);
        }
        let hash = hasher.finish();
        match seen.get(&hash) {
            Some(&existing) => {
                remap.push(existing);
                shared += 1;
            }
            None => {
                let index = scene.textures.len() as i32;
                seen.insert(hash, index);
                scene.textures.push(layer);
                remap.push(index);
            }
        }
    }
    for material in &mut scene.materials[materials_before..] {
        if material.texture_layer >= layers_before as i32 {
            material.texture_layer = remap[material.texture_layer as usize - layers_before];
        }
    }
    shared
}

fn read_roles(path: &Path) -> Result<Roles, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    Roles::parse(&text).map_err(|e| format!("{}: {e}", path.display()))
}

fn layer(
    layers: &mut Layers,
    scene: &mut SceneAsset,
    name: &str,
    make: impl FnOnce() -> solstice_procgen::surface::Surface,
) -> i32 {
    if let Some(index) = layers.names.iter().position(|n| n == name) {
        return (layers.first + index) as i32;
    }
    println!("  texture {name}");
    layers.names.push(name.to_owned());
    scene.textures.push(make().bake(scene.texture_size));
    scene.textures.len() as i32 - 1
}

fn build(path: &Path, texture_size: Option<u32>) -> Result<SceneAsset, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let base = path.parent().unwrap_or(Path::new("."));
    let mut level = Level {
        scene: SceneAsset {
            texture_size: 1024,
            ..Default::default()
        },
        kits: Vec::new(),
        trees: Vec::new(),
        grass: Vec::new(),
        species: HashMap::new(),
        breeds: HashMap::new(),
        manifest: String::new(),
        named_lights: Vec::new(),
    };
    for (number, line) in text.lines().enumerate() {
        let at = |e: String| format!("{}:{}: {e}", path.display(), number + 1);
        let trimmed = line.split('#').next().unwrap_or("").trim();
        if let Some(rest) = trimmed.strip_prefix("meta ") {
            level.manifest.push_str(rest.trim());
            level.manifest.push('\n');
            continue;
        }
        let Some(words) = Words::parse(line) else {
            continue;
        };
        level.command(base, &words).map_err(at)?;
    }
    if let Some(size) = texture_size {
        level.scene.texture_size = size;
    }
    let Level {
        mut scene,
        kits,
        trees,
        grass,
        species,
        breeds,
        mut manifest,
        named_lights,
    } = level;

    for (name, index) in &named_lights {
        writeln!(manifest, "light {name} {index}").unwrap();
    }

    // Kits: each file imported once, placed as often as asked.
    let clip_sources = clip_files(&kits)?;
    let options = ImportOptions {
        texture_size: scene.texture_size,
        ..Default::default()
    };
    let mut warnings: Vec<String> = Vec::new();
    let mut seen_layers: HashMap<u64, i32> = HashMap::new();
    let mut shared = 0;
    for (alias, kit) in &kits {
        let used = !kit.placements.whole.is_empty() || !kit.placements.parts.is_empty();
        if !used {
            println!("kit {alias} is never placed: skipped");
            continue;
        }
        println!("importing {}...", kit.path.display());
        let options = ImportOptions {
            skinned: kit.skinned,
            ..options
        };
        let imported =
            import_gltf(&kit.path, &options).map_err(|e| format!("{}: {e}", kit.path.display()))?;
        warnings.extend(imported.warnings.iter().map(|w| format!("{alias}: {w}")));
        let skeletons_before = scene.skeletons.len();
        let (layers_before, materials_before) = (scene.textures.len(), scene.materials.len());
        let ranges = append_model(&mut scene, imported, &kit.placements)
            .map_err(|e| format!("{}: {e}", kit.path.display()))?;
        shared += share_layers(&mut scene, &mut seen_layers, layers_before, materials_before);
        scene.collide.resize(scene.instances.len(), Collide::Auto);
        scene.instance_poses.resize(scene.instances.len(), NO_POSE);
        let transforms = kit
            .placements
            .whole
            .iter()
            .chain(kit.placements.parts.iter().map(|(_, transform)| transform));
        for ((range, meta), transform) in ranges
            .iter()
            .zip(kit.whole_meta.iter().chain(&kit.parts_meta))
            .zip(transforms)
        {
            for instance in range.clone() {
                scene.collide[instance as usize] = meta.collide;
            }
            if let Some(surface) = &meta.surface {
                writeln!(
                    manifest,
                    "surf {} {} {surface}",
                    range.start,
                    range.end - range.start
                )
                .unwrap();
            }
            if let Some(tag) = &meta.tag {
                let pose = range
                    .clone()
                    .map(|i| scene.instance_poses[i as usize])
                    .find(|p| *p != NO_POSE);
                let pose = pose.map_or(-1, i64::from);
                write!(
                    manifest,
                    "inst {tag} {} {} {pose}",
                    range.start,
                    range.end - range.start
                )
                .unwrap();
                for value in transform.to_cols_array() {
                    write!(manifest, " {value}").unwrap();
                }
                manifest.push('\n');
            }
        }
        if kit.skinned {
            if scene.skeletons.len() != skeletons_before + 1 {
                return Err(format!(
                    "{}: a skinned kit must hold exactly one skeleton",
                    kit.path.display()
                ));
            }
            let skeleton = skeletons_before as u32;
            writeln!(manifest, "skeleton {alias} {skeleton}").unwrap();
            let target = scene.skeletons[skeletons_before].clone();
            let target_roles = kit.roles.as_deref().map(read_roles).transpose()?;
            for (name, source, source_clip, looping, source_roles) in &kit.clips {
                let file = &clip_sources[source];
                let (_, frames) = file
                    .clips
                    .iter()
                    .find(|(n, _)| n == source_clip)
                    .ok_or_else(|| format!("{}: no clip '{source_clip}'", source.display()))?;
                let fitted = match (source_roles, &target_roles) {
                    (Some(from), Some(to)) => {
                        retarget(&file.rig, &read_roles(from)?, &target, to, frames)
                    }
                    _ => by_name(&file.rig, &target, frames),
                };
                let clip =
                    solstice_anim::compress(&format!("{alias}:{name}"), skeleton, &fitted, *looping);
                scene.clips.push(clip);
            }
            println!("  {} clips fitted to {alias}", kit.clips.len());
        } else if !kit.clips.is_empty() {
            return Err(format!("kit {alias} has clips but is not `skinned`"));
        }
    }
    scene.instance_poses.resize(scene.instances.len(), NO_POSE);
    if shared > 0 {
        println!("{shared} texture layers were the same as another kit's, and are shared");
    }

    // Trees: each species grown a few ways, wood and leaves as two meshes placed together.
    let build_options = BuildOptions::default();
    let mut layers = Layers {
        names: Vec::new(),
        first: scene.textures.len(),
    };
    let mut grown: HashMap<(String, u32), (u32, u32, u32, f32)> = HashMap::new();
    let mut tinted: HashMap<(u32, [u8; 3]), u32> = HashMap::new();
    if !trees.is_empty() {
        println!("growing trees...");
    }
    for tree in &trees {
        let key = (tree.species.clone(), tree.variant);
        if !grown.contains_key(&key) {
            let kind = species
                .get(&tree.species)
                .cloned()
                .or_else(|| Species::by_name(&tree.species))
                .ok_or_else(|| format!("no tree species '{}'", tree.species))?;
            let plant = kind.grow(tree.variant);
            println!(
                "  {} {}: {} wood and {} leaf triangles",
                tree.species,
                tree.variant,
                plant.wood.triangle_count(),
                plant.leaves.triangle_count()
            );
            let first_mesh = scene.meshes.len() as u32;
            scene.meshes.push(build_virtual_mesh(&plant.wood, &build_options));
            scene
                .meshes
                .push(build_virtual_mesh(&plant.leaves, &build_options));
            let bark = kind.bark;
            let leaf = kind.leaves.kind;
            let bark_layer = layer(&mut layers, &mut scene, bark.name(), || bark.surface(0));
            let leaf_layer = layer(&mut layers, &mut scene, leaf.name(), || leaf.atlas(0));
            let bark_material = scene.materials.len() as u32;
            scene.materials.push(Material {
                base_color: [1.0; 4],
                roughness: 1.0,
                uv_scale: 1.0 / BARK_TILE_METRES,
                normal_strength: 1.0,
                texture_layer: bark_layer,
                ..Default::default()
            });
            scene.materials.push(Material {
                base_color: [1.0; 4],
                roughness: 1.0,
                normal_strength: 1.0,
                texture_layer: leaf_layer,
                flags: Material::TWO_SIDED | Material::FOLIAGE,
                ..Default::default()
            });
            grown.insert(
                key.clone(),
                (first_mesh, bark_material, bark_material + 1, kind.trunk_radius),
            );
        }
        let (mesh, bark, leaves, radius) = grown[&key];
        // A tinted tree has leaves of its own colour, on the same picture.
        let leaves = if tree.tint == [100; 3] {
            leaves
        } else {
            *tinted.entry((leaves, tree.tint)).or_insert_with(|| {
                let mut material = scene.materials[leaves as usize];
                for (channel, tint) in tree.tint.iter().enumerate() {
                    material.base_color[channel] *= f32::from(*tint) / 100.0;
                }
                scene.materials.push(material);
                scene.materials.len() as u32 - 1
            })
        };
        let transform = Mat4::from_scale_rotation_translation(
            Vec3::splat(tree.scale),
            Quat::from_rotation_y(tree.yaw),
            tree.position,
        );
        scene.instances.push(Instance {
            mesh,
            material: bark,
            transform,
        });
        scene.instances.push(Instance {
            mesh: mesh + 1,
            material: leaves,
            transform,
        });
        writeln!(
            manifest,
            "trunk {} {} {} {:.3}",
            tree.position.x,
            tree.position.y,
            tree.position.z,
            radius * tree.scale
        )
        .unwrap();
    }
    scene.collide.resize(scene.instances.len(), Collide::None);

    // Grass: each breed's patches share a few meshes and one atlas.
    let mut patches: HashMap<(String, u32), (u32, u32, f32)> = HashMap::new();
    if !grass.is_empty() {
        println!("growing grass...");
    }
    for patch in &grass {
        let key = (patch.breed.clone(), patch.variant);
        if !patches.contains_key(&key) {
            let breed = breeds
                .get(&patch.breed)
                .cloned()
                .or_else(|| Meadow::by_name(&patch.breed))
                .ok_or_else(|| format!("no grass breed '{}'", patch.breed))?;
            let seeded = Meadow {
                seed: patch.variant,
                ..breed.clone()
            };
            let mesh = seeded.mesh();
            println!(
                "  {} {}: {} triangles",
                patch.breed,
                patch.variant,
                mesh.triangle_count()
            );
            let mesh_index = scene.meshes.len() as u32;
            scene.meshes.push(build_virtual_mesh(&mesh, &build_options));
            let atlas = layer(
                &mut layers,
                &mut scene,
                &format!("grass_{}", patch.breed),
                || breed.atlas(0),
            );
            // One material a breed: look for it by its layer.
            let material = scene
                .materials
                .iter()
                .position(|m| m.texture_layer == atlas)
                .unwrap_or_else(|| {
                    scene.materials.push(Material {
                        base_color: [1.0; 4],
                        roughness: 1.0,
                        normal_strength: 1.0,
                        texture_layer: atlas,
                        flags: Material::TWO_SIDED | Material::FOLIAGE,
                        ..Default::default()
                    });
                    scene.materials.len() - 1
                }) as u32;
            patches.insert(key.clone(), (mesh_index, material, breed.size));
        }
        let (mesh, material, size) = patches[&key];
        let material = if patch.tint == [100; 3] {
            material
        } else {
            *tinted.entry((material, patch.tint)).or_insert_with(|| {
                let mut tinted_material = scene.materials[material as usize];
                for (channel, tint) in patch.tint.iter().enumerate() {
                    tinted_material.base_color[channel] *= f32::from(*tint) / 100.0;
                }
                scene.materials.push(tinted_material);
                scene.materials.len() as u32 - 1
            })
        };
        let half = size * 0.5;
        let transform = Mat4::from_translation(patch.position)
            * Mat4::from_rotation_y(patch.turn as f32 * std::f32::consts::FRAC_PI_2)
            * Mat4::from_translation(Vec3::new(-half, 0.0, -half));
        scene.instances.push(Instance {
            mesh,
            material,
            transform,
        });
    }
    scene.collide.resize(scene.instances.len(), Collide::None);
    scene.instance_poses.resize(scene.instances.len(), NO_POSE);

    for clip in &scene.clips {
        writeln!(
            manifest,
            "clip {} {} {}",
            clip.name, clip.skeleton, clip.frames
        )
        .unwrap();
    }

    warnings.sort();
    warnings.dedup();
    for warning in warnings {
        println!("warning: {warning}");
    }
    scene.gameplay = vec![GameFile {
        name: LEVEL_FILE.to_owned(),
        text: manifest,
    }];
    Ok(scene)
}

fn main() -> Result<(), String> {
    let mut args = std::env::args().skip(1);
    let mut input = None;
    let mut output = PathBuf::from("level.solstice");
    let mut texture_size = None;
    let mut raw_textures = false;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--output" => output = PathBuf::from(args.next().ok_or("--output needs a path")?),
            "--texture-size" => {
                texture_size = Some(
                    args.next()
                        .and_then(|v| v.parse().ok())
                        .ok_or("--texture-size needs a number")?,
                );
            }
            "--raw-textures" => raw_textures = true,
            other if !other.starts_with('-') => input = Some(PathBuf::from(other)),
            other => return Err(format!("unknown argument: {other}")),
        }
    }
    let input = input.ok_or("usage: levelc LEVEL.txt --output OUT.solstice")?;
    let start = Instant::now();
    let mut scene = build(&input, texture_size)?;
    if !raw_textures {
        println!("compressing {} texture layers...", scene.textures.len());
        solstice_builder::compress_textures(&mut scene);
    }
    println!(
        "{} meshes, {} instances, {} unique triangles, {} instanced triangles, {} lights, {} skeletons, {} poses, {} clips",
        scene.meshes.len(),
        scene.instances.len(),
        scene.unique_source_triangles(),
        scene.total_source_triangles(),
        scene.lights.len(),
        scene.skeletons.len(),
        scene.poses.len(),
        scene.clips.len(),
    );
    let bytes = solstice_asset::file::encode(&solstice_builder::paginate(&scene));
    if let Some(parent) = output.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    std::fs::write(&output, &bytes).map_err(|e| e.to_string())?;
    println!(
        "wrote {} ({:.1} MB) in {:.1}s",
        output.display(),
        bytes.len() as f64 / 1.0e6,
        start.elapsed().as_secs_f32()
    );
    Ok(())
}
