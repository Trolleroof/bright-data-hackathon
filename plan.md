**Bidex**

A generalizable live twin: one short table demo becomes new sim behavior in seconds, without pausing.

---

## Problem

Teaching a robot a new move usually means weeks of engineering, or a giant model like GEN-1.5.

GEN-1.5: show one 8-second demo → the model does the skill in seconds. We cannot train that model. We also cannot drive a real arm.

If we only track a red cube in sim, nothing adapts. If we only run a ticket board, nothing physical happens. If we **codegen new Python every run**, each skill takes minutes and does not scale.

**The gap:** new table situations should work from one demo, fast and repeatable, while the live twin stays up.

---

## Solution

Copy GEN-1.5’s *interface*, not its brain.

**Generalization = composable primitives + params, not new code every time.**

You record ~8 seconds. The factory extracts **parameters** from the bag, fills a skill spec, tests on replay, and hot-swaps. The twin never stops.

| GEN-1.5 | Bidex |
|---|---|
| One demo in model memory | One demo → param JSON |
| Composes prompts A + B | Composes primitives `goto` + `avoid` |
| Seconds to adapt | **Fast path: ~15–30 s** after recording |
| Pretrained weights | Fixed engine + web lookup |

No real robot. No neural policy. Detection = color + one AprilTag.

---

## Skill primitives (the engine)

Skills are **not** hardcoded moves and **not** new Python per run. They are params fed into fixed templates:

| Primitive | Input | What it does |
|---|---|---|
| `track_cube` | red blob x,y each frame | Keeps cube planted in MuJoCo |
| `replay_trajectory` | `[[x, y, t], ...]` from recording bag | Replays recorded push path (Run A primary) |
| `goto` | start + end from recording bag | Simple push A → target (fallback) |
| `approach` | `[x, y]` + `height_cm` | EE over cube before grasp |
| `grasp` | — | Kinematic attach: cube follows end-effector |
| `place` | `[x, y, z]` | Move attached cube to target pose |
| `release` | — | Detach cube onto table |
| `avoid` | not-red x,y + Bright Data `{name, width_cm, height_cm}` | Spawns geom, reroutes around it |
| `compose` | ordered list of primitives | Chains A, then B, then C… |

**Example skill spec (what gets hot-swapped):**

```json
{
  "version": 2,
  "steps": [
    { "op": "replay_trajectory", "path": [[0, 0, 0], [0.28, 0.18, 2.0]] },
    { "op": "avoid", "at": [-0.12, 0.05], "catalog_url": "…", "geom": "cylinder" }
  ]
}
```

**Pick-and-place (Run C or alternate demo):**

```json
{
  "version": 2,
  "steps": [
    { "op": "approach", "at": [0, 0], "height_cm": 8 },
    { "op": "grasp" },
    { "op": "place", "at": [0.28, 0.18, 0] },
    { "op": "release" }
  ]
}
```

Adding skill C = append one step to this JSON. Same engine. That is generalizable.

---

## Fast path vs slow path

| Path | When | Time | What runs |
|---|---|---|---|
| **Fast** | Recording matches a known primitive (`replay_trajectory`, `goto`, pick-and-place chain, `avoid`, `compose`) | ~15–30 s | Extract waypoints → scrape if new blob → patch spec → replay → ship |
| **Slow** | Weird motion or extraction fails | ~2–4 min | Planner + implementer agents edit templates or selectors, then same replay gate |

Demo default: **fast path**. Slow path is backup + scraper-repair beat.

LLM agents are for **repair and novelty**, not every happy-path skill.

---

## How the table knows anything

The camera does **not** recognize “bottle.”

| Thing | How we know | Used for |
|---|---|---|
| Where the table is | One AprilTag, taped down | Origin + scale |
| Red blob | Color | Cube position |
| Not-red blob | Color | New object at x,y |
| Name + size | Bright Data scrape | Geom dimensions in sim |
| What to do | Primitive rules | `replay_trajectory` / `goto` from motion, pick-and-place from grasp segment, `avoid` for any new blob |

**Demo contract:** water bottle on the table for run B. Scraper aimed at one catalog URL in `brightdata/rules.yaml`. Position from camera. Centimeters from the web.

You do not type “avoid the bottle.” Ending the recording writes the ticket.

“Bring in” = spawn name+size in MuJoCo. Real bottle stays put. Virtual arm steers around it.

---

## What each tool does

**Twin (the body)**  
MuJoCo + HUD. Always on. Runs the **primitive engine** from the current skill spec. Camera pose, cube, obstacles, virtual arm.

**Physical prompt (the teaching)**  
Record 3–12 s, then stop. Bag → waypoint extraction + Port ticket. Walking the camera alone is not a prompt.

**SigNoz (alarm + black box)**  
`physical_prompt` when recording ends. Spans: `detect`, `tag_pose`, `update_twin`, `extract_params`, `scrape`, `patch_spec`, `test`, `approve`, `skill_exec`. Judges read the timeline, not a dashboard tour.

**Port (job board)**  
Stages: prompt → extract → scrape → patch → test → **Approve** → release. Tracks `PhysicalPrompt`, `ChangeRequest`, `FactoryRun`, `ScraperJob`, `TwinRelease`. Agents on slow path only: planner, implementer, tester, scraper-repair. Approve ships the new spec. Walk the camera during Approve = zero downtime.

**Bright Data (lookup)**  
Scrapes one public catalog URL. Returns `{ name, width_cm, height_cm }`. Does not see the camera. Any object with a catalog page works — same pipeline for bottle, tape, cup. Scraper-repair edits selectors in `brightdata/rules.yaml` if the page breaks.

**Replay bag (exam)**  
Tests the spec against the recording, not your live hand. Pass → Approve. Play again after ship to prove it was not a one-off.

---

## Demo (minimum: 2 prompts, composable to N)

**Run A — `goto`**
1. Walk camera. Push cube. Twin tracks.
2. Record ~8 s: push cube to target. `PROMPTED` → SigNoz → Port.
3. Fast path patches `goto` params. Approve. Walk camera while Approve is up.
4. Virtual arm runs `goto` alone.

**Run B — `compose(goto, avoid)`**
1. Drop bottle. End prompt.
2. Bright Data fills size. Fast path appends `avoid` step.
3. Approve. Show scraper break + repair once (slow path or forced selector break).
4. Arm: target **and** around bottle. Replay works a second time.

**Optional run C — pick-and-place**  
Record: approach cube, lift, set on target. Fast path fills `approach` → `grasp` → `place` → `release`. Same Approve + hot-swap loop.

**Optional run D+**  
Same loop. New primitive step or new obstacle. Still one engine, longer `compose` chain. Keep demo to 2–3 runs max for judges unless pick-and-place replaces Run A.

Backup if alert dies: start the same request in Port by hand.

---

## Table setup (one tag)

Print `print/apriltag_36h11_id0_letter.png` at **100%**. Off: fit-to-page.

```
back of table
[TAG]                    [TARGET tape square]

         [RED CUBE]

[you + camera]
front of table
```

1. Tape **flat** at **back-left**. White margin only. No tape on black square.
2. Cube center. No tag on cube.
3. Target = taped square, back-right.
4. Bottle off table until run B. Then left of cube.
5. Measure outer black square in cm → `APRILTAG_SIZE_CM` in `.env`.

Tag must stay in frame. Do not move it after taping.

---

## Do not build

- Real robot control
- NeRF / 3D reconstruction
- Policy training / foundation model claims
- New Python file per skill (params only on happy path)
- Vision that classifies object type

---

## Done when

- Cube stays planted when you walk the camera
- Recording → params → spec patch in **&lt; 30 s** on fast path
- Ending a recording opens Port with no typed ticket
- Bottle size from Bright Data JSON; auto-repair shown once
- Replay gates Approve; camera-move during ship proves zero downtime
- `compose(replay, avoid)` works; pick-and-place chain works; replay succeeds twice
- SigNoz alone explains both runs
- Adding run C is “append a step,” not a rewrite

---

## Pitch (say this)

> GEN-1.5 generalizes by pretraining.  
> Bidex generalizes by **composable primitives**: show once, extract params, scrape size from the web, ship without downtime.  
> Same engine for any catalog object. More skills = longer compose chain, not new code.  
> Port shows the run. SigNoz shows the proof.
