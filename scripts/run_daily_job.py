#!/usr/bin/env python3
"""Entry point for the daily scheduled run (invoked by GitHub Actions).

Requires these environment variables (set as GitHub Actions secrets):
    ANTHROPIC_API_KEY, RAPIDAPI_KEY, ADZUNA_APP_ID, ADZUNA_APP_KEY,
    HF_TOKEN, HF_DATASET_REPO
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import run_daily_search, NoProfileError  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("run_daily_job")


def main() -> int:
    try:
        result = run_daily_search()
    except NoProfileError as e:
        log.warning(str(e))
        return 0  # not an error: just nothing to do until a resume is uploaded
    except Exception:
        log.exception("Daily job search failed")
        return 1

    log.info(
        "Done. candidates_found=%d unseen_after_dedupe=%d final_count=%d",
        result["candidates_found"],
        result["unseen_after_dedupe"],
        result["final_count"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
