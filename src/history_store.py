"""Shared persistence for the resume profile, seen-job history, and latest results.

The Gradio Space (interactive, resume upload) and the daily scheduled job
(GitHub Actions, no UI) both need to read/write the same state. We use a
private Hugging Face Hub *dataset* repo as that shared store. If HF_DATASET_REPO
isn't configured, we fall back to a local JSON directory so the app still works
for local development.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from src.config import (
    HF_TOKEN,
    HF_DATASET_REPO,
    LOCAL_DATA_DIR,
    RESUME_PROFILE_FILE,
    SEEN_JOBS_FILE,
    LATEST_RESULTS_FILE,
    SEEN_JOB_MEMORY_DAYS,
)

log = logging.getLogger(__name__)


def _use_hub() -> bool:
    return bool(HF_TOKEN and HF_DATASET_REPO)


def _local_path(filename: str) -> str:
    os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
    return os.path.join(LOCAL_DATA_DIR, filename)


def _read_json(filename: str, default):
    if _use_hub():
        try:
            from huggingface_hub import hf_hub_download

            path = hf_hub_download(
                repo_id=HF_DATASET_REPO,
                repo_type="dataset",
                filename=filename,
                token=HF_TOKEN,
            )
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.info("No existing %s on the Hub yet (%s); using default.", filename, e)
            return default

    path = _local_path(filename)
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(filename: str, data) -> None:
    if _use_hub():
        from huggingface_hub import HfApi
        import tempfile

        api = HfApi(token=HF_TOKEN)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=2)
            tmp_path = tmp.name
        api.upload_file(
            path_or_fileobj=tmp_path,
            path_in_repo=filename,
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
            token=HF_TOKEN,
            commit_message=f"Update {filename}",
        )
        os.remove(tmp_path)
        return

    path = _local_path(filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# --- Resume profile ---

def load_profile() -> dict | None:
    return _read_json(RESUME_PROFILE_FILE, None)


def save_profile(profile: dict) -> None:
    _write_json(RESUME_PROFILE_FILE, profile)


# --- Seen-job history (for "never repeat what I recommended before") ---

def load_seen_jobs() -> dict:
    """Returns {job_id: date_first_shown_iso}."""
    return _read_json(SEEN_JOBS_FILE, {})


def filter_unseen(jobs: list[dict]) -> list[dict]:
    """Drop any job whose id was already recommended within SEEN_JOB_MEMORY_DAYS."""
    seen = load_seen_jobs()
    cutoff = datetime.now(timezone.utc) - timedelta(days=SEEN_JOB_MEMORY_DAYS)
    unseen = []
    for job in jobs:
        shown_at = seen.get(job["id"])
        if shown_at:
            try:
                if datetime.fromisoformat(shown_at) > cutoff:
                    continue
            except ValueError:
                continue
        unseen.append(job)
    return unseen


def mark_as_seen(jobs: list[dict]) -> None:
    seen = load_seen_jobs()
    now_iso = datetime.now(timezone.utc).isoformat()
    for job in jobs:
        seen[job["id"]] = now_iso

    # prune anything far outside the memory window so the file doesn't grow forever
    cutoff = datetime.now(timezone.utc) - timedelta(days=SEEN_JOB_MEMORY_DAYS * 3)
    pruned = {}
    for job_id, ts in seen.items():
        try:
            if datetime.fromisoformat(ts) > cutoff:
                pruned[job_id] = ts
        except ValueError:
            continue

    _write_json(SEEN_JOBS_FILE, pruned)


# --- Latest results (what the Gradio UI displays) ---

def save_latest_results(jobs: list[dict]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(jobs),
        "jobs": jobs,
    }
    _write_json(LATEST_RESULTS_FILE, payload)


def load_latest_results() -> dict:
    return _read_json(LATEST_RESULTS_FILE, {"generated_at": None, "count": 0, "jobs": []})
