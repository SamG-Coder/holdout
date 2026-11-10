//! The desktop runner: a window to play in, or a headless run that follows a script and saves
//! pictures, for checking the game without anyone at the keyboard.
//!
//! ```text
//! holdout SCENE.solstice [--size WxH] [--time HOURS] [--quality low|medium|high]
//! holdout SCENE.solstice --capture OUT.png [--frames N] [--size WxH] [--do "SCRIPT"]
//! ```
//!
//! A script is commands separated by `;`, each `FRAME: COMMAND`:
//!
//! ```text
//! 30: key KeyW down; 120: key KeyW up; 60: mouse 200 0; 90: button left down
//! 150: shot build/shots/a.png      # saves the picture as it is at that frame
//! 0: fly 10 2 5 0.5 -0.1           # flies the camera to x y z yaw pitch
//! 0: time 18.5
//! ```

#[cfg(target_arch = "wasm32")]
fn main() {}

#[cfg(not(target_arch = "wasm32"))]
fn main() {
    if let Err(error) = native::run() {
        eprintln!("error: {error}");
        std::process::exit(1);
    }
}

#[cfg(not(target_arch = "wasm32"))]
mod native {
    use holdout::input::Input;
    use holdout::{Game, SceneInfo};
    use solstice_asset::LoadedScene;
    use solstice_render::{Gpu, Quality, Renderer, RendererSettings};
    use std::path::{Path, PathBuf};
    use std::sync::{Arc, Mutex};
    use std::time::Instant;
    use winit::application::ApplicationHandler;
    use winit::dpi::PhysicalSize;
    use winit::event::{DeviceEvent, DeviceId, ElementState, MouseButton, WindowEvent};
    use winit::event_loop::{ActiveEventLoop, EventLoop};
    use winit::keyboard::{KeyCode, PhysicalKey};
    use winit::window::{CursorGrabMode, Fullscreen, Window, WindowId};

    const CAPTURE_FORMAT: wgpu::TextureFormat = wgpu::TextureFormat::Rgba8Unorm;
    type Failure = Box<dyn std::error::Error>;

    struct Options {
        scene: PathBuf,
        size: (u32, u32),
        capture: Option<PathBuf>,
        frames: u32,
        script: Vec<(u32, String)>,
        time: Option<f32>,
        quality: Option<Quality>,
        fullscreen: bool,
    }

    fn parse_script(text: &str) -> Result<Vec<(u32, String)>, String> {
        let mut script = Vec::new();
        for part in text.split(';') {
            let part = part.trim();
            if part.is_empty() {
                continue;
            }
            let (frame, command) = part
                .split_once(':')
                .ok_or_else(|| format!("'{part}': a script command is FRAME: COMMAND"))?;
            let frame = frame
                .trim()
                .parse()
                .map_err(|_| format!("'{frame}' is not a frame number"))?;
            script.push((frame, command.trim().to_owned()));
        }
        Ok(script)
    }

    fn parse_args() -> Result<Options, String> {
        let mut options = Options {
            scene: PathBuf::from("dist/assets/level.solstice"),
            size: (1600, 900),
            capture: None,
            frames: 120,
            script: Vec::new(),
            time: None,
            quality: None,
            fullscreen: false,
        };
        let mut args = std::env::args().skip(1);
        while let Some(arg) = args.next() {
            let mut value = || args.next().ok_or(format!("{arg} needs a value"));
            match arg.as_str() {
                "--size" => {
                    let text = value()?;
                    let (w, h) = text.split_once('x').ok_or("--size expects WxH")?;
                    options.size = (
                        w.parse().map_err(|e| format!("--size: {e}"))?,
                        h.parse().map_err(|e| format!("--size: {e}"))?,
                    );
                }
                "--capture" => options.capture = Some(PathBuf::from(value()?)),
                "--frames" => {
                    options.frames = value()?.parse().map_err(|e| format!("--frames: {e}"))?;
                }
                "--do" => options.script.extend(parse_script(&value()?)?),
                "--script" => {
                    let path = value()?;
                    let text = std::fs::read_to_string(&path).map_err(|e| format!("{path}: {e}"))?;
                    let joined: String = text
                        .lines()
                        .map(|line| line.split('#').next().unwrap_or(""))
                        .collect::<Vec<_>>()
                        .join(";");
                    options.script.extend(parse_script(&joined)?);
                }
                "--time" => {
                    options.time = Some(value()?.parse().map_err(|e| format!("--time: {e}"))?);
                }
                "--quality" => {
                    let name = value()?;
                    options.quality =
                        Some(Quality::from_name(&name).ok_or(format!("no quality '{name}'"))?);
                }
                "--fullscreen" => options.fullscreen = true,
                other if !other.starts_with('-') => options.scene = PathBuf::from(other),
                other => return Err(format!("unknown argument: {other}")),
            }
        }
        Ok(options)
    }

    fn load_scene(path: &Path) -> Result<LoadedScene, Failure> {
        let start = Instant::now();
        let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let scene = solstice_asset::file::decode(&bytes)?;
        log::info!(
            "loaded {} ({:.0} MB) in {:.2}s",
            path.display(),
            bytes.len() as f64 / 1.0e6,
            start.elapsed().as_secs_f32()
        );
        Ok(scene)
    }

    fn settings(options: &Options) -> RendererSettings {
        let mut settings = RendererSettings::default();
        if let Some(quality) = options.quality {
            settings.apply_quality(quality);
        }
        settings
    }

    fn start_game(
        scene: &LoadedScene,
        renderer: &mut Renderer,
        options: &Options,
    ) -> Result<Game, Failure> {
        let info = SceneInfo {
            gameplay: &scene.scene.gameplay,
            collision: scene.collision.as_ref(),
            skeletons: &scene.scene.skeletons,
            clips: &scene.scene.clips,
            poses: &scene.scene.poses,
            viewpoint: scene.scene.viewpoint,
        };
        let mut game = Game::new(&info, renderer)?;
        if let Some(hours) = options.time {
            game.set_time(hours);
        }
        Ok(game)
    }

    fn create_instance() -> wgpu::Instance {
        wgpu::Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::from_env().unwrap_or(wgpu::Backends::PRIMARY),
            ..wgpu::InstanceDescriptor::new_without_display_handle()
        })
    }

    pub fn run() -> Result<(), Failure> {
        env_logger::Builder::from_env(
            env_logger::Env::default().default_filter_or("info,wgpu_core=warn,wgpu_hal=warn"),
        )
        .init();
        let options = parse_args()?;
        let scene = load_scene(&options.scene)?;
        if options.capture.is_some() {
            return capture(&options, &scene);
        }
        let event_loop = EventLoop::new()?;
        let mut app = App {
            options,
            scene,
            state: None,
            input: Input::new(),
            captured_mouse: false,
        };
        event_loop.run_app(&mut app)?;
        Ok(())
    }

    /// Carries out one script command. Returns a picture to save, if it asked for one.
    fn script_command(command: &str, game: &mut Game, input: &mut Input) -> Option<PathBuf> {
        let words: Vec<&str> = command.split_whitespace().collect();
        let number = |index: usize| -> f32 {
            words
                .get(index)
                .and_then(|w| w.parse().ok())
                .unwrap_or(0.0)
        };
        match words.first().copied() {
            Some("key") => input.key(words.get(1).unwrap_or(&""), words.get(2) == Some(&"down")),
            Some("button") => {
                input.button(words.get(1).unwrap_or(&""), words.get(2) == Some(&"down"));
            }
            Some("mouse") => input.mouse_motion(number(1), number(2)),
            Some("shot") => return words.get(1).map(PathBuf::from),
            Some("time") => game.set_time(number(1)),
            Some(_) => {
                if !game.debug_command(command) {
                    log::warn!("script: unknown command '{command}'");
                }
            }
            None => {}
        }
        None
    }

    /// Runs the game headless for a number of frames, following the script, and saves pictures.
    fn capture(options: &Options, scene: &LoadedScene) -> Result<(), Failure> {
        let path = options.capture.as_ref().expect("capture mode");
        let gpu = pollster::block_on(Gpu::request(
            &create_instance(),
            None,
            wgpu::PowerPreference::HighPerformance,
        ))?;
        let errors: Arc<Mutex<Vec<String>>> = Default::default();
        let sink = errors.clone();
        gpu.device
            .on_uncaptured_error(Arc::new(move |error: wgpu::Error| {
                sink.lock().expect("error sink").push(error.to_string());
            }));
        let start = Instant::now();
        let mut renderer = Renderer::new(&gpu, scene, CAPTURE_FORMAT, settings(options));
        log::info!("renderer created in {:.2}s", start.elapsed().as_secs_f32());
        let mut game = start_game(scene, &mut renderer, options)?;
        let mut input = Input::new();

        let target = gpu.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("capture"),
            size: wgpu::Extent3d {
                width: options.size.0,
                height: options.size.1,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: CAPTURE_FORMAT,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC,
            view_formats: &[],
        });
        let view = target.create_view(&Default::default());
        const STEP: f32 = 1.0 / 60.0;
        let mut cpu_ms = 0.0f32;
        let start = Instant::now();
        for frame in 0..options.frames {
            let mut shots = Vec::new();
            for (at, command) in &options.script {
                if *at == frame {
                    shots.extend(script_command(command, &mut game, &mut input));
                }
            }
            let before = Instant::now();
            let frame_view = game.frame(&mut renderer, &mut input, STEP);
            cpu_ms += before.elapsed().as_secs_f32() * 1000.0;
            renderer.render(
                &gpu,
                &frame_view.camera,
                &frame_view.environment,
                &view,
                options.size,
                STEP,
            );
            gpu.device.poll(wgpu::PollType::wait_indefinitely())?;
            for shot in shots {
                save_png(&gpu, &target, options.size, &shot)?;
                println!("saved {}", shot.display());
            }
        }
        let frames = options.frames.max(1) as f32;
        save_png(&gpu, &target, options.size, path)?;
        let stats = renderer.stats();
        println!(
            "avg {:.2} ms a frame, game {:.3} ms | {} clusters, {} triangles of {} source, {} instances",
            start.elapsed().as_secs_f32() * 1000.0 / frames,
            cpu_ms / frames,
            stats.clusters,
            stats.triangles,
            stats.source_triangles,
            stats.instances,
        );
        if let Some(times) = renderer.section_times() {
            let parts: Vec<String> = solstice_render::profiler::SECTIONS
                .iter()
                .zip(times)
                .filter(|(_, ms)| *ms >= 0.01)
                .map(|(name, ms)| format!("{name} {ms:.2}"))
                .collect();
            println!(
                "gpu ms: {} | total {:.2}",
                parts.join(", "),
                times.iter().sum::<f32>()
            );
        }
        for line in game.debug_summary() {
            println!("{line}");
        }
        let errors = errors.lock().expect("error sink");
        if errors.is_empty() {
            println!("saved {} with no GPU errors", path.display());
            Ok(())
        } else {
            Err(format!("{} GPU errors, first:\n{}", errors.len(), errors[0]).into())
        }
    }

    fn read_pixels(gpu: &Gpu, texture: &wgpu::Texture, size: (u32, u32)) -> Result<Vec<u8>, Failure> {
        let row_bytes = size.0 * 4;
        let aligned = row_bytes.next_multiple_of(wgpu::COPY_BYTES_PER_ROW_ALIGNMENT);
        let staging = gpu.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("capture staging"),
            size: u64::from(aligned) * u64::from(size.1),
            usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });
        let mut encoder = gpu.device.create_command_encoder(&Default::default());
        encoder.copy_texture_to_buffer(
            texture.as_image_copy(),
            wgpu::TexelCopyBufferInfo {
                buffer: &staging,
                layout: wgpu::TexelCopyBufferLayout {
                    offset: 0,
                    bytes_per_row: Some(aligned),
                    rows_per_image: Some(size.1),
                },
            },
            wgpu::Extent3d {
                width: size.0,
                height: size.1,
                depth_or_array_layers: 1,
            },
        );
        gpu.queue.submit([encoder.finish()]);
        staging.slice(..).map_async(wgpu::MapMode::Read, |result| {
            result.expect("mapping the capture buffer failed");
        });
        gpu.device.poll(wgpu::PollType::wait_indefinitely())?;
        let data = staging.slice(..).get_mapped_range()?;
        let mut pixels = Vec::with_capacity((row_bytes * size.1) as usize);
        for row in data.chunks_exact(aligned as usize) {
            pixels.extend_from_slice(&row[..row_bytes as usize]);
        }
        drop(data);
        Ok(pixels)
    }

    fn save_png(
        gpu: &Gpu,
        texture: &wgpu::Texture,
        size: (u32, u32),
        path: &Path,
    ) -> Result<(), Failure> {
        let pixels = read_pixels(gpu, texture, size)?;
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                std::fs::create_dir_all(parent)?;
            }
        }
        let file = std::io::BufWriter::new(std::fs::File::create(path)?);
        let mut encoder = png::Encoder::new(file, size.0, size.1);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        encoder.write_header()?.write_image_data(&pixels)?;
        Ok(())
    }

    struct WindowState {
        window: Arc<Window>,
        surface: wgpu::Surface<'static>,
        config: wgpu::SurfaceConfiguration,
        gpu: Gpu,
        renderer: Renderer,
        game: Game,
        last_frame: Instant,
        title_timer: f32,
        frames_since_title: u32,
    }

    struct App {
        options: Options,
        scene: LoadedScene,
        state: Option<WindowState>,
        input: Input,
        captured_mouse: bool,
    }

    impl App {
        fn create_state(&self, event_loop: &ActiveEventLoop) -> Result<WindowState, Failure> {
            let mut attributes = Window::default_attributes()
                .with_title("HOLDOUT")
                .with_inner_size(PhysicalSize::new(self.options.size.0, self.options.size.1));
            if self.options.fullscreen {
                attributes = attributes.with_fullscreen(Some(Fullscreen::Borderless(None)));
            }
            let window = Arc::new(event_loop.create_window(attributes)?);
            let instance = create_instance();
            let surface = instance.create_surface(window.clone())?;
            let gpu = pollster::block_on(Gpu::request(
                &instance,
                Some(&surface),
                wgpu::PowerPreference::HighPerformance,
            ))?;
            let size = window.inner_size();
            let mut config = surface
                .get_default_config(&gpu.adapter, size.width.max(1), size.height.max(1))
                .ok_or("this surface cannot be presented to")?;
            config.format = config.format.remove_srgb_suffix();
            config.present_mode = wgpu::PresentMode::AutoVsync;
            surface.configure(&gpu.device, &config);
            let mut renderer =
                Renderer::new(&gpu, &self.scene, config.format, settings(&self.options));
            let game = start_game(&self.scene, &mut renderer, &self.options)?;
            Ok(WindowState {
                window,
                surface,
                config,
                gpu,
                renderer,
                game,
                last_frame: Instant::now(),
                title_timer: 0.0,
                frames_since_title: 0,
            })
        }

        fn draw(&mut self) {
            let Some(state) = self.state.as_mut() else {
                return;
            };
            let now = Instant::now();
            let delta = (now - state.last_frame).as_secs_f32();
            state.last_frame = now;
            let view = state.game.frame(&mut state.renderer, &mut self.input, delta);

            state.title_timer += delta;
            state.frames_since_title += 1;
            if state.title_timer > 0.5 {
                let stats = state.renderer.stats();
                state.window.set_title(&format!(
                    "HOLDOUT | {:.0} fps | {:.2}M tris",
                    state.frames_since_title as f32 / state.title_timer,
                    stats.triangles as f32 / 1.0e6,
                ));
                state.title_timer = 0.0;
                state.frames_since_title = 0;
            }

            let texture = match state.surface.get_current_texture() {
                wgpu::CurrentSurfaceTexture::Success(texture)
                | wgpu::CurrentSurfaceTexture::Suboptimal(texture) => texture,
                wgpu::CurrentSurfaceTexture::Outdated | wgpu::CurrentSurfaceTexture::Lost => {
                    state.surface.configure(&state.gpu.device, &state.config);
                    return;
                }
                _ => return,
            };
            let target = texture.texture.create_view(&Default::default());
            state.renderer.render(
                &state.gpu,
                &view.camera,
                &view.environment,
                &target,
                (state.config.width, state.config.height),
                delta,
            );
            state.gpu.queue.present(texture);
        }

        fn set_mouse_capture(&mut self, capture: bool) {
            let Some(state) = &self.state else { return };
            let mode = if capture {
                CursorGrabMode::Locked
            } else {
                CursorGrabMode::None
            };
            if state.window.set_cursor_grab(mode).is_err() && capture {
                let _ = state.window.set_cursor_grab(CursorGrabMode::Confined);
            }
            state.window.set_cursor_visible(!capture);
            self.captured_mouse = capture;
        }
    }

    impl ApplicationHandler for App {
        fn resumed(&mut self, event_loop: &ActiveEventLoop) {
            if self.state.is_some() {
                return;
            }
            match self.create_state(event_loop) {
                Ok(state) => self.state = Some(state),
                Err(error) => {
                    log::error!("{error}");
                    event_loop.exit();
                }
            }
        }

        fn window_event(&mut self, event_loop: &ActiveEventLoop, _: WindowId, event: WindowEvent) {
            match event {
                WindowEvent::CloseRequested => event_loop.exit(),
                WindowEvent::Resized(size) => {
                    if let Some(state) = self.state.as_mut() {
                        if size.width > 0 && size.height > 0 {
                            state.config.width = size.width;
                            state.config.height = size.height;
                            state.surface.configure(&state.gpu.device, &state.config);
                        }
                    }
                }
                WindowEvent::KeyboardInput { event, .. } => {
                    if let PhysicalKey::Code(code) = event.physical_key {
                        let down = event.state == ElementState::Pressed;
                        if down && code == KeyCode::Escape && self.captured_mouse {
                            self.set_mouse_capture(false);
                        }
                        if !event.repeat {
                            // winit's key names are the browser's `KeyboardEvent.code` names.
                            self.input.key(&format!("{code:?}"), down);
                        }
                    }
                }
                WindowEvent::MouseInput { state, button, .. } => {
                    let name = match button {
                        MouseButton::Left => Some("left"),
                        MouseButton::Right => Some("right"),
                        MouseButton::Middle => Some("middle"),
                        _ => None,
                    };
                    let down = state == ElementState::Pressed;
                    // The click that captures the mouse is not a shot.
                    if let (Some(name), true) = (name, self.captured_mouse) {
                        self.input.button(name, down);
                    } else if down && button == MouseButton::Left {
                        self.set_mouse_capture(true);
                    }
                }
                WindowEvent::MouseWheel { delta, .. } => {
                    self.input.wheel += match delta {
                        winit::event::MouseScrollDelta::LineDelta(_, y) => y,
                        winit::event::MouseScrollDelta::PixelDelta(p) => p.y as f32 / 40.0,
                    };
                }
                WindowEvent::Focused(false) => {
                    self.input.release_all();
                    self.set_mouse_capture(false);
                }
                WindowEvent::RedrawRequested => {
                    self.draw();
                    if let Some(state) = &self.state {
                        state.window.request_redraw();
                    }
                }
                _ => {}
            }
        }

        fn device_event(&mut self, _: &ActiveEventLoop, _: DeviceId, event: DeviceEvent) {
            if let (DeviceEvent::MouseMotion { delta }, true) = (event, self.captured_mouse) {
                self.input.mouse_motion(delta.0 as f32, delta.1 as f32);
            }
        }
    }
}
