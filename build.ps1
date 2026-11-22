# Build Thrust -> build/thrust.ssd (Thrust Next, SWRAM) and build/thrust-orig.ssd (the original)
#
#   .\build.ps1             assemble both discs; fail unless the original's CRC32 is 6389c446
#   .\build.ps1 -Run        ...then launch b2 on the SWRAM disc (-Beebjit for beebjit)
#   .\build.ps1 -Run -Orig  ...launch the original disc instead
#   .\build.ps1 -Smoke      ...then boot both discs in jsbeeb and play every level (tools/smoke.mjs),
#                           and run tools/check_laser_clip.mjs
#   .\build.ps1 -Flags      ...then build the SWRAM game with each feature flag off in turn
#   .\build.ps1 -Release    the SWRAM disc for other people: debug display off (asserted in the
#                           source) and an INFO file on the disc naming the commit and the flags
#
# Both discs come from the same source: thrust.6502 line 30 is `_SWRAM_BUILD =? TRUE`, and this
# script passes -D _SWRAM_BUILD=0 / -1 on every build. The original's CRC32 anchors the game's
# behaviour (CLAUDE.md, "Build Verification"); any change that moves it fails the build.
#
# beebasm: $env:BEEBASM, else beebasm.exe in the repo root (pinned at 1.11).
# Emulators: $env:B2 / $env:BEEBJIT, else the paths below.
param([switch]$Run, [switch]$Orig, [switch]$Beebjit, [switch]$Smoke, [switch]$Flags, [switch]$Release)

$ErrorActionPreference = 'Stop'
if ($args) { throw "build.ps1: unknown argument(s): $args" }

$OrigCrc = '6389c446'

$root  = $PSScriptRoot
$build = Join-Path $root 'build'
New-Item -ItemType Directory -Force $build | Out-Null

$beebasm = if ($env:BEEBASM) { $env:BEEBASM } else { Join-Path $root 'beebasm.exe' }
if (-not (Test-Path $beebasm)) { throw "beebasm not found: $beebasm (set `$env:BEEBASM)" }

function Get-Crc32([string]$path) {
    $table = [uint32[]]::new(256)
    for ($i = 0; $i -lt 256; $i++) {
        $c = [uint32]$i
        for ($k = 0; $k -lt 8; $k++) {
            if ($c -band 1) { $c = [uint32](0xEDB88320u -bxor ($c -shr 1)) } else { $c = $c -shr 1 }
        }
        $table[$i] = $c
    }
    $crc = [uint32]::MaxValue
    foreach ($b in [IO.File]::ReadAllBytes($path)) {
        $crc = $table[($crc -bxor $b) -band 0xFF] -bxor ($crc -shr 8)
    }
    return ('{0:x8}' -f ($crc -bxor [uint32]::MaxValue))
}

function Invoke-Build([string]$name, [int]$swram, [string[]]$defines = @()) {
    $ssd    = Join-Path $build "$name.ssd"
    $log    = Join-Path $build "$name.txt"
    $labels = Join-Path $build "$name.labels"
    Remove-Item -ErrorAction SilentlyContinue $ssd, $labels
    # beebasm resolves INCLUDEs relative to the working directory
    Push-Location $root
    try {
        $defs = @('-D', "_SWRAM_BUILD=$swram") + ($defines | ForEach-Object { '-D', $_ })
        & $beebasm -i thrust.6502 -do $ssd -boot Thrust -v -d -labels $labels @defs *> $log
        $code = $LASTEXITCODE
    } finally { Pop-Location }
    if ($code -ne 0 -or -not (Test-Path $ssd)) {
        Get-Content $log | Select-String -Pattern 'error' -SimpleMatch | Select-Object -First 10 | ForEach-Object { Write-Host $_ }
        throw "${name}: beebasm failed (exit $code), see $log"
    }
    return $ssd
}

$origSsd  = Invoke-Build 'thrust-orig' 0
if ($Release) {
    # INFO, *TYPE-able on the disc: which commit, whether the tree was clean, and every flag's
    # value (names without underscores, which MODE 7 shows as dashes). The values come from the build's own FLAG lines, so assemble once to read them
    # (with a placeholder INFO for PUTTEXT), then again with the real file.
    $infoPath = Join-Path $build 'INFO.txt'
    [IO.File]::WriteAllText($infoPath, "`r")
    $null = Invoke-Build 'thrust' -1 @('_RELEASE=-1')
    $flagLines = Get-Content (Join-Path $build 'thrust.txt') | Where-Object { $_ -match '^FLAG (_[A-Z_]+) +(-?\d+)' } |
                 ForEach-Object { $null = $_ -match '^FLAG (_[A-Z_]+) +(-?\d+)'; '  {0,-22} {1}' -f $Matches[1].TrimStart('_').Replace('_', ' '), $(if ($Matches[2] -ne '0') { 'on' } else { 'off' }) }
    $commit = (& git -C $root rev-parse --short HEAD) 2>$null
    $dirty  = if ((& git -C $root status --porcelain) 2>$null) { ' + edits' } else { '' }
    $info = @('Thrust Next', "Built $(Get-Date -Format 'yyyy-MM-dd HH:mm') from $commit$dirty", 'Flags:') + $flagLines
    [IO.File]::WriteAllText($infoPath, ($info -join "`r") + "`r")     # BBC text files end lines with CR
    $swramSsd = Invoke-Build 'thrust' -1 @('_RELEASE=-1')
} else {
    $swramSsd = Invoke-Build 'thrust' -1
}

$origGot  = Get-Crc32 $origSsd
$swramGot = Get-Crc32 $swramSsd
Write-Host "thrust-orig.ssd  $origGot  (must be $OrigCrc)"
Write-Host "thrust.ssd       $swramGot  (SWRAM)"
# The build's own space reports (PRINTs in thrust.6502). The SWRAM bank figure overstates the real
# headroom: the payload travels inside the Thrust file (docs/review-2026-10.md, section 4).
Get-Content (Join-Path $build 'thrust.txt') | Select-String -Pattern 'FREE=' -SimpleMatch | ForEach-Object { Write-Host "  $_" }
if ($origGot -ne $OrigCrc) { throw "original build CRC ${origGot} != ${OrigCrc} - the original game's binary has changed" }

if ($Flags) {
    # Each feature must assemble without the others (CLAUDE.md, "Build flags"). The teleporter's
    # prerequisites can only go with it.
    $sets = @(
        @('_UNROLL_TERRAIN=0'), @('_FRIENDLY_KEYS=0'), @('_THRUST_PARTICLES=0'), @('_NO_WRAP_UNDERGROUND=0'),
        @('_DEBUG_FRAME_TIME=0'), @('_DEBUG_RASTERS=-1'), @('_TIMED_LASER=0'), @('_Y_BANDS=0'),
        @('_BOBBING_MINES=0'), @('_TELEPORTER=0'), @('_SWITCHES=0'),
        @('_GRAVITY_WELL=0', '_TELEPORTER=0'), @('_LAST_USED_CHECKPOINT=0', '_TELEPORTER=0')
    )
    foreach ($set in $sets) {
        $null = Invoke-Build 'flagtest' -1 $set
        Write-Host "  builds with $($set -join ' ')"
    }
    Remove-Item -ErrorAction SilentlyContinue (Join-Path $build 'flagtest.*')
}

if ($Smoke) {
    & node (Join-Path $root 'tools\smoke.mjs') $swramSsd $origSsd > (Join-Path $build 'smoke.json')
    if ($LASTEXITCODE -ne 0) { throw "smoke test failed (exit $LASTEXITCODE), see build/smoke.json" }
    Write-Host "smoke: both discs play all six levels"
    & node (Join-Path $root 'tools\check_laser_clip.mjs') $swramSsd > (Join-Path $build 'check_laser_clip.json')
    if ($LASTEXITCODE -ne 0) { throw "laser clip check failed (exit $LASTEXITCODE), see build/check_laser_clip.json" }
    Write-Host "check_laser_clip: no beam pixels below the screen"
}

if ($Run) {
    $disc = if ($Orig) { $origSsd } else { $swramSsd }
    # b2: -0 FILE drive 0, -b auto-boot; the model and sideways RAM come from b2's own config.
    # beebjit: -autoboot, -swram N per bank (the SWRAM build uses banks 4 and 5).
    if ($Beebjit) {
        $exe = if ($env:BEEBJIT) { $env:BEEBJIT } else { 'D:\tools\beeb\beebjit_win_0.9.5\beebjit.exe' }
        & $exe -0 $disc -autoboot -swram 4 -swram 5
    } else {
        $exe = if ($env:B2) { $env:B2 } else { 'D:\tools\beeb\b2\b2\b2.exe' }
        & $exe -0 $disc -b
    }
}
