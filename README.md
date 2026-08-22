# Bidex

Show a table move once. The twin learns it and keeps running.

The camera sees **where** things are, not **what** they are or **how big** they are. Bright Data fills that from the live web. Port turns the recording into a shipped skill — no typed ticket.

```
R record → factory → (F: Bright Data + avoid) → Port sync → replay → S play
```

Missing sponsor keys = that step skips. The twin still opens.

---

## Bright Data — web eyes (Run B only)

A not-red blob is just `(x, y)`. Bright Data turns a label like `"water bottle"` into physics the twin can use.

| Call | API | Returns | When |
|---|---|---|---|
| `search()` | SERP zone | product / mesh URLs | `F` |
| `fetch()` | Web Unlocker | HTML past anti-bot walls | `F` |
| `extract()` | local | `{name, width_cm, height_cm, weight_g, material}` | after fetch |
| mesh ladder | SERP + Unlocker | `.glb` / `.stl` from web | after scrape |

Skill A (`R` only) **never** scrapes — hands look like obstacles. Press **`F`** for Run B. Fixture fallback is labelled on the HUD, never silent.

---

## Port — job board for a physical prompt

Each factory run writes a linked graph in Port (`sync_fast_path_run`):

| Blueprint | What it is |
|---|---|
| `physical_prompt` | the bag — ticket opens when you stop recording |
| `change_request` | stage + summary (`pick_and_place -> PASS in 12 ms`) |
| `factory_run` | skill + pass/fail |
| `scraper_job` | **Run B only** — catalog URL + dimensions from Bright Data |
| `approval` | replay exam result |
| `twin_release` | hot-swapped spec (only if replay passed) |

Replay fail ⇒ no release. No Port keys ⇒ factory still runs locally.

---

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/check_setup.py
```

Print `print/apriltag_36h11_id0_letter.png` at **100%**. Tape flat. Measure outer black square → `APRILTAG_SIZE_CM` (letter print = 15.3 cm).

---

## Demo loop

```bash
mjpython -m twin.sim --camera
```

Keys in **this terminal**, not the MuJoCo window:

| Key | Action |
|---|---|
| `R` | Record 3–20 s → factory. No Bright Data. |
| `F` | Run B: scrape blob, append `avoid`, Port `scraper_job`. |
| `S` | Play `outputs/skill_spec.json`. |

Headless proofs: `python scripts/check_vision.py`, `run_factory.py --smoke`, `run_skill.py`, `twin.sim --skill`.

---

## Browser

```bash
python web/server.py --twin --camera    # :8080
cd web && npm install && npm run dev    # :3000
```

**LIVE OPS** — twin + camera. **FLIGHT RECORDER** — trace waterfall + check runner.

---

## Keys

| Key | Where |
|---|---|
| `PORT_CLIENT_ID`, `PORT_CLIENT_SECRET` | Port → Credentials |
| `BRIGHTDATA_API_TOKEN` | Bright Data → API token |
| `BRIGHTDATA_SERP_ZONE`, `BRIGHTDATA_UNLOCKER_ZONE` | Proxies & Scraping → zone names |
| `APRILTAG_SIZE_CM` | ruler, after taping tag |

Optional: `BRIGHTDATA_CATALOG_URL` — skip search, unlock one page only.
