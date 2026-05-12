---
name: alive flag couples drawing and behaviour
description: OBJ_flag_alive (level_obj_flags bit 1) controls both whether an object is plotted AND whether its per-frame update runs; clearing it makes the object vanish, not just go dormant.
type: project
---

When the switches & triggers MVP wired `clear_alive`/`toggle_alive` to a gun, the gun went *invisible* rather than going dormant — confirmed in-emulator on 2026-05-06 with the level-3 hand-authored test wiring. Engine-side this is because `OBJ_flag_alive` is the gate the per-object loop tests at `test_alive_flag` (`thrust.6502:1806`) before doing both the visibility / plot path AND the per-type behaviour (firing, beam draw, etc.).

**Why:** the original game only ever cleared `alive` on destruction, where "vanish + stop firing" is the right combined behaviour. The flag never had to mean two separate things until switches let designers disable a behaviour while keeping the object visible.

**How to apply:** when designing actions for switches/triggers (or any future "disable but keep visible" feature), don't reuse `OBJ_flag_alive`. Add a separate `OBJ_flag_disabled` bit (or similar) and gate per-type behaviour on it independently, leaving `alive` to mean "exists / is drawn". The MVP set_alive / clear_alive / toggle_alive actions stay as-is — they're the "vanish" semantics — but a follow-up should add `set_disabled` / `clear_disabled` / `toggle_disabled` actions that flip the new flag, and an editor cue (e.g. dimmed sprite) to indicate disabled state. Plan addition belongs in `docs/plan-switches-and-triggers.md` §10 deferred follow-ups.
