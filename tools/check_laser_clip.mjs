// check_laser_clip.mjs - an up-facing laser beam must not plot above the playfield.
//
//   node tools/check_laser_clip.mjs [build/thrust.ssd]
//
// Level 0's laser turret (object 3) is moved up 40 world units and given dx 0, dy -128, so its
// full beam would end above the top of the screen. Rows above the playfield map to the status
// bar and, below row 16, to code at $3800-$3C7F (calculate_pixels_ptr). The check compares
// $3800-$3C7F before and after 400 fields against the bytes the game itself writes there.
// Exit 0: no beam pixels below the screen. 1: the beam wrote there. 2: could not run.
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { keys, loadMachineSession } from "./jsbeeb_src.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const disc = resolve(process.argv[2] || join(root, "build", "thrust.ssd"));
const L = {};
for (const m of readFileSync(disc.replace(/\.ssd$/i, ".labels"), "utf8").matchAll(/'([^']+)':(-?\d+)L/g)) L[m[1]] = +m[2];
for (const n of ["level_0_obj_type", "level_0_obj_data_1", "level_0_obj_data_2", "level_0_obj_pos_Y", "start_new_level"])
    if (!(n in L)) { console.error(`label ${n} missing (SWRAM build with _TIMED_LASER?)`); process.exit(2); }

const MS = await loadMachineSession();
const K = keys();
const m = new MS("B-DFS1.2");
await m.initialise();
await m.boot();
m.loadDisc(disc);
await m.autoboot();
await m.runFrames(300);
const OBJ = 3;
if (m.readMemory(L.level_0_obj_type + OBJ, 1, { bank: 4 })[0] !== 0x09) { console.error("level 0 object 3 is not a laser"); process.exit(2); }
m.writeMemory(L.level_0_obj_data_1 + OBJ, [0x00], { bank: 4 });
m.writeMemory(L.level_0_obj_data_2 + OBJ, [0x80], { bank: 4 });
const y = m.readMemory(L.level_0_obj_pos_Y + OBJ, 1, { bank: 4 })[0];
m.writeMemory(L.level_0_obj_pos_Y + OBJ, [(y - 0x28) & 0xff], { bank: 4 });
m.keyDown(K.SPACE);
await m.runFrames(10);
m.keyUp(K.SPACE);
await m.runUntilAddress(L.start_new_level, 10);

const below = () => [0x3800, 0x3900, 0x3a00, 0x3b00].flatMap((a) => m.readMemory(a, 256)).concat(m.readMemory(0x3c00, 128));
const before = below();
await m.runFrames(400);
const after = below();
// The game's own variables and self-modified operands in this range (measured on a good build)
const expected = new Set([0x38ef, 0x38f4, 0x3984, 0x3988, 0x3acd]);
const stray = [];
for (let i = 0; i < before.length; i++) if (before[i] !== after[i] && !expected.has(0x3800 + i)) stray.push((0x3800 + i).toString(16));
console.log(JSON.stringify({ tool: "check_laser_clip", stray }));
process.exit(stray.length ? 1 : 0);
