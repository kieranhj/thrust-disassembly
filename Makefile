# Wrapper so that `make` works from PowerShell / Windows Terminal.
# GNU make runs recipes with cmd.exe here (no sh on PATH); build.ps1 is the build.
PS = pwsh -NoProfile -ExecutionPolicy Bypass -File build.ps1

.PHONY: all build release flags smoke run run-orig help
all: build

build:
	$(PS)

release:
	$(PS) -Release

flags:
	$(PS) -Flags

smoke:
	$(PS) -Smoke

run:
	$(PS) -Run

run-orig:
	$(PS) -Run -Orig

help:
	@echo make           - build build\thrust.ssd (SWRAM) and build\thrust-orig.ssd, check the original's CRC
	@echo make release   - the SWRAM disc for other people (build.ps1 -Release)
	@echo make flags     - also build with each feature flag off in turn
	@echo make smoke     - also play every level headless in jsbeeb (tools\smoke.mjs, needs node)
	@echo make run       - build, then launch b2 on the SWRAM disc (run-orig: the original)
	@echo make help      - this list
