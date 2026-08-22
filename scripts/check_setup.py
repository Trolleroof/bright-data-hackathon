"""Smoke-check the twin scene and the three sponsor stubs. No factory."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mujoco

from integrations.brightdata import smoke as brightdata_smoke
from integrations.config import load_settings
from integrations.port import smoke as port_smoke
from integrations.signoz import smoke as signoz_smoke


def check_twin() -> str:
    scene = ROOT / "twin" / "scene.xml"
    model = mujoco.MjModel.from_xml_path(str(scene))
    mujoco.MjData(model)
    names = {"cube", "apriltag", "target", "ee"}
    found = {
        name
        for name in names
        if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name) >= 0
        or mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name) >= 0
    }
    missing = names - found
    if missing:
        raise RuntimeError(f"scene missing: {sorted(missing)}")
    return f"scene ok ({model.nbody} bodies)"


def check_vision() -> str:
    """Camera stack imports and the tag size is set. Does not open the camera."""
    import cv2  # noqa: PLC0415 — reported as a row, not a hard import

    from vision.tag import TagDetector

    settings = load_settings()
    if settings.apriltag_size_m <= 0:
        return f"opencv {cv2.__version__}. APRILTAG_SIZE_CM not set -> tracking SKIPPED"
    TagDetector(settings.apriltag_size_m)
    return f"opencv {cv2.__version__}, tag {settings.apriltag_size_cm} cm"


def main() -> int:
    settings = load_settings()
    rows: list[tuple[str, str, str]] = []
    failed = False

    checks = [
        ("twin", check_twin),
        ("vision", check_vision),
        ("signoz", signoz_smoke),
        ("port", port_smoke),
        ("brightdata", brightdata_smoke),
    ]
    for name, fn in checks:
        try:
            detail = fn()
            rows.append((name, "OK", detail))
        except Exception as exc:  # noqa: BLE001 — setup report, then exit
            rows.append((name, "FAIL", str(exc)))
            failed = True

    print("Bidex setup")
    print(f"  tag cm: {settings.apriltag_size_cm or '(not set)'}")
    print(f"  keys: signoz={settings.signoz_ready} port={settings.port_ready} brightdata={settings.brightdata_ready}")
    print()
    width = max(len(name) for name, _, _ in rows)
    for name, status, detail in rows:
        print(f"  {name.ljust(width)}  {status:4}  {detail}")
    print()
    print("Next: python scripts/check_vision.py   (track_cube geometry, no camera)")
    print("      python -m vision.track            (camera + HUD)")
    print("      python -m twin.sim --camera       (twin with the cube tracked)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
