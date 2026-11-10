// Everything HOLDOUT sounds like, made here: there is not a recording in the game. Each sound
// is built from noise, sine sweeps and filters when the game starts, a few variations of each
// so that repeats don't sound stamped out, and placed in the world by the browser's 3D audio.

const RATE = 44100;

function random(seed) {
  let s = (seed >>> 0) || 1;
  return () => {
    s ^= s << 13; s >>>= 0;
    s ^= s >>> 17;
    s ^= s << 5; s >>>= 0;
    return s / 4294967296;
  };
}

const samples = (seconds) => Math.ceil(seconds * RATE);

function noise(seconds, seed) {
  const next = random(seed);
  const out = new Float32Array(samples(seconds));
  for (let i = 0; i < out.length; i++) out[i] = next() * 2 - 1;
  return out;
}

/// A second-order filter over a whole sound: `kind` is lowpass, highpass or bandpass. The
/// frequency may be a number or a function of time in seconds.
function filter(data, kind, frequency, q = 0.707) {
  const out = new Float32Array(data.length);
  let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  let b0 = 0, b1 = 0, b2 = 0, a1 = 0, a2 = 0;
  const set = (f) => {
    const w = 2 * Math.PI * Math.min(Math.max(f, 10), RATE * 0.45) / RATE;
    const alpha = Math.sin(w) / (2 * q);
    const cos = Math.cos(w);
    const a0 = 1 + alpha;
    if (kind === "lowpass") { b0 = (1 - cos) / 2; b1 = 1 - cos; b2 = b0; }
    else if (kind === "highpass") { b0 = (1 + cos) / 2; b1 = -(1 + cos); b2 = b0; }
    else { b0 = alpha; b1 = 0; b2 = -alpha; }
    b0 /= a0; b1 /= a0; b2 /= a0; a1 = -2 * cos / a0; a2 = (1 - alpha) / a0;
  };
  const moving = typeof frequency === "function";
  if (!moving) set(frequency);
  for (let i = 0; i < data.length; i++) {
    if (moving && (i & 31) === 0) set(frequency(i / RATE));
    const x = data[i];
    const y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
    x2 = x1; x1 = x; y2 = y1; y1 = y;
    out[i] = y;
  }
  return out;
}

/// Shapes a sound's loudness over time: `shape(t)` in seconds.
function shaped(data, shape) {
  const out = new Float32Array(data.length);
  for (let i = 0; i < data.length; i++) out[i] = data[i] * shape(i / RATE);
  return out;
}

const decay = (time, attack = 0.0005) => (t) => (t < attack ? t / attack : Math.exp(-(t - attack) / time));

/// A sine whose pitch runs from one frequency to another, exponentially, over `time` seconds.
function sweep(seconds, from, to, time) {
  const out = new Float32Array(samples(seconds));
  let phase = 0;
  for (let i = 0; i < out.length; i++) {
    const t = i / RATE;
    const f = to + (from - to) * Math.exp(-t / time);
    phase += 2 * Math.PI * f / RATE;
    out[i] = Math.sin(phase);
  }
  return out;
}

function mix(seconds, layers) {
  const out = new Float32Array(samples(seconds));
  for (const [data, gain, at = 0] of layers) {
    const start = Math.round(at * RATE);
    const count = Math.min(data.length, out.length - start);
    for (let i = 0; i < count; i++) out[start + i] += data[i] * gain;
  }
  return out;
}

/// Drives a sound into soft clipping, as loud things overload the ear and the air, then sets
/// its peak.
function finish(data, drive = 1, peak = 0.9) {
  let top = 1e-6;
  for (let i = 0; i < data.length; i++) {
    data[i] = Math.tanh(data[i] * drive);
    top = Math.max(top, Math.abs(data[i]));
  }
  // The last few milliseconds fade, so that nothing ends with a click.
  const fade = Math.min(samples(0.01), data.length);
  for (let i = 0; i < fade; i++) data[data.length - 1 - i] *= i / fade;
  for (let i = 0; i < data.length; i++) data[i] *= peak / top;
  return data;
}

// ---------------------------------------------------------------------------- The sounds

function gunshot(seed, near) {
  const crack = shaped(filter(noise(0.08, seed), "highpass", 1400), decay(near ? 0.011 : 0.007));
  const body = shaped(filter(noise(0.4, seed + 1), "lowpass", near ? 1100 : 700), decay(0.065));
  const thump = shaped(sweep(0.3, 170, 44, 0.035), decay(0.07));
  const snap = shaped(filter(noise(0.03, seed + 2), "bandpass", 3300, 2), decay(0.006));
  const tail = shaped(filter(noise(1.4, seed + 3), "bandpass", 620, 0.6), decay(near ? 0.28 : 0.42, 0.02));
  const slap = shaped(filter(noise(0.5, seed + 4), "lowpass", 1500), decay(0.06));
  const layers = [
    [crack, near ? 1.1 : 0.5], [body, 1.3], [thump, near ? 1.25 : 0.9], [snap, near ? 0.3 : 0.0, 0.017],
    [tail, near ? 0.2 : 0.42, 0.01], [slap, 0.2, 0.11], [slap, 0.11, 0.24],
  ];
  const out = mix(1.5, layers);
  return finish(near ? out : filter(out, "lowpass", 4200), near ? 2.6 : 1.8);
}

/// A 9 mm from a short barrel: sharper and shorter than a rifle, with less under it.
function pistolShot(seed) {
  const crack = shaped(filter(noise(0.06, seed), "highpass", 1900), decay(0.008));
  const body = shaped(filter(noise(0.3, seed + 1), "lowpass", 1500), decay(0.04));
  const thump = shaped(sweep(0.2, 210, 70, 0.025), decay(0.045));
  const snap = shaped(filter(noise(0.03, seed + 2), "bandpass", 4200, 2), decay(0.005));
  const tail = shaped(filter(noise(0.9, seed + 3), "bandpass", 900, 0.6), decay(0.18, 0.02));
  const slide = shaped(filter(noise(0.05, seed + 4), "bandpass", 2600, 3), decay(0.012));
  const out = mix(1.0, [[crack, 1.1], [body, 1.1], [thump, 0.8], [snap, 0.3, 0.012], [tail, 0.16, 0.01],
    [slide, 0.25, 0.05]]);
  return finish(out, 2.4);
}

function impact(seed, kind) {
  const hit = shaped(filter(noise(0.2, seed), "bandpass", { concrete: 2100, metal: 3800, wood: 900, dirt: 380, glass: 5200, flesh: 300 }[kind], 0.8),
    decay({ concrete: 0.03, metal: 0.02, wood: 0.035, dirt: 0.05, glass: 0.02, flesh: 0.045 }[kind]));
  const layers = [[hit, 1]];
  const next = random(seed + 9);
  if (kind === "metal") {
    // A ring of a few partials, as a struck plate gives.
    for (const partial of [1730, 2890, 4410, 6120]) {
      const tone = shaped(sweep(0.5, partial * (0.96 + next() * 0.08), partial, 0.2), decay(0.06 + next() * 0.1));
      layers.push([tone, 0.3]);
    }
  } else if (kind === "glass") {
    for (let i = 0; i < 7; i++) {
      const tone = shaped(sweep(0.25, 3000 + next() * 5000, 3000 + next() * 5000, 0.1), decay(0.03 + next() * 0.05));
      layers.push([tone, 0.25, next() * 0.12]);
    }
  } else if (kind === "wood") {
    layers.push([shaped(sweep(0.2, 320, 180, 0.03), decay(0.035)), 0.9]);
  } else if (kind === "dirt" || kind === "flesh") {
    layers.push([shaped(sweep(0.2, 140, 60, 0.03), decay(0.05)), 0.9]);
    if (kind === "flesh") layers.push([shaped(filter(noise(0.15, seed + 3), "bandpass", 1800, 1.5), decay(0.02)), 0.35, 0.01]);
  } else {
    // Stone: grit scattering after the strike.
    layers.push([shaped(filter(noise(0.35, seed + 2), "highpass", 2600), decay(0.09, 0.02)), 0.25, 0.02]);
  }
  return finish(mix(0.6, layers), 1.4);
}

function footstep(seed, kind) {
  const tone = { concrete: 950, dirt: 320, wood: 520, metal: 1400 }[kind];
  const heel = shaped(filter(noise(0.12, seed), "bandpass", tone * 0.6, 1), decay(0.018));
  const toe = shaped(filter(noise(0.12, seed + 1), "bandpass", tone, 0.9), decay(0.025));
  const thud = shaped(sweep(0.12, 110, 55, 0.02), decay(0.03));
  const layers = [[heel, 1], [toe, 0.7, 0.05], [thud, kind === "wood" ? 1.1 : 0.6]];
  if (kind === "dirt") layers.push([shaped(filter(noise(0.2, seed + 2), "highpass", 3000), decay(0.05, 0.01)), 0.25, 0.02]);
  if (kind === "metal") layers.push([shaped(sweep(0.3, 610, 600, 0.1), decay(0.07)), 0.35]);
  return finish(mix(0.3, layers), 1.2, 0.7);
}

/// A dry mechanical sound: a click, a clack, a slide.
function mechanism(seed, hits) {
  const layers = [];
  for (const [at, tone, length, gain] of hits) {
    layers.push([shaped(filter(noise(0.1, seed + layers.length), "bandpass", tone, 2.2), decay(length)), gain, at]);
    layers.push([shaped(sweep(0.08, tone * 0.5, tone * 0.45, 0.02), decay(length * 0.7)), gain * 0.4, at]);
  }
  const last = Math.max(...hits.map((hit) => hit[0])) + 0.25;
  return finish(mix(last, layers), 1.5, 0.75);
}

function whiz(seed) {
  const air = shaped(filter(noise(0.3, seed), "bandpass", (t) => 5200 * Math.exp(-t / 0.07) + 700, 3),
    (t) => Math.exp(-((t - 0.05) ** 2) / 0.0012));
  const crack = shaped(filter(noise(0.03, seed + 1), "highpass", 3000), decay(0.004));
  return finish(mix(0.32, [[air, 1], [crack, 0.6, 0.045]]), 1.3, 0.8);
}

function casing(seed) {
  const next = random(seed);
  const layers = [];
  let at = 0;
  for (let bounce = 0; bounce < 3; bounce++) {
    for (const partial of [4100, 6300, 8800]) {
      layers.push([shaped(sweep(0.12, partial * (0.97 + next() * 0.06), partial, 0.05), decay(0.012 + next() * 0.01)), 0.4 / (bounce + 1), at]);
    }
    at += 0.07 + next() * 0.05;
  }
  return finish(mix(0.4, layers), 1, 0.5);
}

function explosion(seed) {
  const blast = shaped(filter(noise(0.6, seed), "lowpass", (t) => 5000 * Math.exp(-t / 0.08) + 300), decay(0.12));
  const boom = shaped(sweep(1.6, 95, 26, 0.25), decay(0.5));
  const rumble = shaped(filter(noise(3.5, seed + 1), "lowpass", 160), decay(1.1, 0.05));
  const debris = shaped(filter(noise(2.5, seed + 2), "highpass", 1800), (t) => (t < 0.25 ? 0 : Math.exp(-(t - 0.25) / 0.5)) * (0.5 + 0.5 * Math.sin(t * 90)));
  const echo = shaped(filter(noise(1.2, seed + 3), "lowpass", 700), decay(0.3));
  return finish(mix(3.6, [[blast, 1.6], [boom, 1.5], [rumble, 0.9], [debris, 0.16], [echo, 0.35, 0.33], [echo, 0.2, 0.71]]), 3.2);
}

/// Speech with the words taken out: a voice's buzz through moving mouth shapes, squeezed
/// through a radio. What the Directorate's masked soldiers sound like to those they hunt.
function chatter(seed, pitch, radio) {
  const next = random(seed);
  const syllables = 4 + Math.floor(next() * 4);
  const layers = [];
  let at = radio ? 0.07 : 0;
  for (let s = 0; s < syllables; s++) {
    const length = 0.07 + next() * 0.09;
    const voice = new Float32Array(samples(length));
    let phase = 0;
    const base = pitch * (0.85 + next() * 0.4);
    const bend = (next() - 0.5) * 0.3;
    for (let i = 0; i < voice.length; i++) {
      phase += (base * (1 + bend * i / voice.length)) / RATE;
      phase -= Math.floor(phase);
      voice[i] = phase * 2 - 1;
    }
    const mouth = mix(length, [
      [filter(voice, "bandpass", 350 + next() * 500, 4), 1],
      [filter(voice, "bandpass", 1100 + next() * 1300, 5), 0.7],
      [shaped(filter(noise(length, seed + s + 50), "highpass", 3500), () => (next() < 0.3 ? 0.4 : 0.05)), 0.3],
    ]);
    layers.push([shaped(mouth, (t) => Math.sin(Math.PI * Math.min(t / length, 1)) ** 0.6), 1, at]);
    at += length + (next() < 0.25 ? 0.09 : 0.015);
  }
  let out = mix(at + 0.15, layers);
  if (radio) {
    out = filter(filter(out, "highpass", 500), "lowpass", 2800);
    const squelch = shaped(filter(noise(0.07, seed + 99), "highpass", 2200), decay(0.02));
    out = mix(at + 0.2, [[out, 1], [squelch, 0.5], [squelch, 0.6, at + 0.03]]);
  }
  return finish(out, radio ? 3 : 1.6, 0.8);
}

function heartbeat(seed) {
  const thud = shaped(sweep(0.25, 90, 42, 0.04), decay(0.07));
  const gasp = shaped(filter(noise(0.3, seed), "bandpass", 900, 1.2), decay(0.08, 0.02));
  return finish(mix(0.5, [[thud, 1.2], [thud, 0.8, 0.16], [gasp, 0.25]]), 1.8, 0.85);
}

/// A slow bed of wind, made to loop without a join.
function wind(seed) {
  const length = 9;
  const raw = filter(noise(length + 1, seed), "bandpass", (t) => 300 + 160 * Math.sin(t * 0.7) + 90 * Math.sin(t * 1.9), 0.5);
  const out = new Float32Array(samples(length));
  const overlap = samples(1);
  for (let i = 0; i < out.length; i++) {
    const swell = 0.6 + 0.4 * Math.sin((i / out.length) * 2 * Math.PI * 2);
    let value = raw[i];
    if (i < overlap) {
      // The start is the end fading out under the start fading in.
      const blend = i / overlap;
      value = raw[i] * blend + raw[i + out.length] * (1 - blend);
    }
    out[i] = value * swell;
  }
  return finish(out, 1, 0.5);
}

/// What the open air does to a loud sound: a few early slaps off the houses, then a soft wash.
function impulse(seed) {
  const next = random(seed);
  const out = new Float32Array(samples(2.2));
  for (const [at, gain] of [[0.06, 0.5], [0.11, 0.35], [0.19, 0.3], [0.31, 0.22], [0.47, 0.15]]) {
    const start = samples(at * (0.9 + next() * 0.2));
    for (let i = 0; i < 300; i++) out[start + i] += (next() * 2 - 1) * gain * Math.exp(-i / 60);
  }
  for (let i = samples(0.04); i < out.length; i++) {
    out[i] += (next() * 2 - 1) * 0.1 * Math.exp(-(i / RATE) / 0.55);
  }
  return filter(out, "lowpass", 2600);
}

function library() {
  const made = {};
  const add = (name, count, make) => { made[name] = Array.from({ length: count }, (_, i) => make(1000 + name.length * 77 + i * 131)); };
  add("carbine_shot", 4, (seed) => gunshot(seed, true));
  add("pistol_shot", 4, (seed) => pistolShot(seed));
  add("rifle_shot", 4, (seed) => gunshot(seed, false));
  for (const kind of ["concrete", "metal", "wood", "dirt", "glass", "flesh"]) add(`impact_${kind}`, 3, (seed) => impact(seed, kind));
  for (const kind of ["concrete", "dirt", "wood", "metal"]) add(`step_${kind}`, 5, (seed) => footstep(seed, kind));
  add("whiz", 4, whiz);
  add("casing", 4, casing);
  add("explosion", 2, explosion);
  add("jump", 1, (seed) => footstep(seed, "concrete"));
  add("land", 2, (seed) => finish(mix(0.4, [[footstep(seed, "concrete"), 1], [shaped(sweep(0.2, 90, 40, 0.03), decay(0.06)), 1.2]]), 1.5, 0.8));
  add("mag_out", 2, (seed) => mechanism(seed, [[0, 1900, 0.008, 0.8], [0.05, 900, 0.03, 0.9], [0.13, 1400, 0.012, 0.4]]));
  add("mag_in", 2, (seed) => mechanism(seed, [[0, 1200, 0.012, 0.6], [0.06, 800, 0.03, 1], [0.085, 2600, 0.006, 0.7]]));
  add("bolt_release", 2, (seed) => mechanism(seed, [[0, 2400, 0.006, 0.6], [0.035, 1100, 0.03, 1.1], [0.05, 3100, 0.01, 0.6]]));
  add("reload_start", 1, (seed) => mechanism(seed, [[0, 700, 0.03, 0.4], [0.08, 1500, 0.01, 0.3]]));
  add("dry_fire", 1, (seed) => mechanism(seed, [[0, 2800, 0.005, 0.8]]));
  add("weapon_raise", 1, (seed) => mechanism(seed, [[0, 500, 0.05, 0.5], [0.12, 1700, 0.008, 0.4]]));
  add("weapon_lower", 1, (seed) => mechanism(seed, [[0, 420, 0.06, 0.5]]));
  add("grenade_throw", 1, (seed) => mechanism(seed, [[0, 2900, 0.005, 0.7], [0.04, 3600, 0.004, 0.5], [0.16, 380, 0.08, 0.6]]));
  add("pickup", 1, (seed) => mechanism(seed, [[0, 1500, 0.01, 0.6], [0.07, 2100, 0.012, 0.7], [0.15, 900, 0.03, 0.5]]));
  add("use_start", 1, (seed) => mechanism(seed, [[0, 1300, 0.01, 0.5], [0.09, 1650, 0.01, 0.5]]));
  add("use_done", 1, (seed) => mechanism(seed, [[0, 2200, 0.008, 0.8], [0.06, 2900, 0.02, 0.9]]));
  add("charge_armed", 1, () => finish(mix(1.1, [0, 0.33, 0.66].map((at) => [shaped(sweep(0.12, 1800, 1800, 1), decay(0.05)), 0.7, at])), 1, 0.6));
  add("radio", 2, (seed) => finish(mix(0.2, [[shaped(filter(noise(0.09, seed), "highpass", 2400), decay(0.025)), 1], [shaped(sweep(0.05, 1400, 900, 0.02), decay(0.02)), 0.3]]), 1.5, 0.45));
  add("player_hurt", 3, heartbeat);
  add("player_death", 1, (seed) => finish(mix(1.6, [[heartbeat(seed), 1], [shaped(sweep(1.5, 240, 60, 0.6), decay(0.6)), 0.5], [shaped(filter(noise(1.5, seed), "lowpass", 300), decay(0.5)), 0.7]]), 1.5));
  add("death", 3, (seed) => finish(mix(0.9, [[footstep(seed, "dirt"), 0.8, 0.3], [shaped(sweep(0.3, 85, 45, 0.04), decay(0.07)), 1.1, 0.32], [mechanism(seed, [[0.34, 1500, 0.02, 0.5], [0.42, 2300, 0.01, 0.3]]), 0.6]]), 1.4, 0.7));
  add("bark_contact", 5, (seed) => chatter(seed, 118, true));
  add("bark_ally_contact", 3, (seed) => chatter(seed, 150, false));
  return made;
}

// ---------------------------------------------------------------------------- Playing them

/// How far away each kind of sound is heard at full strength, in metres.
const NEAR = { rifle_shot: 14, explosion: 30, impact: 3.5, step: 2, whiz: 4, casing: 1.2, death: 4, bark: 7 };

export class Sound {
  #context = null;
  #buffers = {};
  #master = null;
  #world = null;
  #musicGain = null;
  #echo = null;
  #volume = 0.8;
  #musicVolume = 0.6;
  #drums = 0;
  #strings = null;
  #nextBeat = 0;
  #beat = 0;
  #nextDistant = 6;
  #random = random(77);

  /// Makes the sounds and starts the air and the music. Called from a click, as browsers ask.
  start() {
    if (this.#context) return;
    const context = new AudioContext({ sampleRate: RATE, latencyHint: "interactive" });
    this.#context = context;
    for (const [name, variants] of Object.entries(library())) {
      this.#buffers[name] = variants.map((data) => {
        const buffer = context.createBuffer(1, data.length, RATE);
        buffer.copyToChannel(data, 0);
        return buffer;
      });
    }
    const limiter = context.createDynamicsCompressor();
    limiter.threshold.value = -9;
    limiter.knee.value = 6;
    limiter.ratio.value = 12;
    limiter.attack.value = 0.002;
    limiter.release.value = 0.14;
    limiter.connect(context.destination);
    this.#master = context.createGain();
    this.#master.connect(limiter);
    this.#world = context.createGain();
    this.#world.connect(this.#master);
    this.#echo = context.createConvolver();
    const response = impulse(5);
    const wet = context.createBuffer(1, response.length, RATE);
    wet.copyToChannel(response, 0);
    this.#echo.buffer = wet;
    this.#echo.connect(this.#world);

    this.#musicGain = context.createGain();
    this.#musicGain.connect(this.#master);
    this.#startAir();
    this.#startMusic();
    this.setVolumes(this.#volume, this.#musicVolume);
  }

  resume() {
    this.#context?.resume();
  }

  setVolumes(volume, music) {
    this.#volume = volume;
    this.#musicVolume = music;
    if (!this.#context) return;
    this.#master.gain.setTargetAtTime(volume, this.#context.currentTime, 0.05);
    this.#musicGain.gain.setTargetAtTime(music, this.#context.currentTime, 0.05);
  }

  /// In a menu, the world goes quiet and the music stays.
  setMenu(inMenu) {
    if (!this.#context) return;
    this.#world.gain.setTargetAtTime(inMenu ? 0.12 : 1, this.#context.currentTime, 0.2);
  }

  #startAir() {
    const context = this.#context;
    const data = wind(31);
    const buffer = context.createBuffer(1, data.length, RATE);
    buffer.copyToChannel(data, 0);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    const gain = context.createGain();
    gain.gain.value = 0.13;
    source.connect(gain).connect(this.#world);
    source.start();
  }

  #startMusic() {
    const context = this.#context;
    // A low drone under everything: two strings a fifth apart, slowly opening and closing.
    const drone = context.createGain();
    drone.gain.value = 0.16;
    const tone = context.createBiquadFilter();
    tone.type = "lowpass";
    tone.frequency.value = 190;
    tone.Q.value = 1.2;
    const swell = context.createOscillator();
    swell.frequency.value = 0.045;
    const depth = context.createGain();
    depth.gain.value = 90;
    swell.connect(depth).connect(tone.frequency);
    swell.start();
    for (const [frequency, detune] of [[55, -6], [55, 7], [82.41, -4], [110, 5]]) {
      const voice = context.createOscillator();
      voice.type = "sawtooth";
      voice.frequency.value = frequency;
      voice.detune.value = detune;
      voice.connect(tone);
      voice.start();
    }
    tone.connect(drone).connect(this.#musicGain);
    // A tense cluster a semitone apart, which comes up as the fight heats.
    const strings = context.createGain();
    strings.gain.value = 0;
    const air = context.createBiquadFilter();
    air.type = "bandpass";
    air.frequency.value = 880;
    air.Q.value = 0.7;
    for (const frequency of [220, 233.08, 329.63, 349.23]) {
      const voice = context.createOscillator();
      voice.type = "sawtooth";
      voice.frequency.value = frequency;
      voice.detune.value = (this.#random() - 0.5) * 16;
      voice.connect(air);
      voice.start();
    }
    air.connect(strings).connect(this.#musicGain);
    this.#strings = strings;
    this.#nextBeat = context.currentTime + 0.5;
  }

  /// A drum of the music's pulse: a low hit, or a dry tick.
  #drum(at, low, level) {
    const context = this.#context;
    const gain = context.createGain();
    gain.connect(this.#musicGain);
    if (low) {
      const voice = context.createOscillator();
      voice.frequency.setValueAtTime(78, at);
      voice.frequency.exponentialRampToValueAtTime(36, at + 0.16);
      gain.gain.setValueAtTime(level, at);
      gain.gain.exponentialRampToValueAtTime(0.001, at + 0.42);
      voice.connect(gain);
      voice.start(at);
      voice.stop(at + 0.45);
    } else {
      const source = context.createBufferSource();
      source.buffer = this.#buffers.dry_fire[0];
      source.playbackRate.value = 1.7;
      gain.gain.value = level * 0.35;
      source.connect(gain);
      source.start(at);
    }
  }

  #one(name) {
    const variants = this.#buffers[name];
    return variants ? variants[Math.floor(this.#random() * variants.length)] : null;
  }

  /// Plays the frame's sounds: `text` is the game's list, `listener` where they are heard from.
  play(text, listener, seconds) {
    const context = this.#context;
    if (!context || context.state !== "running") return;
    const now = context.currentTime;
    if (listener.length >= 6) {
      const ear = context.listener;
      const [x, y, z, fx, fy, fz] = listener;
      if (ear.positionX) {
        ear.positionX.value = x; ear.positionY.value = y; ear.positionZ.value = z;
        ear.forwardX.value = fx; ear.forwardY.value = fy; ear.forwardZ.value = fz;
        ear.upX.value = 0; ear.upY.value = 1; ear.upZ.value = 0;
      } else {
        ear.setPosition(x, y, z);
        ear.setOrientation(fx, fy, fz, 0, 1, 0);
      }
    }
    for (const line of text.split("\n")) {
      if (!line) continue;
      const [name, x, y, z, volume, pitch] = line.split(" ");
      const buffer = this.#one(name);
      if (!buffer) continue;
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.playbackRate.value = Number(pitch);
      const gain = context.createGain();
      gain.gain.value = Number(volume);
      source.connect(gain);
      let at = now;
      if (x === "-") {
        gain.connect(this.#world);
        if (name === "carbine_shot" || name === "pistol_shot") {
          const send = context.createGain();
          send.gain.value = 0.22;
          gain.connect(send).connect(this.#echo);
        }
      } else {
        const place = [Number(x), Number(y), Number(z)];
        const distance = Math.hypot(place[0] - listener[0], place[1] - listener[1], place[2] - listener[2]);
        const kind = Object.keys(NEAR).find((key) => name.startsWith(key)) ?? "impact";
        const panner = context.createPanner();
        panner.panningModel = "HRTF";
        panner.distanceModel = "inverse";
        panner.refDistance = NEAR[kind];
        panner.rolloffFactor = 1.1;
        panner.positionX.value = place[0]; panner.positionY.value = place[1]; panner.positionZ.value = place[2];
        // Air takes the top off what is far away, and sound takes its time to arrive.
        const air = context.createBiquadFilter();
        air.type = "lowpass";
        air.frequency.value = Math.max(700, 17000 / (1 + distance / 30));
        gain.connect(air).connect(panner).connect(this.#world);
        if (kind === "rifle_shot" || kind === "explosion") {
          const send = context.createGain();
          send.gain.value = Math.min(0.5, 0.15 + distance / 200);
          panner.connect(send).connect(this.#echo);
        }
        at = now + Math.min(distance / 343, 1.5);
      }
      source.start(at);
    }

    // The music: the pulse and the strings follow how hot the fight is.
    const heat = listener[6] ?? 0;
    this.#drums += (heat - this.#drums) * Math.min(1, seconds * (heat > this.#drums ? 2.5 : 0.35));
    this.#strings.gain.setTargetAtTime(this.#drums * 0.05, now, 0.5);
    const beat = 60 / 104 / 2;
    while (this.#nextBeat < now + 0.15) {
      const step = this.#beat % 16;
      if (this.#drums > 0.08) {
        if ([0, 3, 6, 10, 12].includes(step)) this.#drum(this.#nextBeat, true, 0.42 * this.#drums);
        if (step % 2 === 1 && this.#drums > 0.4) this.#drum(this.#nextBeat, false, 0.3 * this.#drums);
      }
      this.#beat++;
      this.#nextBeat += beat;
    }

    // Far off, the occupation goes on: a burst of fire somewhere across town, now and then.
    this.#nextDistant -= seconds;
    if (this.#nextDistant <= 0) {
      this.#nextDistant = 7 + this.#random() * 16;
      const shots = this.#random() < 0.25 ? 1 : 2 + Math.floor(this.#random() * 5);
      const pan = context.createStereoPanner();
      pan.pan.value = this.#random() * 1.6 - 0.8;
      const far = context.createBiquadFilter();
      far.type = "lowpass";
      far.frequency.value = 500 + this.#random() * 500;
      const gain = context.createGain();
      gain.gain.value = 0.1 + this.#random() * 0.08;
      far.connect(gain).connect(pan).connect(this.#world);
      for (let i = 0; i < shots; i++) {
        const source = context.createBufferSource();
        source.buffer = shots === 1 ? this.#one("explosion") : this.#one("rifle_shot");
        source.playbackRate.value = 0.8 + this.#random() * 0.15;
        source.connect(far);
        source.start(now + 0.3 + i * (0.09 + this.#random() * 0.05));
      }
    }
  }
}
