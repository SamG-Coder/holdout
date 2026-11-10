// HOLDOUT in the browser: loads the scene and the game, feeds it the keys and the mouse, draws
// the interface over its picture, and plays what it says should be heard.

import init, { WebGame, header_bytes, read_header } from "./pkg/holdout.js";
import { Sound } from "./audio.js";

const params = new URLSearchParams(location.search);
const el = (id) => document.getElementById(id);
const canvas = el("view");
const sceneUrl = params.get("scene") ?? "assets/level.solstice";
const megabytes = (name, fallback) => (Number(params.get(name)) || fallback) * 1048576;

function fail(text) {
  el("error").hidden = false;
  el("error").textContent = text;
  el("loading").hidden = true;
}

function progress(share, text) {
  el("loading-fill").style.width = `${Math.round(share * 100)}%`;
  if (text) el("loading-text").textContent = text;
}

/// Reads parts of the scene by HTTP Range. The scene is one file or, where a host will not
/// take a file so large, that file cut into equal parts with a note beside it
/// (`NAME.parts.json`: the whole size, the size of a part, how many). A server that doesn't do
/// ranges sends a whole file once, and what is asked of it is then cut from memory.
class SceneFile {
  #url;
  #parts = null;
  #wholes = new Map();

  static async open(url) {
    const file = new SceneFile();
    file.#url = url;
    try {
      const note = await fetch(`${url}.parts.json`);
      if (note.ok) file.#parts = await note.json();
    } catch {
      // No note: the scene is one file.
    }
    return file;
  }

  async read(start, end) {
    if (!this.#parts) return this.#readFrom(this.#url, start, end);
    const size = this.#parts.part;
    const first = Math.floor(start / size);
    const last = Math.floor((end - 1) / size);
    const name = (index) => `${this.#url}.${String(index).padStart(3, "0")}`;
    if (first === last) return this.#readFrom(name(first), start - first * size, end - first * size);
    // Across the join of two parts or more: read from each, and put them end to end.
    const pieces = await Promise.all(Array.from({ length: last - first + 1 }, (_, i) => {
      const index = first + i;
      return this.#readFrom(name(index), Math.max(start - index * size, 0), Math.min(end - index * size, size));
    }));
    const out = new Uint8Array(end - start);
    let offset = 0;
    for (const piece of pieces) {
      out.set(piece, offset);
      offset += piece.length;
    }
    return out;
  }

  async #readFrom(url, start, end) {
    const whole = this.#wholes.get(url);
    if (whole) return whole.subarray(start, end);
    const response = await fetch(url, { headers: { Range: `bytes=${start}-${end - 1}` } });
    if (!response.ok) throw new Error(`Could not load ${url} (HTTP ${response.status}).`);
    if (response.status === 200) {
      const total = Number(response.headers.get("content-length")) || 0;
      const reader = response.body.getReader();
      const chunks = [];
      let received = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.length;
        if (total) progress(0.05 + 0.5 * received / total, `Downloading Alder Ridge… ${(received / 1e6).toFixed(0)} MB`);
      }
      const all = new Uint8Array(received);
      let offset = 0;
      for (const chunk of chunks) {
        all.set(chunk, offset);
        offset += chunk.length;
      }
      this.#wholes.set(url, all);
      return all.subarray(start, end);
    }
    return new Uint8Array(await response.arrayBuffer());
  }
}

async function inflate(bytes) {
  const unpacked = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(unpacked).arrayBuffer());
}

/// Unpacks a block that should come to `limit` bytes, and refuses to unpack more.
async function inflateAtMost(bytes, limit) {
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw")).getReader();
  const out = new Uint8Array(limit);
  let filled = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (filled + value.length > limit) {
      await reader.cancel();
      throw new Error("a part of the scene unpacks larger than it says");
    }
    out.set(value, filled);
    filled += value.length;
  }
  return out.subarray(0, filled);
}

/// Fetches the parts of the scene the renderer asks for as the view needs them.
class Streamer {
  static MAX_FETCHING = 48;
  static MERGE_GAP = 256 * 1024;
  static MERGE_MOST = 8 * 1048576;
  #game;
  #file;

  constructor(game, file) {
    this.#game = game;
    this.#file = file;
  }

  pump() {
    const flat = this.#game.stream_requests(Streamer.MAX_FETCHING);
    const requests = [];
    for (let i = 0; i < flat.length; i += 4) {
      requests.push({ id: flat[i], start: flat[i + 1], end: flat[i + 2], deflated: flat[i + 3] !== 0 });
    }
    requests.sort((a, b) => a.start - b.start);
    // Requests for parts that lie close together in the file share one fetch.
    let run = [];
    for (const request of requests) {
      const last = run[run.length - 1];
      if (last && (request.start - last.end > Streamer.MERGE_GAP || request.end - run[0].start > Streamer.MERGE_MOST)) {
        this.#fetchRun(run);
        run = [];
      }
      run.push(request);
    }
    if (run.length > 0) this.#fetchRun(run);
  }

  async #fetchRun(run) {
    const start = run[0].start;
    let stored;
    try {
      stored = await this.#file.read(start, run[run.length - 1].end);
    } catch (error) {
      for (const request of run) setTimeout(() => this.#game.request_failed(request.id), 1000);
      return;
    }
    // Unpack the whole run at once: one after another, a long run holds its last pages back
    // so long that the renderer has given up on them.
    await Promise.all(run.map(async (request) => {
      const part = stored.subarray(request.start - start, request.end - start);
      try {
        this.#game.deliver(request.id, request.deflated ? await inflate(part) : part);
      } catch (error) {
        setTimeout(() => this.#game.request_failed(request.id), 1000);
      }
    }));
  }
}

const canvasSize = () => {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  return [Math.max(1, Math.round(canvas.clientWidth * ratio)), Math.max(1, Math.round(canvas.clientHeight * ratio))];
};

// ------------------------------------------------------------------------------ Settings

const settings = {
  sensitivity: 1, invert: false, quality: "high", scale: 1, volume: 0.8, music: 0.6,
  ...JSON.parse(localStorage.getItem("holdout-settings") ?? "{}"),
};

function applySettings(game, sound) {
  game?.set_look(0.0022 * settings.sensitivity, settings.invert);
  game?.set_quality(settings.quality);
  game?.set_render_scale(settings.scale);
  sound?.setVolumes(settings.volume, settings.music);
  localStorage.setItem("holdout-settings", JSON.stringify(settings));
}

function bindSettings(game, sound) {
  const bind = (id, key, read = Number) => {
    const input = el(id);
    const show = () => {
      const output = input.parentElement.querySelector("output");
      if (output) output.textContent = input.type === "range" ? Number(input.value).toFixed(2) : "";
    };
    if (input.type === "checkbox") input.checked = settings[key];
    else input.value = settings[key];
    show();
    input.addEventListener("input", () => {
      settings[key] = input.type === "checkbox" ? input.checked : read(input.value);
      show();
      applySettings(game, sound);
    });
  };
  bind("sensitivity", "sensitivity");
  bind("invert", "invert");
  bind("quality", "quality", String);
  bind("scale", "scale");
  bind("volume", "volume");
  bind("music", "music");
}

// ------------------------------------------------------------------------------ The interface

const compassStrip = el("compass-strip");
const COMPASS_VH_PER_DEGREE = 0.4;
{
  const names = { 0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW" };
  // Twice round, so that the strip can slide past north without a gap.
  for (let degrees = -360; degrees <= 720; degrees += 15) {
    const mark = document.createElement("span");
    const wrapped = ((degrees % 360) + 360) % 360;
    mark.textContent = names[wrapped] ?? String(wrapped);
    if (names[wrapped]) mark.className = "major";
    mark.style.left = `${degrees * COMPASS_VH_PER_DEGREE}vh`;
    compassStrip.appendChild(mark);
  }
}

let lastObjective = "";
let lastLine = "";
const friendMarks = [];

function showHud(hud) {
  el("vignette").style.opacity = Math.min(1, hud.flash * 0.9 + Math.max(0, (45 - hud.hp) / 45) * 0.75);
  const arc = el("hurt-arc");
  arc.style.opacity = Math.min(1, hud.flash * 1.6);
  arc.style.transform = `rotate(${hud.hurtAngle}deg)`;

  compassStrip.style.transform = `translateX(${-hud.compass * COMPASS_VH_PER_DEGREE}vh)`;

  if (hud.objective !== lastObjective) {
    lastObjective = hud.objective;
    el("objective-text").textContent = hud.objective;
    const box = el("objective");
    box.style.opacity = hud.objective ? 1 : 0;
    box.classList.remove("changed");
    void box.offsetWidth;
    box.classList.add("changed");
  }

  // The crosshair opens with the weapon's spread and goes when the sights come up.
  const gap = Math.max(0.55, hud.spread * 100);
  const cross = el("crosshair");
  cross.style.opacity = hud.ready ? Math.max(0, 1 - hud.aim * 2.5) : 0;
  cross.querySelector(".up").style.top = `${-gap - 0.95}vh`;
  cross.querySelector(".down").style.top = `${gap}vh`;
  cross.querySelector(".left").style.left = `${-gap - 0.95}vh`;
  cross.querySelector(".right").style.left = `${gap}vh`;
  cross.querySelector(".dot").style.opacity = hud.aim > 0.5 ? 0 : 0.7;

  const marker = el("hit-marker");
  marker.style.opacity = Math.min(1, hud.hit);
  marker.classList.toggle("kill", hud.hit > 1);

  const goal = el("goal");
  goal.hidden = !hud.goal;
  if (hud.goal) {
    goal.style.left = `${hud.goal[0] * 100}%`;
    goal.style.top = `${hud.goal[1] * 100}%`;
    el("goal-distance").textContent = `${Math.round(hud.goal[2])} M`;
    goal.style.opacity = hud.goal[2] < 4 ? 0.25 : 1;
  }

  const friends = el("friends");
  while (friendMarks.length < hud.friends.length) {
    const mark = document.createElement("i");
    friends.appendChild(mark);
    friendMarks.push(mark);
  }
  friendMarks.forEach((mark, index) => {
    const friend = hud.friends[index];
    mark.hidden = !friend;
    if (friend) {
      mark.style.left = `${friend[0] * 100}%`;
      mark.style.top = `${friend[1] * 100}%`;
      mark.style.opacity = friend[2] < 2.5 ? 0.3 : 0.9;
    }
  });

  const prompt = el("prompt");
  prompt.hidden = !hud.prompt;
  if (hud.prompt) {
    el("prompt-text").textContent = hud.prompt;
    el("prompt-ring").style.strokeDashoffset = 119.4 * (1 - (hud.progress ?? 0));
  }

  const subtitle = el("subtitle");
  const line = hud.line ? `${hud.line[0]}|${hud.line[1]}` : "";
  if (line !== lastLine) {
    lastLine = line;
    subtitle.hidden = !hud.line;
    if (hud.line) {
      el("subtitle-speaker").textContent = hud.line[0];
      el("subtitle-text").textContent = hud.line[1];
    }
  }

  const fill = el("health-fill");
  fill.style.width = `${Math.max(0, hud.hp)}%`;
  fill.classList.toggle("low", hud.hp < 40);

  const rounds = el("ammo-rounds");
  rounds.textContent = hud.ammo;
  rounds.classList.toggle("low", hud.ammo <= hud.mag * 0.2);
  el("ammo-reserve").textContent = `/ ${hud.reserve}`;
  el("weapon-name").textContent = hud.weapon;
  const grenades = el("grenades");
  if (grenades.childElementCount !== hud.grenades) {
    grenades.replaceChildren(...Array.from({ length: hud.grenades }, () => document.createElement("i")));
  }
  el("arms-hint").textContent = hud.reloading ? "RELOADING"
    : hud.ammo === 0 ? (hud.reserve ? "PRESS R TO RELOAD" : "OUT OF AMMUNITION")
    : hud.picked ? `+${hud.picked} ROUNDS` : "";
}

// ------------------------------------------------------------------------------ Starting up

async function main() {
  if (!navigator.gpu) {
    fail("This browser has no WebGPU. HOLDOUT needs a recent Chrome or Edge on a desktop GPU.");
    return;
  }
  if (!(await navigator.gpu.requestAdapter())) {
    fail("WebGPU is here, but not for this GPU or driver. Try updating your graphics driver.");
    return;
  }
  progress(0.02, "Starting the engine…");
  await init();

  progress(0.05, "Reading Alder Ridge…");
  const file = await SceneFile.open(sceneUrl);
  const [manifestOffset, manifestBytes] = read_header(await file.read(0, header_bytes()));
  const manifest = await inflate(await file.read(manifestOffset, manifestOffset + manifestBytes));

  progress(0.6, "Preparing the GPU…");
  [canvas.width, canvas.height] = canvasSize();
  const game = await WebGame.create(
    canvas,
    manifest,
    manifestOffset + manifestBytes,
    megabytes("geometry-mb", 512),
    megabytes("texture-mb", 768),
  );
  const streamer = new Streamer(game, file);
  const sound = new Sound();
  applySettings(game, null);
  bindSettings(game, sound);

  // The picture starts at once, with what has arrived, while the rest loads behind the title.
  let last = performance.now();
  let playing = false;
  let screen = "title";
  let frames = 0;
  let fpsSince = last;
  const showFps = params.has("fps");
  el("fps").hidden = !showFps;

  const screens = ["title", "pause", "settings", "controls", "dead", "complete"];
  let underneath = "title";
  function show(name) {
    if (name === "settings" || name === "controls") underneath = screen;
    screen = name;
    for (const id of screens) el(id).hidden = id !== name;
    el("hud").hidden = name !== null;
    game.set_paused(name !== null && name !== "dead" && name !== "complete");
    sound.setMenu(name === "title" || name === "pause" || name === "settings" || name === "controls");
  }

  function capture() {
    // Raw movement where the browser has it, plain lock where not; some hosts allow neither.
    canvas.requestPointerLock?.({ unadjustedMovement: true })?.catch?.(() =>
      Promise.resolve(canvas.requestPointerLock?.()).catch(() => {}));
  }

  function resume() {
    show(null);
    capture();
    sound.resume();
  }

  for (const button of document.querySelectorAll("[data-open]")) {
    button.addEventListener("click", () => show(button.dataset.open));
  }
  for (const button of document.querySelectorAll("[data-close]")) {
    button.addEventListener("click", () => show(underneath));
  }
  el("play").addEventListener("click", () => {
    // The first time, the place and the hour come up over the opening view, and go.
    if (!playing) el("location").classList.add("shown");
    playing = true;
    sound.start();
    resume();
  });
  el("resume").addEventListener("click", resume);
  const retry = () => {
    game.restart();
    resume();
  };
  el("restart-checkpoint").addEventListener("click", retry);
  el("retry").addEventListener("click", retry);
  el("again").addEventListener("click", () => location.reload());

  document.addEventListener("pointerlockchange", () => {
    if (document.pointerLockElement !== canvas && playing && screen === null) {
      game.release_all();
      show("pause");
    }
  });
  canvas.addEventListener("click", () => {
    if (playing && screen === null && document.pointerLockElement !== canvas) capture();
  });

  const buttons = ["left", "middle", "right"];
  window.addEventListener("keydown", (event) => {
    if (event.code === "Escape" && playing && (screen === "pause")) {
      resume();
      return;
    }
    if (screen !== null) return;
    if (!event.repeat) game.key(event.code, true);
    if (["Space", "Tab", "ArrowUp", "ArrowDown", "F2"].includes(event.code) || event.ctrlKey) event.preventDefault();
  });
  window.addEventListener("keyup", (event) => game.key(event.code, false));
  canvas.addEventListener("mousedown", (event) => {
    if (document.pointerLockElement === canvas) game.mouse_button(buttons[event.button] ?? "", true);
  });
  window.addEventListener("mouseup", (event) => game.mouse_button(buttons[event.button] ?? "", false));
  window.addEventListener("mousemove", (event) => {
    if (document.pointerLockElement === canvas) game.mouse_motion(event.movementX, event.movementY);
  });
  window.addEventListener("wheel", (event) => {
    if (document.pointerLockElement === canvas) game.wheel(-Math.sign(event.deltaY));
  }, { passive: true });
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  window.addEventListener("blur", () => game.release_all());

  function tick(now) {
    const seconds = Math.min((now - last) / 1000, 0.1);
    last = now;
    const [width, height] = canvasSize();
    if (width !== canvas.width || height !== canvas.height) {
      canvas.width = width;
      canvas.height = height;
      game.resize(width, height);
    }
    game.frame(seconds);
    streamer.pump();
    if (game.started()) {
      const text = game.hud();
      if (text) {
        const hud = JSON.parse(text);
        if (screen === null) {
          showHud(hud);
          if (hud.state === "dead" && hud.ended > 2.2) {
            document.exitPointerLock?.();
            show("dead");
          } else if (hud.state === "complete" && hud.ended > 1.5) {
            const [shots, hits, kills, heads, deaths, seconds] = hud.tally ?? [0, 0, 0, 0, 0, 0];
            el("tally-time").textContent = `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
            el("tally-kills").textContent = kills;
            el("tally-accuracy").textContent = shots ? `${Math.round(100 * hits / shots)}%` : "—";
            el("tally-heads").textContent = heads;
            el("tally-deaths").textContent = deaths;
            document.exitPointerLock?.();
            show("complete");
          }
        }
      }
      sound.play(game.take_sounds(), game.listener(), seconds);
    }
    if (showFps && ++frames >= 30) {
      el("fps").textContent = `${(frames * 1000 / (now - fpsSince)).toFixed(0)} fps · ${game.gpu_error_count()} GPU errors`;
      frames = 0;
      fpsSince = now;
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  // What the game collides with comes next, and then the game itself can start.
  progress(0.7, "Loading the streets…");
  const ranges = game.collision_ranges();
  const sizes = game.collision_sizes();
  const parts = [];
  for (let i = 0; i < ranges.length; i += 2) {
    parts.push(file.read(ranges[i], ranges[i + 1]).then((part) => inflateAtMost(part, sizes[i / 2])));
  }
  for (const part of await Promise.all(parts)) game.deliver_collision(part);
  progress(0.85, "Briefing the cell…");
  // A frame's pause, so that the words above are seen before the work that follows.
  await new Promise((resolve) => setTimeout(resolve, 60));
  game.begin();
  game.set_paused(true);
  applySettings(game, sound);
  // The opening view streams in behind the title: wait until it has stopped arriving.
  progress(0.9, "Bringing the street into focus…");
  for (let quiet = 0, before = -1, waited = 0; quiet < 12 && waited < 260; waited++) {
    await new Promise((resolve) => setTimeout(resolve, 50));
    const [installed] = game.pages();
    quiet = installed === before ? quiet + 1 : 0;
    before = installed;
  }
  progress(1, "Ready");
  el("loading").hidden = true;
  el("title-menu").hidden = false;
  window.holdout = game;
  if (params.has("autostart")) {
    playing = true;
    show(null);
  }
}

main().catch((error) => {
  console.error(error);
  fail(String(error?.message ?? error));
});
