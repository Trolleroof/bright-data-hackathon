# ScaleTwin — setup

Twin window + Port / SigNoz / Bright Data stubs. Factory is not built yet.

```bash
cd /Users/nikhi/zero-downtime-hackathon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/check_setup.py
python -m twin.sim
```

Missing sponsor keys = that row says skipped. The sim still opens.

Fill `.env` when you have them:

| Key | Where |
|---|---|
| `SIGNOZ_ENDPOINT`, `SIGNOZ_INGESTION_KEY` | SigNoz → Settings → Ingestion |
| `PORT_CLIENT_ID`, `PORT_CLIENT_SECRET` | Port → profile → Credentials |
| `BRIGHTDATA_API_TOKEN`, `BRIGHTDATA_COLLECTOR_ID` | Bright Data → API token + Scraper Studio collector `c_…` |
| `APRILTAG_SIZE_CM` | ruler, outer black square after you tape the tag |
