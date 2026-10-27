// smoke.mjs - boot each disc headless in jsbeeb and play the first frames of every level.
//
//   node tools/smoke.mjs                 both discs (build/thrust.ssd, build/thrust-orig.ssd)
//   node tools/smoke.mjs build/thrust.ssd [--frames N] [--shots]
//   SMOKE_MODEL=Master node tools/smoke.mjs     on a Master 128 (default B-DFS1.2)
//
// For each disc: SHIFT+BREAK on a Model B (jsbeeb's B has RAM in sideways bank 4), wait for the
// instructions page, press SPACE. Then for each level 0-5: stop at start_new_level, set
// level_number so its INC lands on that level, run N fields with no keys held, and count passes
// through tick_loop. A level passes if the game loop ran for at least a quarter of the fields,
// was still running at the end, and level_number is still the level asked for. --shots writes build/smoke/<disc>-L<n>.png.
//
// Addresses come from the build's label dump (build/<stem>.labels, written by build.ps1), never
// from this file. Exit 0: every level of every disc passed. 1: something failed. 2: could not
// judge (no labels, the disc never reached the instructions page).
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { keys, loadMachineSession, version } from "./jsbeeb_src.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const opt = (name, def) => {
    const i = args.indexOf(name);
    if (i < 0) return def;
    const v = args[i + 1];
    args.splice(i, 2);
    return v;
};
const flag = (name) => {
    const i = args.indexOf(name);
    if (i < 0) return false;
    args.splice(i, 1);
    return true;
};
const FRAMES = Number(opt("--frames", 300));
const SHOTS = flag("--shots");
const discs = args.length ? args.map((a) => resolve(a)) : ["thrust.ssd", "thrust-orig.ssd"].map((d) => join(root, "build", d));

/** beebasm's -d -labels dump: [{'name':123L,...}] (a Python-style dict). */
function readLabels(path) {
    const text = readFileSync(path, "utf8");
    const out = {};
    for (const m of text.matchAll(/'([^']+)':(-?\d+)L/g)) out[m[1]] = Number(m[2]);
    return out;
}

function need(labels, name) {
    if (!(name in labels)) {
        console.error(`label ${name} not in the dump`);
        process.exit(2);
    }
    return labels[name];
}

const MachineSession = await loadMachineSession();
const K = keys();
let failures = 0;
const report = [];

for (const disc of discs) {
    const labelsPath = disc.replace(/\.ssd$/i, ".labels");
    if (!existsSync(disc) || !existsSync(labelsPath)) {
        console.error(`${disc} or its .labels missing: run .\\build.ps1 first`);
        process.exit(2);
    }
    const L = readLabels(labelsPath);
    const TICK = need(L, "tick_loop"), START = need(L, "start_new_level"), LEVEL = need(L, "level_number");
    const name = basename(disc, ".ssd");

    const m = new MachineSession(process.env.SMOKE_MODEL || "B-DFS1.2");
    await m.initialise();
    await m.boot();
    m.loadDisc(disc);
    await m.autoboot();
    await m.runFrames(300);
    m.keyDown(K.SPACE);
    await m.runFrames(10);
    m.keyUp(K.SPACE);
    try {
        await m.runUntilAddress(START, 10);
    } catch {
        console.error(`${name}: never reached start_new_level after SPACE`);
        process.exit(2);
    }
    const atStart = m.snapshot();

    for (let level = 0; level < 6; level++) {
        m.restore(atStart);
        m.writeMemory(LEVEL, [(level - 1) & 0xff]);
        let ticks = 0, lastTick = 0;
        const f0 = m.frameCount;
        const unwatch = m.onExecute((pc) => {
            if (pc === TICK) { ticks++; lastTick = m.frameCount - f0; }
        });
        const { framesRun } = await m.runFrames(FRAMES);
        unwatch();
        const got = m.readMemory(LEVEL, 1)[0];
        // The level-start animation, and a death and respawn if a gun hits the idle ship, pause
        // tick_loop for a while, so ask only that the loop ran for a quarter of the fields and
        // was still running in the last 50. A crash or a hang stops it for good.
        const ok = framesRun >= FRAMES && got === level && ticks >= FRAMES / 4 && framesRun - lastTick <= 50;
        if (!ok) failures++;
        report.push({ disc: name, level, ok, ticks, fields: framesRun, last_pass_field: lastTick, level_number: got });
        console.error(`${name} level ${level}: ${ok ? "ok  " : "FAIL"} ${ticks} passes in ${framesRun} fields (last at ${lastTick}), level_number=${got}`);
        if (SHOTS) {
            const dir = join(root, "build", "smoke");
            mkdirSync(dir, { recursive: true });
            writeFileSync(join(dir, `${name}-L${level}.png`), await m.screenshotActive());
        }
    }
    m.destroy();
}

console.log(JSON.stringify({ tool: "smoke", jsbeeb: version(), frames: FRAMES, failures, report }));
process.exit(failures ? 1 : 0);
