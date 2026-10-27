// jsbeeb_src.mjs - find the jsbeeb the MCP is using, and say which one it is.
//
// beeb-port-kit template, MIT, Kieran Connell 2026.
//
// The headless harnesses (probe_shot.mjs, verify_dynamic.mjs) drive the same
// MachineSession class the jsbeeb MCP server uses, so they have to import it from
// wherever `npx jsbeeb-mcp` cached the package. That path used to be hardcoded:
//
//   C:/Users/.../npm-cache/_npx/e76f2a7d329553db/node_modules/jsbeeb/src
//
// which named one user, one machine, and an npx cache hash that changes whenever the
// spec does. Worse, it was silent: updating jsbeeb-mcp from 3.3.0 to 3.4.0 swapped
// jsbeeb 1.24.1 for 1.25.0 underneath that exact path, and the harnesses would have
// carried on measuring against a different emulator without a word (2026-09-07).
//
// So: resolve it, and PRINT THE VERSION on stderr, because a harness that cannot say
// which emulator it measured with is not an instrument.
//
// And resolve THE PINNED ONE. `.mcp.json` pins the MCP (`jsbeeb-mcp@4.3.0`), and
// the jsbeeb loaded here is the one in the npx cache holding exactly that
// jsbeeb-mcp - so the harnesses measure on the emulator the MCP runs. This used to
// take the highest jsbeeb in ANY cache, which is whatever an unpinned project last
// pulled: on 2026-10-21 the kit was pinned to 4.0.0 (jsbeeb 2.3.2) and its
// harnesses ran on 2.10.0, from another project's bare `npx jsbeeb-mcp`. If the
// pinned cache is missing it refuses, and says the one command that makes it.
// Without a pin (no `.mcp.json`, or a bare spec) it falls back to the highest, and
// says so.
//
// JSBEEB_SRC still overrides everything, for a checkout or an odd install.

import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

function versionAt(dir) {
    const pkg = join(dir, "package.json");
    if (!existsSync(join(dir, "src", "machine-session.js")) || !existsSync(pkg)) return null;
    try {
        return JSON.parse(readFileSync(pkg, "utf8")).version || "0.0.0";
    } catch {
        return null;
    }
}

const cmp = (a, b) => {
    const pa = a.split(".").map(Number), pb = b.split(".").map(Number);
    for (let i = 0; i < 3; i++) if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) - (pb[i] || 0);
    return 0;
};

/** The exact jsbeeb-mcp version `.mcp.json` (beside tools/) pins, or null. */
function pinnedMcp() {
    const file = join(dirname(fileURLToPath(import.meta.url)), "..", ".mcp.json");
    if (!existsSync(file)) return null;
    try {
        const args = JSON.parse(readFileSync(file, "utf8")).mcpServers?.jsbeeb?.args || [];
        for (const a of args) {
            const m = /^jsbeeb-mcp@(\d+\.\d+\.\d+)$/.exec(a);
            if (m) return m[1];
        }
    } catch { /* unreadable: treat as unpinned */ }
    return null;
}

/**
 * The jsbeeb in the npx cache `npx jsbeeb-mcp@<pin>` made - the one the MCP
 * runs - or null. npx names that folder by the first 16 hex digits of the
 * SHA-512 of the spec it was given (checked 2026-10-21: `jsbeeb-mcp@4.3.0` ->
 * cab22bfea9534dc7, `jsbeeb-mcp` -> e76f2a7d329553db), so it is computed, not
 * searched for. A bare `npx jsbeeb-mcp` cache can hold the same jsbeeb-mcp over
 * a jsbeeb resolved on another day, and its package.json cannot tell them
 * apart: npx writes `^<version>` into both.
 */
function pinnedCache(pin) {
    const hash = createHash("sha512").update(`jsbeeb-mcp@${pin}`).digest("hex").slice(0, 16);
    const roots = [
        process.env.LOCALAPPDATA ? join(process.env.LOCALAPPDATA, "npm-cache", "_npx") : null,
        join(homedir(), ".npm", "_npx"),
    ].filter(Boolean);
    for (const root of roots) {
        const mods = join(root, hash, "node_modules");
        try {
            const mcp = JSON.parse(readFileSync(join(mods, "jsbeeb-mcp", "package.json"), "utf8"));
            const dir = join(mods, "jsbeeb");
            const v = versionAt(dir);
            if (mcp.version === pin && v) return { dir, version: v };
        } catch { /* absent, or a half-written install */ }
    }
    return null;
}

/** Absolute path to jsbeeb's src/, plus the version found there. */
export function resolveJsbeebSrc() {
    const override = process.env.JSBEEB_SRC;
    if (override) {
        const dir = join(override, "..");
        return { src: override.split("\\").join("/"), version: versionAt(dir) || "unknown (JSBEEB_SRC)" };
    }

    const pin = pinnedMcp();
    if (pin) {
        const hit = pinnedCache(pin);
        if (!hit) {
            throw new Error(
                `.mcp.json pins jsbeeb-mcp@${pin}, and no npx cache holds it. Run ` +
                `\`npx -y jsbeeb-mcp@${pin} < /dev/null\` once and let it finish ` +
                "(an interrupted install leaves a cache with no package.json), " +
                "or set JSBEEB_SRC to a jsbeeb checkout's src/ directory.");
        }
        return { src: join(hit.dir, "src").split("\\").join("/"), version: hit.version, mcp: pin };
    }
    console.error("jsbeeb_src: no exact jsbeeb-mcp pin in .mcp.json - taking the highest jsbeeb cached");

    const roots = [
        join(process.cwd(), "node_modules"),
        process.env.LOCALAPPDATA ? join(process.env.LOCALAPPDATA, "npm-cache", "_npx") : null,
        join(homedir(), ".npm", "_npx"),
    ].filter(Boolean);

    const found = [];
    for (const root of roots) {
        if (!existsSync(root)) continue;
        // either <root>/jsbeeb, or <root>/<npx-hash>/node_modules/jsbeeb
        for (const dir of [join(root, "jsbeeb"),
                           ...readdirSync(root, { withFileTypes: true })
                               .filter((e) => e.isDirectory())
                               .map((e) => join(root, e.name, "node_modules", "jsbeeb"))]) {
            const v = versionAt(dir);
            if (v) found.push({ dir, version: v });
        }
    }
    if (!found.length) {
        throw new Error(
            "cannot find jsbeeb. Run `npx jsbeeb-mcp` once so npm caches it, " +
            "or set JSBEEB_SRC to a jsbeeb checkout's src/ directory.");
    }
    found.sort((a, b) => cmp(b.version, a.version));
    const best = found[0];
    return { src: join(best.dir, "src").split("\\").join("/"), version: best.version };
}

/**
 * The key argument `keyDown`/`keyUp` want, for the jsbeeb that is loaded.
 *
 * **jsbeeb 2.0 CHANGED THE TYPE.** 1.x took a numeric browser `keyCode` (16 =
 * SHIFT, 88 = X); 2.x takes a `KeyboardEvent.code` STRING naming the physical
 * position ("ShiftLeft", "KeyX"). Passing the old number to 2.x matches
 * nothing and, up to 2.3.0, DOES NOT THROW - the key is simply never pressed
 * (2.3.1 throws instead: mattgodbolt/jsbeeb#1172, fixed). That is how it
 * was found: SHIFT+BREAK stopped booting the disc, so every harness counter
 * read its power-on value and verify_dynamic.mjs reported all zeros, which
 * reads exactly like a regression in the port (2026-09-23; jsbeeb 2.3.0 came
 * in with jsbeeb-mcp 4.0.0).
 *
 * Add a key here rather than writing a literal at the call site, so the next
 * harness cannot reintroduce the same silent failure.
 */
export function keys() {
    const { version } = resolveJsbeebSrc();
    const major = parseInt(version, 10);
    return keysFor(!Number.isNaN(major) && major >= 2);
}

function keysFor(modern) {
    return modern
        ? { SHIFT: "ShiftLeft", CTRL: "ControlLeft", ESCAPE: "Escape",
            SPACE: "Space", RETURN: "Enter",
            X: "KeyX", Z: "KeyZ", K: "KeyK", M: "KeyM", L: "KeyL", P: "KeyP", Q: "KeyQ",
            UP: "ArrowUp", DOWN: "ArrowDown", LEFT: "ArrowLeft", RIGHT: "ArrowRight" }
        : { SHIFT: 16, CTRL: 17, ESCAPE: 27,
            SPACE: 32, RETURN: 13,
            X: 88, Z: 90, K: 75, M: 77, L: 76, P: 80, Q: 81,
            UP: 38, DOWN: 40, LEFT: 37, RIGHT: 39 };
}

/** The jsbeeb version the harnesses load ("2.10.2"), for a report line. */
export function version() {
    return resolveJsbeebSrc().version;
}

/**
 * THE KEY POLICY: a key argument of the WRONG TYPE for this jsbeeb is translated
 * if `keys()` knows it, and REFUSED - thrown - if it does not. Never pressed as
 * nothing.
 *
 * 1942 for the BBC Master carried this as `withNumericKeys` (its
 * tools/jsbeeb_src.mjs, 2026-09-23): every one of its harnesses booted with
 * `keyDown(16)` for SHIFT+BREAK, 2.3.0 took a string, the number named no key,
 * and every oracle reported "never reached" on a good image. jsbeeb 2.3.1 throws
 * on an unknown code by itself (mattgodbolt/jsbeeb#1172), but not on a number
 * that happens to be a valid code in some other sense, and not under 1.x for a
 * string: this wrapper makes both directions loud on every version. Add a key to
 * `keys()` rather than here.
 *
 * keyDownRaw([col, row]) - the BBC matrix position - did not change across 2.0
 * and is untouched. A project that needs a modifier held with certain matrix
 * keys can wrap keyDownRaw the same way: 1942's `withDebugCtrl` held CTRL for
 * as long as S, I or B was down, because its debug keys wanted CTRL from
 * decision 136 and thirty harnesses pressed them by four idioms - one wrapper,
 * not thirty edits. It is a pattern, not something the template needs.
 */
function withKeyPolicy(MachineSession, modern) {
    const both = [keysFor(true), keysFor(false)];
    const table = new Map();
    for (const name of Object.keys(both[0])) table.set(both[modern ? 1 : 0][name], both[modern ? 0 : 1][name]);
    const want = modern ? "string" : "number";
    const code = (k) => {
        if (typeof k === want) return k;
        if (!table.has(k)) {
            throw new Error(`key ${JSON.stringify(k)} is a ${typeof k}, this jsbeeb wants a ${want}, and `
                + "keys() in tools/jsbeeb_src.mjs has no translation: add it there, or press the BBC "
                + "matrix position with keyDownRaw([col, row])");
        }
        return table.get(k);
    };
    return class extends MachineSession {
        keyDown(k, shiftDown = false) { return super.keyDown(code(k), shiftDown); }
        keyUp(k) { return super.keyUp(code(k)); }
    };
}

/** Import MachineSession, announcing the jsbeeb it came from. */
export async function loadMachineSession() {
    const { src, version, mcp } = resolveJsbeebSrc();
    console.error(`[jsbeeb ${version}${mcp ? `, jsbeeb-mcp@${mcp}` : ""}] ${src}`);
    const { MachineSession } = await import(`file:///${src}/machine-session.js`);
    const major = parseInt(version, 10);
    return withKeyPolicy(MachineSession, !Number.isNaN(major) && major >= 2);
}
