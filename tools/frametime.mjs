// frametime.mjs - how long each game frame takes, measured on the demo.
//
//   node tools/frametime.mjs [disc ...] [--fields N] [--level L]
//
// --level L: start level L (0-5) and leave the ship idle on its pad instead of running the demo.
// --fly: with --level, fly a fixed pattern (thrust bursts, turning) so the window scrolls both
//        ways; keys are pressed by matrix position, so the run is the same every time.
//
// Boots each disc (default both builds), starts a game as the demo (demo_mode_flag, recorded
// keys from level 0), and times every pass through tick_loop with the CPU's cycle counter. The demo replays
// recorded keys, so a build's run is the same every time and two builds can be compared. The
// game frame is gated on the OS centisecond clock (draw_player_timed_to_vsync waits for >= 3 cs),
// so a frame is 3 cs (60,000 cycles) when the work fits and 4 cs or more when it does not.
//
// Prints a histogram of frame lengths in cs and the mean; one JSON line on stdout.
// Exit 0, or 2 if it could not run (missing labels, the demo never started).
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { keys, loadMachineSession, version } from "./jsbeeb_src.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
let FIELDS = 3000, LEVEL = -1;
const fi = args.indexOf("--fields");
if (fi >= 0) { FIELDS = Number(args[fi + 1]); args.splice(fi, 2); }
const FLY = args.includes("--fly");
if (FLY) args.splice(args.indexOf("--fly"), 1);
const li = args.indexOf("--level");
if (li >= 0) { LEVEL = Number(args[li + 1]); args.splice(li, 2); }
const discs = args.length ? args.map((a) => resolve(a)) : ["thrust.ssd", "thrust-orig.ssd"].map((d) => join(root, "build", d));

const MS = await loadMachineSession();
const K = keys();
const results = [];
for (const disc of discs) {
    const lp = disc.replace(/\.ssd$/i, ".labels");
    if (!existsSync(lp)) { console.error(`${lp} missing`); process.exit(2); }
    const L = {};
    for (const m of readFileSync(lp, "utf8").matchAll(/'([^']+)':(-?\d+)L/g)) L[m[1]] = +m[2];
    for (const n of ["tick_loop", "start_new_level", "level_number", "demo_keypress_bit_mask", "demo_keypress_timer", "demo_keypress_index"]) if (!(n in L)) { console.error(`label ${n} missing`); process.exit(2); }

    const m = new MS("B-DFS1.2");
    await m.initialise();
    await m.boot();
    m.loadDisc(disc);
    await m.autoboot();
    await m.runFrames(300);
    // Start a game, then turn it into the demo at start_new_level: demo_mode_flag ($01) on and
    // the recorded keypress stream rewound. (The real demo only runs after a game over.)
    m.keyDown(K.SPACE);
    await m.runFrames(10);
    m.keyUp(K.SPACE);
    try { await m.runUntilAddress(L.start_new_level, 20); } catch { console.error(`${disc}: game never started`); process.exit(2); }
    if (LEVEL >= 0) {
        m.writeMemory(L.level_number, [(LEVEL - 1) & 0xff]);   // idle on this level instead
    } else {
        m.writeMemory(0x01, [0xff]);
        for (const n of ["demo_keypress_bit_mask", "demo_keypress_timer", "demo_keypress_index"]) m.writeMemory(L[n], [0]);
    }
    await m.runUntilAddress(L.tick_loop, 20);

    const cpu = m._machine.processor;
    const now = () => cpu.cycleSeconds * 2000000 + cpu.currentCycles;
    const lengths = [];
    let last = now();
    const un = m.onExecute((pc) => {
        if (pc !== L.tick_loop) return;
        const t = now();
        lengths.push(t - last);
        last = t;
    });
    if (FLY) {
        // SHIFT = thrust (matrix col 0, row 0). Rotate keys differ by build (_FRIENDLY_KEYS:
        // Z/X; original: CAPS LOCK/CTRL), so press both pairs; the unused pair does nothing.
        const THRUST = [0, 0], LEFT = [[1, 6], [0, 4]], RIGHT = [[2, 4], [1, 0]];
        const hold = async (keys, n) => { keys.forEach((k) => m.keyDownRaw(k)); await m.runFrames(n); keys.forEach((k) => m.keyUpRaw(k)); };
        let done = 0;
        const pattern = [[[THRUST], 40], [[], 30], [LEFT, 6], [[THRUST], 25], [[], 25], [RIGHT, 12], [[THRUST], 25], [[], 30], [LEFT, 6]];
        while (done < FIELDS) for (const [k, n] of pattern) { await hold(k.flat().length ? k : [], n); done += n; }
    } else {
        await m.runFrames(FIELDS);
    }
    un();
    m.destroy();

    // Frames longer than 20 cs are level changes, deaths and messages, not game frames.
    const frames = lengths.filter((c) => c < 400000);
    const hist = {};
    for (const c of frames) { const cs = Math.round(c / 20000); hist[cs] = (hist[cs] || 0) + 1; }
    const mean = frames.reduce((a, b) => a + b, 0) / frames.length / 20000;
    const name = disc.split(/[\\/]/).pop();
    console.error(`${name}: ${frames.length} frames, mean ${mean.toFixed(2)} cs (${(100 / mean).toFixed(1)} fps); by length in cs: ${JSON.stringify(hist)}`);
    results.push({ disc: name, level: LEVEL, frames: frames.length, mean_cs: +mean.toFixed(3), hist });
}
console.log(JSON.stringify({ tool: "frametime", jsbeeb: version(), fields: FIELDS, results }));
