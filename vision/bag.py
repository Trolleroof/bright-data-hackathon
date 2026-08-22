"""Physical prompt bags: what the factory reads after you stop recording."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrations.config import ROOT

RECORDINGS_DIR = ROOT / "recordings"
BAG_VERSION = 1


@dataclass(frozen=True)
class BagFrame:
    t: float
    cube_xy: tuple[float, float] | None
    obstacle_xy: tuple[float, float] | None
    tag_seen: bool


@dataclass
class PromptBag:
    frames: list[BagFrame]
    started_at: str
    duration_s: float
    bag_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": BAG_VERSION,
            "bag_id": self.bag_id,
            "started_at": self.started_at,
            "duration_s": round(self.duration_s, 3),
            "frame_count": len(self.frames),
            "frames": [
                {
                    "t": round(frame.t, 4),
                    "cube_xy": list(frame.cube_xy) if frame.cube_xy else None,
                    "obstacle_xy": list(frame.obstacle_xy) if frame.obstacle_xy else None,
                    "tag_seen": frame.tag_seen,
                }
                for frame in self.frames
            ],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PromptBag:
        if raw.get("version") != BAG_VERSION:
            raise ValueError(f"unsupported bag version: {raw.get('version')!r}")
        frames: list[BagFrame] = []
        for item in raw.get("frames") or []:
            cube = item.get("cube_xy")
            obstacle = item.get("obstacle_xy")
            frames.append(
                BagFrame(
                    t=float(item["t"]),
                    cube_xy=(float(cube[0]), float(cube[1])) if cube else None,
                    obstacle_xy=(float(obstacle[0]), float(obstacle[1])) if obstacle else None,
                    tag_seen=bool(item.get("tag_seen")),
                )
            )
        return cls(
            frames=frames,
            started_at=str(raw.get("started_at", "")),
            duration_s=float(raw.get("duration_s", 0.0)),
            bag_id=str(raw.get("bag_id", "unknown")),
        )


def new_bag_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"bag_{stamp}"


def save_bag(bag: PromptBag, path: Path | None = None) -> Path:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    target = path or (RECORDINGS_DIR / f"{bag.bag_id}.json")
    target.write_text(json.dumps(bag.to_dict(), indent=2) + "\n")
    return target


def load_bag(path: str | Path) -> PromptBag:
    return PromptBag.from_dict(json.loads(Path(path).read_text()))
