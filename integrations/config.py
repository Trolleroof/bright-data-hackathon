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
    brightdata_collector_id: str
    brightdata_catalog_url: str
    apriltag_size_cm: str

    @property
    def signoz_ready(self) -> bool:
        return bool(self.signoz_endpoint and self.signoz_ingestion_key)

    @property
    def port_ready(self) -> bool:
        return bool(self.port_client_id and self.port_client_secret)

    @property
    def brightdata_ready(self) -> bool:
        return bool(self.brightdata_api_token and self.brightdata_collector_id)


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
        brightdata_collector_id=os.getenv("BRIGHTDATA_COLLECTOR_ID", "").strip(),
        brightdata_catalog_url=os.getenv(
            "BRIGHTDATA_CATALOG_URL",
            "https://www.ikea.com/us/en/p/ikea-365-water-bottle-dark-gray-70478228/",
        ).strip(),
        apriltag_size_cm=os.getenv("APRILTAG_SIZE_CM", "").strip(),
    )
