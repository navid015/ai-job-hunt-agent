"""Orchestrates one end-to-end daily job-search run.

Steps: load resume profile -> query job source APIs -> drop jobs already
recommended in the memory window -> score/rank the rest with Claude -> keep
the top N -> persist results and mark them as seen.
"""

import logging

from src.config import DAILY_JOB_COUNT, MAX_SEARCH_QUERIES_PER_RUN
from src.history_store import (
    load_profile,
    filter_unseen,
    mark_as_seen,
    save_latest_results,
)
from src.job_ranker import rank_jobs
from src.job_sources import search_all_sources

log = logging.getLogger(__name__)


class NoProfileError(RuntimeError):
    """Raised when the daily job runs before any resume has been uploaded/analyzed."""


def run_daily_search(top_n: int = DAILY_JOB_COUNT) -> dict:
    profile = load_profile()
    if not profile:
        raise NoProfileError(
            "No resume profile found yet. Upload and analyze a resume in the app first."
        )

    queries = profile.get("target_titles") or profile.get("search_keywords") or []
    if not queries:
        raise RuntimeError("Resume profile has no search keywords/titles to search with.")
    # target_titles is ordered best-fit first; capping keeps job-source API usage
    # (esp. JSearch's free-tier request quota) sustainable for a daily cron job.
    queries = queries[:MAX_SEARCH_QUERIES_PER_RUN]

    log.info("Searching job sources with %d queries...", len(queries))
    candidates = search_all_sources(queries, num_pages=1)
    log.info("Fetched %d raw candidate jobs.", len(candidates))

    unseen = filter_unseen(candidates)
    log.info("%d jobs remain after removing previously recommended ones.", len(unseen))

    ranked = rank_jobs(profile, unseen, top_n=top_n)
    log.info("Selected top %d jobs after scoring.", len(ranked))

    save_latest_results(ranked)
    if ranked:
        mark_as_seen(ranked)

    return {
        "candidates_found": len(candidates),
        "unseen_after_dedupe": len(unseen),
        "final_count": len(ranked),
        "jobs": ranked,
    }
