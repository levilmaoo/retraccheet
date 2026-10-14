# Simulation Lab 1.0.0

Standalone desktop player-visualization and camera simulation for Windows x64.
The intended future local test environment is **Project Reboot / Fortnite 14.60**.
**Live Fortnite integration is unavailable and has not been tested.**

## Delivery status

- Implemented: synthetic moving players, boxes, skeletons, health bars, names,
  distances, tracers, selection FOV circle, target filtering, selection priorities,
  simulation camera following, smoothing, camera movement and projection, graphical
  settings tabs, pause/reset, persistent settings, and diagnostic logs.
- Local automated validation: 20 mathematical, selection, simulation, profile,
  and persistence tests passed on macOS with Python 3.9.6.
- Windows workflow: prepared at `../.github/workflows/simulation-lab-windows.yml`.
  It tests the source GUI, builds a single-file executable, checks its AMD64 PE
  header, launches the executable, tests settings persistence, and uploads artifacts.
- Windows CI run [#1](https://github.com/levilmaoo/retraccheet/actions/runs/38496865969)
  **passed** on Windows Server 2022 x64: all 20 logic tests, source GUI startup,
  executable packaging, AMD64 PE verification, and packaged GUI smoke testing.
  A [Windows executable package](https://github.com/levilmaoo/retraccheet/actions/runs/38496865969/artifacts/11863896340)
  was produced. Use the latest successful run's artifact for updated documentation.
  Windows 10/11 visual acceptance and the manual checks below remain pending.
- Workspace inspection found no authorized Unreal SDK, debug symbols, source
  integration, offsets, or game-state interface. The existing root project is an
  unrelated Twilio utility; it was left unchanged.

This app renders exclusively in its own window. It does not attach to Fortnite,
read or write another process, inject code, send game input, or interact with
anti-cheat. Anti-cheat bypass and stealth injection are not implemented.

## Windows tester: get and launch the build

1. Open [the repository's Windows build workflow](https://github.com/levilmaoo/retraccheet/actions/workflows/simulation-lab-windows.yml).
   The app and workflow are already published. If using your own repository,
   retain the `simulation-lab/` layout and the root `.github/workflows` workflow.
   Do not upload unrelated private workspace files.
2. Select the latest successful run. To build a fresh copy, select **Run workflow**.
   A push or pull request changing these files also triggers it.
3. Only accept a successful run. Download **SimulationLab-Windows-x64** from that
   run's Artifacts section and extract the ZIP to a normal user-writable folder.
4. In PowerShell, run `Get-FileHash .\SimulationLab.exe -Algorithm SHA256` and
   compare it with `SHA256.txt` from the same artifact.
5. Launch `SimulationLab.exe`. Python does not need to be installed for the
   packaged executable. The build is unsigned; your Windows policy may require
   an approved code-signing process before distribution. Do not disable endpoint
   protection to run it.
6. Confirm the title says **SIMULATED PLAYERS**, the header says Fortnite
   integration is unavailable, and the canvas says **SIMULATED DATA ONLY**.
   Fortnite does not need to be running.

Target test systems: Windows 10/11 x64 with a desktop session. Windows ARM64,
32-bit Windows, compatibility layers, and Remote Desktop rendering are untested.
No administrator rights are required.

## Controls and settings

The menu has **Visuals**, **Targets**, and **Scene** tabs. Settings save automatically
400 ms after the last change and again at exit.

| Control | Effect |
| --- | --- |
| Click scene, then W/A/S/D | Move forward/left/back/right in the simulation |
| Q / E | Move camera down / up |
| Left-button drag | Look around; temporarily takes precedence over following |
| Space / Pause button | Pause actor motion; camera remains interactive |
| R / Reset scene | Restore deterministic scene and camera; retain settings |
| Escape / loss of focus | Clear held movement keys |
| Restore default settings | Reset settings and scene, then save |
| Follow with simulation camera | Smoothly rotate this app's camera toward selected target |

Visualization annotations can be toggled independently. Blue denotes teammates,
pink denotes opponents, gray denotes synthetic occlusion, and gold denotes the
selected target. Underlying simulated actors remain drawn when annotations are
disabled. Health and visibility are generated test data, not observed game state.
Actors beyond maximum distance are omitted from visualization and selection.

Selection requires a living player within maximum distance, inside the viewport,
and inside the selection cone. Visibility and teammate eligibility are separately
configurable. Crosshair prioritizes angular error; Distance prioritizes world
distance; Health prioritizes lowest health. Equal scores resolve by player ID.
Head and Chest select different synthetic aim points.

**Selection FOV** is the full cone angle in degrees. **Camera FOV** is horizontal
FOV in degrees, independent of viewport aspect ratio. Smoothing is an exponential
time constant in seconds: lower values follow faster. Updates use elapsed time
to maintain equivalent smoothing across frame rates. Long stalls are capped to
50 ms per frame to avoid large jumps. Target selection is recomputed each frame.
Player count supports 1–64; changing count resets the synthetic scene. Speed 0
freezes actor motion without pausing camera interaction.

## Persistence and diagnostics

Default location: `%LOCALAPPDATA%\SimulationLab\`.

- `settings.json`: schema version 1; validated ranges and types; atomic replacement.
- `settings-invalid-<timestamp>.json`: preserved rejected configuration, when the
  filesystem permits it. The app falls back to defaults and displays a warning.
- `application.log`: initialization warnings, callback errors, save failures.

For an isolated manual test:

```powershell
.\SimulationLab.exe --settings-dir .\tester-settings
```

Do not place test settings in a protected installation directory. A save error
appears below the menu and is logged. Use **Profile / tester help** to find the
active settings path and integration status.

## Manual acceptance checklist

Record Windows version, display resolution/scaling, artifact run URL, executable
SHA256, observed frame rate, and any logs. Test at 100%, 150%, and 200% scaling
where available, including resizing and maximizing.

1. Open all three menu tabs. Verify all controls are accessible with no clipping.
2. Toggle each visualization control. Confirm its annotation appears/disappears
   while underlying actors remain. Confirm the selection circle resizes with FOV.
3. Disable camera follow initially. Narrow/widen selection FOV and change maximum
   distance. Confirm selected actors meet the limits and offscreen actors cannot
   be selected. Turn visibility and teammate filters on/off; verify eligible
   targets change. Try all three selection priorities and both aim points.
4. Enable follow. Compare smoothing 0.02 versus 2 seconds. Verify camera turns
   faster at 0.02 and stays stable when no target is eligible. Drag the view and
   confirm follow resumes after releasing the mouse.
5. Change camera FOV from 40 to 120. Resize the window. Check boxes and skeletons
   stay aligned with synthetic actors and the circle stays centered.
6. Click the canvas, hold each movement key, release it, and change focus while a
   key is held. Verify no stuck movement. Try drag, pause, resume, and reset.
7. Set 64 players and speed 3; run for ten minutes and monitor frame rate and logs.
   There is no claimed performance threshold until tested on target hardware.
8. Change several settings, exit normally, restart, and confirm they persist.
   In a separate `tester-settings` directory, replace `settings.json` with invalid
   JSON, restart, and verify warning/default recovery and backup preservation.
9. Run with a directory where the tester lacks write access and verify a clear
   failure rather than silently claiming that settings saved.
10. Confirm no Fortnite integration claim is shown anywhere. Running alongside a
    local game does not establish live integration; the actors remain synthetic.

Packaged automated smoke test (isolated settings; writes a JSON result):

```powershell
$app = Start-Process .\SimulationLab.exe -ArgumentList '--settings-dir smoke-settings --smoke-test smoke-result.json' -PassThru
$app.WaitForExit()
Get-Content .\smoke-result.json
```

A passing result verifies startup, a populated canvas, settings controls, actor
count changes, pause, default restoration, configuration round-trip, and profile
truthfulness. It does not replace visual acceptance or game integration testing.

## Build locally on Windows x64

Use an x64 Python 3.12 installation with Tk support. From this directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe app.py --settings-dir source-test-settings
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name SimulationLab --add-data "profiles;profiles" app.py
.\.venv\Scripts\python.exe verify_pe.py dist/SimulationLab.exe
```

Output: `dist\SimulationLab.exe`. Build with a Windows interpreter: PyInstaller
is not a cross-compiler ([official documentation](https://pyinstaller.org/en/stable/operating-mode.html)).
Tk is part of the standard Python desktop distribution
([Python documentation](https://docs.python.org/3/library/tkinter.html)).
The CI build dependency is pinned; the Python runtime and GitHub actions use
version tags and may receive patch updates. Builds are not claimed bit-reproducible.

## Fortnite 14.60 integration requirements

`profiles/fortnite-14.60.json` records the intended version, missing requirements,
empty verified source/offset lists, and an explicit untested status. It is bundled
as a resource and displayed by the app. It does not enable live integration.

A future authorized integration needs a version-matched, documented game-state
interface or instrumented source build exposing player positions, teams, health,
visibility, camera position/orientation, coordinate units, and FOV convention.
Structure layouts must be verified against that exact build where applicable.
Nothing in this simulation establishes Unreal or Fortnite layout compatibility.

Before any live integration claim, run known fixtures through projection and
selection and record successful tests against the intended local game build.
No invented offsets, fallback offsets from other versions, injection, or
anti-cheat bypass are included.
