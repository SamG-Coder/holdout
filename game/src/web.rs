//! The browser front end: a small API for the page to drive.
//!
//! The page owns the canvas, the animation loop, the keys and the mouse, the interface drawn
//! over the picture, and the sound. This owns the renderer and the game: the page hands over
//! the scene as it arrives, says what the player is pressing, asks for a frame, and is told
//! what to show and what to play.

use crate::input::Input;
use crate::{Game, SceneInfo};
use solstice_asset::scene::Viewpoint;
use solstice_asset::{file, Clip, CollisionIndex, GameFile, Skeleton};
use solstice_render::{Camera, Environment, Gpu, Quality, Renderer, RendererSettings, StreamingBudget};
use std::fmt::Write as _;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use wasm_bindgen::prelude::*;
use web_sys::HtmlCanvasElement;

fn error_string(error: impl std::fmt::Display) -> JsValue {
    JsValue::from_str(&error.to_string())
}

/// Sets up logging and panic messages. Runs once when the module loads.
#[wasm_bindgen(start)]
pub fn start() {
    console_error_panic_hook::set_once();
    let _ = console_log::init_with_level(log::Level::Info);
}

/// The game, bound to one canvas.
#[wasm_bindgen]
pub struct WebGame {
    gpu: Gpu,
    surface: wgpu::Surface<'static>,
    config: wgpu::SurfaceConfiguration,
    renderer: Renderer,
    gpu_errors: Arc<AtomicU32>,
    gameplay: Vec<GameFile>,
    collision: Option<CollisionIndex>,
    data_offset: u64,
    collision_pieces: Vec<Vec<u8>>,
    skeletons: Vec<Skeleton>,
    clips: Vec<Clip>,
    poses: Vec<u32>,
    viewpoint: Option<Viewpoint>,
    game: Option<Game>,
    input: Input,
    /// What the scene shows before the game starts: a slow turn about its viewpoint.
    idle_camera: Camera,
    idle_time: f32,
    paused: bool,
}

#[wasm_bindgen]
impl WebGame {
    /// Makes the renderer from a scene's unpacked manifest; the rest of the scene is asked for
    /// through `stream_requests`. Budgets are bytes of GPU memory. Rejects, with a message fit to
    /// show, if WebGPU or the GPU isn't up to it.
    pub async fn create(
        canvas: HtmlCanvasElement,
        manifest: Vec<u8>,
        data_offset: f64,
        geometry_budget: f64,
        texture_budget: f64,
    ) -> Result<WebGame, JsValue> {
        let scene = file::decode_manifest(&manifest, data_offset as u64).map_err(error_string)?;
        drop(manifest);
        let (width, height) = (canvas.width().max(1), canvas.height().max(1));
        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::BROWSER_WEBGPU,
            ..wgpu::InstanceDescriptor::new_without_display_handle()
        });
        let surface = instance
            .create_surface(wgpu::SurfaceTarget::Canvas(canvas))
            .map_err(error_string)?;
        let gpu = Gpu::request(&instance, Some(&surface), wgpu::PowerPreference::HighPerformance)
            .await
            .map_err(error_string)?;
        let gpu_errors = Arc::new(AtomicU32::new(0));
        let counter = gpu_errors.clone();
        gpu.device
            .on_uncaptured_error(Arc::new(move |error: wgpu::Error| {
                counter.fetch_add(1, Ordering::Relaxed);
                log::error!("GPU error: {error}");
            }));
        let mut config = surface
            .get_default_config(&gpu.adapter, width, height)
            .ok_or_else(|| JsValue::from_str("this canvas cannot be presented to"))?;
        config.format = config.format.remove_srgb_suffix();
        surface.configure(&gpu.device, &config);
        let renderer = Renderer::streaming(
            &gpu,
            &scene,
            config.format,
            RendererSettings::default(),
            StreamingBudget {
                geometry_bytes: geometry_budget as u64,
                texture_bytes: texture_budget as u64,
            },
        );
        let mut idle_camera = Camera::default();
        if let Some(viewpoint) = scene.viewpoint {
            idle_camera.position = glam::Vec3::from_array(viewpoint.position);
            idle_camera.yaw = viewpoint.yaw;
            idle_camera.pitch = viewpoint.pitch;
        }
        Ok(WebGame {
            gpu,
            surface,
            config,
            renderer,
            gpu_errors,
            gameplay: scene.gameplay,
            collision: scene.collision,
            data_offset: scene.data_offset,
            collision_pieces: Vec::new(),
            skeletons: scene.skeletons,
            clips: scene.clips,
            poses: scene.poses,
            viewpoint: scene.viewpoint,
            game: None,
            input: Input::new(),
            idle_camera,
            idle_time: 0.0,
            paused: false,
        })
    }

    /// What to fetch next, as a flat array with four numbers a request: its id, the first byte
    /// in the file, one past the last, and 1 if it must be inflated. Each must later go to
    /// `deliver` or `request_failed`.
    pub fn stream_requests(&mut self, max_fetching: u32) -> Vec<f64> {
        self.renderer
            .stream_requests(max_fetching)
            .iter()
            .flat_map(|request| {
                [
                    f64::from(request.id),
                    request.start as f64,
                    request.end as f64,
                    f64::from(u8::from(request.deflated)),
                ]
            })
            .collect()
    }

    pub fn deliver(&mut self, id: u32, bytes: Vec<u8>) -> bool {
        self.renderer.deliver(id, bytes)
    }

    pub fn request_failed(&mut self, id: u32) {
        self.renderer.request_failed(id);
    }

    /// How much of the scene's geometry is on the GPU, as pages installed and pages in all.
    pub fn pages(&self) -> Vec<u32> {
        let streaming = self.renderer.stats().streaming;
        vec![streaming.installed, streaming.pages.min(streaming.slots.max(1))]
    }

    /// How streaming stands, for finding out why a view will not sharpen.
    pub fn stream_stats(&self) -> String {
        let s = self.renderer.stats().streaming;
        format!(
            "pages {} installed {} slots {} in_transit {} starved {} evictions {} paused {} title {}",
            s.pages,
            s.installed,
            s.slots,
            s.in_transit,
            s.starved,
            s.evictions,
            self.paused,
            self.game.as_ref().is_none_or(Game::on_title),
        )
    }

    /// The parts of the file holding what the game collides with: two numbers each, the first
    /// byte and one past the last. Each is deflated.
    pub fn collision_ranges(&self) -> Vec<f64> {
        let Some(index) = &self.collision else {
            return Vec::new();
        };
        index
            .ranges()
            .iter()
            .flat_map(|&(offset, stored)| {
                let start = self.data_offset + offset;
                [start as f64, (start + u64::from(stored)) as f64]
            })
            .collect()
    }

    /// The size each part of the collision unpacks to: no more should ever be unpacked.
    pub fn collision_sizes(&self) -> Vec<f64> {
        self.collision.as_ref().map_or_else(Vec::new, |index| {
            index.raw_sizes().iter().map(|&s| s as f64).collect()
        })
    }

    /// Takes one part of the collision, inflated, in the order of `collision_ranges`.
    pub fn deliver_collision(&mut self, bytes: Vec<u8>) {
        self.collision_pieces.push(bytes);
    }

    /// Starts the game, once the collision has been delivered. Rejects with what is wrong.
    pub fn begin(&mut self) -> Result<(), JsValue> {
        let pieces = std::mem::take(&mut self.collision_pieces);
        let collision = match &self.collision {
            Some(index) => Some(index.decode(&pieces).map_err(error_string)?),
            None => None,
        };
        let info = SceneInfo {
            gameplay: &self.gameplay,
            collision: collision.as_ref(),
            skeletons: &self.skeletons,
            clips: &self.clips,
            poses: &self.poses,
            viewpoint: self.viewpoint,
        };
        let mut game = Game::new(&info, &mut self.renderer).map_err(|e| JsValue::from_str(&e))?;
        // One frame, so that everyone stands as they should and the weapon is in the hands
        // while the title is still up.
        self.input = Input::new();
        game.frame(&mut self.renderer, &mut self.input, 1.0 / 240.0);
        self.game = Some(game);
        Ok(())
    }

    pub fn started(&self) -> bool {
        self.game.is_some()
    }

    /// Updates the canvas size, in physical pixels.
    pub fn resize(&mut self, width: u32, height: u32) {
        if width > 0 && height > 0 {
            self.config.width = width;
            self.config.height = height;
            self.surface.configure(&self.gpu.device, &self.config);
        }
    }

    /// Holds the game still, as behind a menu, or lets it go on. The picture is still drawn.
    pub fn set_paused(&mut self, paused: bool) {
        self.paused = paused;
        if paused {
            self.input.release_all();
        }
    }

    /// Moves the game on by a frame and draws it.
    pub fn frame(&mut self, delta_seconds: f32) {
        let (camera, environment) = match &mut self.game {
            Some(game) if !self.paused => {
                let view = game.frame(&mut self.renderer, &mut self.input, delta_seconds);
                (view.camera, view.environment)
            }
            Some(game) => {
                let view = game.still(&mut self.renderer);
                self.input.end_frame();
                (view.camera, view.environment)
            }
            None => {
                // Before the game: the scene's own viewpoint, turning slowly.
                self.idle_time += delta_seconds;
                let mut camera = self.idle_camera;
                camera.yaw += (self.idle_time * 0.05).sin() * 0.25;
                (camera, idle_environment())
            }
        };
        let texture = match self.surface.get_current_texture() {
            wgpu::CurrentSurfaceTexture::Success(texture)
            | wgpu::CurrentSurfaceTexture::Suboptimal(texture) => texture,
            wgpu::CurrentSurfaceTexture::Outdated | wgpu::CurrentSurfaceTexture::Lost => {
                self.surface.configure(&self.gpu.device, &self.config);
                return;
            }
            _ => return,
        };
        let view = texture.texture.create_view(&Default::default());
        // Paused, time stands still for what is drawn; but under the title it runs on, so
        // that the clouds move and the view the title stands over streams in.
        let on_title = self.game.as_ref().is_none_or(Game::on_title);
        let seconds = if self.paused && !on_title { 0.0 } else { delta_seconds };
        self.renderer.render(
            &self.gpu,
            &camera,
            &environment,
            &view,
            (self.config.width, self.config.height),
            seconds,
        );
        self.gpu.queue.present(texture);
    }

    /// A key going down or up, by its `KeyboardEvent.code`.
    pub fn key(&mut self, code: &str, down: bool) {
        self.input.key(code, down);
    }

    /// A mouse button going down or up: `left`, `right` or `middle`.
    pub fn mouse_button(&mut self, button: &str, down: bool) {
        self.input.button(button, down);
    }

    /// The mouse moving by this many pixels, right and down.
    pub fn mouse_motion(&mut self, x: f32, y: f32) {
        self.input.mouse_motion(x, y);
    }

    pub fn wheel(&mut self, notches: f32) {
        self.input.wheel += notches;
    }

    /// A stick's push, each axis from -1 to 1 (right, forward), and a second stick's turn in
    /// pixels a second: for gamepads.
    pub fn sticks(&mut self, move_x: f32, move_y: f32, look_x: f32, look_y: f32) {
        self.input.stick = (move_x, move_y);
        self.input.stick_look = (look_x, look_y);
    }

    /// Lets every key and button go, for when the page loses the pointer or the focus.
    pub fn release_all(&mut self) {
        self.input.release_all();
    }

    /// Radians a pixel of mouse motion turns the view, and whether pushing the mouse away looks
    /// down.
    pub fn set_look(&mut self, sensitivity: f32, invert_y: bool) {
        self.input.sensitivity = sensitivity;
        self.input.invert_y = invert_y;
    }

    /// Applies a quality preset by name: `low`, `medium` or `high`. Returns false for another.
    pub fn set_quality(&mut self, name: &str) -> bool {
        match Quality::from_name(name) {
            Some(quality) => {
                self.renderer.settings_mut().apply_quality(quality);
                true
            }
            None => false,
        }
    }

    /// The picture's own resolution as a share of the canvas's.
    pub fn set_render_scale(&mut self, scale: f32) {
        self.renderer.settings_mut().render_scale = scale.clamp(0.4, 1.0);
    }

    /// What the interface shows, as JSON: see `Game::hud`.
    pub fn hud(&self) -> String {
        self.game.as_ref().map_or_else(String::new, |game| {
            game.hud(self.config.width as f32 / self.config.height.max(1) as f32)
        })
    }

    /// The sounds to play since this was last asked, one a line: its name, its place as
    /// `x y z` (or `-` for one in the player's own head), its volume and its pitch.
    pub fn take_sounds(&mut self) -> String {
        let Some(game) = &mut self.game else {
            return String::new();
        };
        let mut out = String::new();
        for sound in game.audio.take() {
            match sound.position {
                Some(p) => writeln!(out, "{} {:.2} {:.2} {:.2} {:.3} {:.3}", sound.name, p.x, p.y, p.z, sound.volume, sound.pitch),
                None => writeln!(out, "{} - - - {:.3} {:.3}", sound.name, sound.volume, sound.pitch),
            }
            .ok();
        }
        out
    }

    /// Where sound is heard from: the ear's place, the way it faces, and how hot the fight is
    /// (0 to 1), which drives the music.
    pub fn listener(&self) -> Vec<f32> {
        self.game.as_ref().map_or_else(Vec::new, |game| {
            let (at, facing) = (game.audio.listener, game.audio.listener_forward);
            vec![at.x, at.y, at.z, facing.x, facing.y, facing.z, game.audio.intensity]
        })
    }

    /// Starts the level again from its beginning or its last checkpoint.
    pub fn restart(&mut self) {
        if let Some(game) = &mut self.game {
            game.restart(&mut self.renderer);
        }
    }

    /// Carries out a developer's command: see `Game::debug_command`.
    pub fn debug(&mut self, command: &str) -> bool {
        self.game
            .as_mut()
            .is_some_and(|game| game.debug_command(command))
    }

    pub fn gpu_error_count(&self) -> u32 {
        self.gpu_errors.load(Ordering::Relaxed)
    }
}

/// The light on the scene before the game sets its own.
fn idle_environment() -> Environment {
    Environment {
        sun_direction: glam::Vec3::new(0.62, 0.3, 0.5).normalize(),
        sun_illuminance: 14.0,
        sky_intensity: 3.0,
        gi_intensity: 0.85,
        ..Default::default()
    }
}

/// Bytes to fetch first, to learn about the rest of a scene file.
#[wasm_bindgen]
pub fn header_bytes() -> u32 {
    file::HEADER_BYTES as u32
}

/// Reads the start of a scene file. Returns where the manifest starts and how large it is.
#[wasm_bindgen]
pub fn read_header(bytes: &[u8]) -> Result<Vec<f64>, JsValue> {
    let header = file::decode_header(bytes).map_err(error_string)?;
    Ok(vec![
        header.manifest_offset as f64,
        header.manifest_bytes as f64,
    ])
}
