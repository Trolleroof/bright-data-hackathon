# Bidex — setup

Twin window + Port / Bright Data stubs and local OpenTelemetry tracing. Demo loop is not built yet.

```bash
cd /Users/nikhi/zero-downtime-hackathon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/check_setup.py
python -m twin.sim
```

## Camera → cube (`track_cube`)

One AprilTag (36h11, id 0) taped flat to the table is the origin. Red = cube.
Every frame: detect the tag, back-project the red blob onto the table plane,
write the result onto the cube in MuJoCo. Walk the camera, the cube stays put.

```bash
python scripts/check_vision.py    # geometry proof, no camera needed
python -m vision.track            # camera + HUD (tag seen / cube x,y / latency)
mjpython -m twin.sim --camera     # twin + track + record + factory + skill
```

Measure the outer black square of the printed tag and put it in `.env` as
`APRILTAG_SIZE_CM` — that is the only scale the pipeline has. Optional camera
tuning (`CAMERA_INDEX`, `CAMERA_FOV_DEG`, `CUBE_TRACK_HEIGHT_CM`) is in
`.env.example`. macOS will ask for camera permission the first time.

With `--camera`, keys go in **this terminal** (not the MuJoCo window):

| Key | Action |
|---|---|
| `R` | Start/stop recording (~3–12 s push) → fast-path factory on stop |
| `F` | Append avoid step from last bag (Run B) |
| `S` | Run the skill spec in sim (after factory PASS) |

Missing sponsor keys = that row says skipped. The sim still opens.

## First-pass skill replay

`outputs/skill_spec.json` is the hot-swappable, version-2 recipe. It supports
`replay_trajectory`, `goto`, and the kinematic `approach` → `grasp`
→ `place` → `release` chain. Validate it without a camera or viewer:

```bash
python scripts/run_skill.py
```

Trajectory times are seconds and must start at zero. A `goto` uses `start`,
`end`, and optional `duration_s` (one second by default). The runner watches
the file and applies a changed spec at a step boundary.

Open the simulated pick-and-place run with:

```bash
python -m twin.sim --skill
```

The blue cursor is the skill engine's table-frame end-effector target. This is
kinematic cube motion; the parked visual arm does not yet have an IK solver.

Fill `.env` when you have them:

| Key | Where |
|---|---|
| `PORT_CLIENT_ID`, `PORT_CLIENT_SECRET` | Port → profile → Credentials |
| `BRIGHTDATA_API_TOKEN`, `BRIGHTDATA_SERP_ZONE`, `BRIGHTDATA_UNLOCKER_ZONE` | Bright Data → API token + a SERP zone + a Web Unlocker zone |
| `APRILTAG_SIZE_CM` | ruler, outer black square after you tape the tag |
