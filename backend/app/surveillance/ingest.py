"""
Outbreak time-series ingestion — populates the outbreak_timeseries table.

Usage:
  docker compose exec backend python -m app.surveillance.ingest

Data source:
  Reads the bundled OWID-derived fixture CSV at:
    app/surveillance/data/owid_fixture.csv
  which contains ~358 rows of approximate historical case counts for
  COVID-19, measles, dengue, and cholera across 12 regions.

  Attribution: Our World in Data (CC BY 4.0) — ourworldindata.org
  See app/surveillance/data/NOTES.md for full attribution details.

Idempotency:
  Skips all inserts if the table already contains any rows (same guard as
  the hospital and graph seed scripts).  To re-run from scratch:
    1. Truncate the table: docker compose exec postgres psql -U epiwatch -c
       "TRUNCATE outbreak_timeseries RESTART IDENTITY;"
    2. Then re-run this script.

Design: reading the CSV into memory and bulk-inserting is fine at our scale
(~358 rows).  For a production OWID integration you would stream the
gzip'd CSV from OWID's S3 bucket and use COPY for bulk inserts.
"""
import asyncio
import csv
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.infra.database import get_session_factory
from app.infra.models import OutbreakTimeSeries

logger = logging.getLogger(__name__)
FIXTURE = Path(__file__).parent / "data" / "owid_fixture.csv"


def _parse_row(row: dict) -> OutbreakTimeSeries:
    return OutbreakTimeSeries(
        disease_name=row["disease_name"].strip(),
        region=row["region"].strip(),
        date=date.fromisoformat(row["date"].strip()),
        case_count=int(row["case_count"]),
        deaths=int(row["deaths"]),
        source=row["source"].strip(),
    )


async def ingest(path: Path = FIXTURE) -> int:
    """
    Load outbreak time-series from path into the DB.
    Returns the number of rows inserted (0 if already seeded).
    """
    async with get_session_factory()() as db:
        existing = await db.execute(select(OutbreakTimeSeries).limit(1))
        if existing.scalar_one_or_none() is not None:
            logger.info("outbreak_timeseries already seeded — skipping")
            return 0

        if not path.exists():
            raise FileNotFoundError(f"fixture not found: {path}")

        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = [_parse_row(r) for r in reader]

        for obj in rows:
            db.add(obj)
        await db.commit()

        by_disease: dict[str, int] = {}
        for obj in rows:
            by_disease[obj.disease_name] = by_disease.get(obj.disease_name, 0) + 1

        logger.info("ingested %d outbreak time-series rows", len(rows))
        for disease, count in sorted(by_disease.items()):
            logger.info("  %-20s %d rows", disease, count)

        return len(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    n = asyncio.run(ingest())
    if n == 0:
        print("already seeded — nothing to do")
    else:
        print(f"ingested {n} rows — done")


if __name__ == "__main__":
    main()
