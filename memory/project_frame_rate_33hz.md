---
name: game runs at ~33Hz not 50Hz
description: Main loop waits for the centisecond timer to reach >=3 before drawing the player, gating the per-frame rate to ~33 frames per second despite the 50Hz vsync.
type: project
---

The BBC's vsync IRQ fires at 50Hz, but Thrust's main loop runs a centisecond-timer wait (`timer >= 3`) before each frame's player-draw step. The result is one per-frame cycle every ~3 cs = ~30ms = ~33 frames per second. Confirmed by Kieran on 2026-05-08 when retuning the switches & triggers refractory window.

**Why:** the original game was tuned to a 33Hz update tempo. Physics integration steps, particle lifetimes, gun fire rates, and explosion durations are all balanced against this cadence.

**How to apply:** any time you need to convert a frame count to a duration (refractory windows, animation lengths, cool-downs, telegraph timings, "N frames before X happens"), use **33Hz** not 50Hz. Examples:
- 0.5s ≈ 16 frames ($10)
- 0.6s ≈ 20 frames ($14)
- 1.0s ≈ 33 frames ($21)
- 1.5s ≈ 50 frames ($32)

If a value comes out feeling too slow / fast in-emulator, suspect this conversion first.
