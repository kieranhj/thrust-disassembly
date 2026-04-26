# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Disassembly and annotated source of **Thrust** (BBC Micro) by Jeremey C. Smith. The source was reverse-engineered by Kieran HJ Connell using BeebDis, and compiles with **BeebAsm**. The single source file `thrust.asm` (~10k lines of 6502 assembly) produces a bootable `.ssd` disc image.

## Build

```
beebasm.exe -i thrust.asm -do thrust.ssd -boot Thrust -v
```

The `make.bat` script runs this (expects `beebasm.exe` at `..\..\Bin\beebasm.exe`) and verifies the output CRC32 against `6389c446` using `crc32dos.exe`.

To run in an emulator: `run.bat` launches the `.ssd` in BeebEm.

## Assembly Conventions

- **Assembler:** BeebAsm syntax (backslash `\` comments, `$` hex prefix, `&` also used for hex, `=` for constants, `EQUB`/`EQUW`/`EQUS` for data).
- **Fixed-point arithmetic:** Most calculations use Q7.8. Y-axis values use Q10.8 (worlds are several screens deep). Some X physics use Q7.16 for extra precision.
- **Naming suffixes:** `_LO`/`_HI` = low/high byte of 16-bit values. `_FRAC`/`_INT` = fractional/integer parts of fixed-point. `_FRAC_LO` = extra low-precision byte. `_INT_HI` = extra high byte.
- **Memory map:** Code relocates from load address `$1A00` to execution address `$0A60`. Key regions: zero page for variables, pages `$300-$5FF` for terrain data, pages `$600-$7BF` for particle system, page `$7C0+` for sound, page `$880+` for trig lookup tables, screen at `$3C80`.

## Build Verification

A correct **non-SWRAM** build (`_SWRAM_BUILD = FALSE` at `thrust.6502:30`) must produce a `.ssd` file with CRC32 `6389c446`. This CRC anchors the original-game gameplay logic (physics, ship handling) — any change that alters this binary risks an unintentional gameplay regression. The default build is SWRAM-enabled and will produce a different CRC; toggle `_SWRAM_BUILD = FALSE` to verify the canonical CRC.
