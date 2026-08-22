from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    signoz_endpoint: str
    signoz_ingestion_key: str
    otel_service_name: str
    port_client_id: str
    port_client_secret: str
    port_api_url: str
    brightdata_api_token: str
    brightdata_serp_zone: str
    brightdata_unlocker_zone: str
    brightdata_catalog_url: str
    apriltag_size_cm: str
    camera_index: int
    camera_fov_deg: float
    camera_width: int
    camera_height: int
    cube_track_height_cm: float
    cube_size_cm: float

    @property
    def apriltag_size_m(self) -> float:
        """Tag size in metres. 0.0 means .env has no APRILTAG_SIZE_CM."""
        try:
            return float(self.apriltag_size_cm) / 100.0
        except ValueError:
            return 0.0

    @property
    def signoz_ready(self) -> bool:
        return bool(self.signoz_endpoint and self.signoz_ingestion_key)

    @property
    def port_ready(self) -> bool:
        return bool(self.port_client_id and self.port_client_secret)

    @property
    def brightdata_ready(self) -> bool:
        return bool(
            self.brightdata_api_token and self.brightdata_serp_zone and self.brightdata_unlocker_zone
        )


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    return Settings(
        signoz_endpoint=os.getenv("SIGNOZ_ENDPOINT", "").strip(),
        signoz_ingestion_key=os.getenv("SIGNOZ_INGESTION_KEY", "").strip(),
        otel_service_name=os.getenv("OTEL_SERVICE_NAME", "bidex").strip() or "bidex",
        port_client_id=os.getenv("PORT_CLIENT_ID", "").strip(),
        port_client_secret=os.getenv("PORT_CLIENT_SECRET", "").strip(),
        port_api_url=os.getenv("PORT_API_URL", "https://api.port.io/v1").strip(),
        brightdata_api_token=os.getenv("BRIGHTDATA_API_TOKEN", "").strip(),
        brightdata_serp_zone=os.getenv("BRIGHTDATA_SERP_ZONE", "serp_api1").strip(),
        brightdata_unlocker_zone=os.getenv("BRIGHTDATA_UNLOCKER_ZONE", "").strip(),
        brightdata_catalog_url=os.getenv("BRIGHTDATA_CATALOG_URL", "").strip(),
        apriltag_size_cm=os.getenv("APRILTAG_SIZE_CM", "").strip(),
        camera_index=_int("CAMERA_INDEX", 0),
        camera_fov_deg=_float("CAMERA_FOV_DEG", 60.0),
        camera_width=_int("CAMERA_WIDTH", 1280),
        camera_height=_int("CAMERA_HEIGHT", 720),
        cube_track_height_cm=_float("CUBE_TRACK_HEIGHT_CM", 2.5),
        cube_size_cm=_float("CUBE_SIZE_CM", 5.0),
    )
