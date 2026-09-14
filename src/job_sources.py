"""Clients for legitimate job-search APIs.

We do NOT scrape LinkedIn/Indeed/Glassdoor/Monster/ZipRecruiter directly --
their Terms of Service prohibit it and it breaks constantly. Instead we query
aggregator APIs that legally syndicate listings from those same boards:

- JSearch (via RapidAPI): aggregates LinkedIn, Indeed, Glassdoor, ZipRecruiter,
  Monster, and many company career pages.
- Adzuna: an independent job-search API covering thousands of US employers and
  boards, used here as a second, complementary source.

Both return a normalized list of job dicts:
    {id, title, company, location, description, url, posted_date, source, remote}
"""

import hashlib
import logging

import requests

from src.config import RAPIDAPI_KEY, ADZUNA_APP_ID, ADZUNA_APP_KEY, JOB_SEARCH_COUNTRY

log = logging.getLogger(__name__)

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"
ADZUNA_URL_TEMPLATE = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def _job_id(source: str, title: str, company: str, location: str, native_id: str = "") -> str:
    if native_id:
        return f"{source}:{native_id}"
    raw = f"{source}|{title}|{company}|{location}".lower().strip()
    return f"{source}:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def search_jsearch(query: str, num_pages: int = 1, date_posted: str = "week") -> list[dict]:
    """Query JSearch (RapidAPI) for a single search phrase."""
    if not RAPIDAPI_KEY:
        log.info("RAPIDAPI_KEY not set, skipping JSearch.")
        return []

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query": f"{query} in United States",
        "page": "1",
        "num_pages": str(num_pages),
        "date_posted": date_posted,  # "today" | "3days" | "week" | "month"
        "country": "us",
    }

    try:
        resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        log.warning("JSearch request failed for query=%r: %s", query, e)
        return []

    jobs = []
    for item in data.get("data", []):
        title = item.get("job_title", "")
        company = item.get("employer_name", "")
        location = ", ".join(
            filter(None, [item.get("job_city"), item.get("job_state"), item.get("job_country")])
        )
        jobs.append(
            {
                "id": _job_id("jsearch", title, company, location, item.get("job_id", "")),
                "title": title,
                "company": company,
                "location": location or "United States",
                "description": (item.get("job_description") or "")[:4000],
                "url": item.get("job_apply_link") or item.get("job_google_link") or "",
                "posted_date": item.get("job_posted_at_datetime_utc", ""),
                "source": item.get("job_publisher", "JSearch"),
                "remote": bool(item.get("job_is_remote")),
            }
        )
    return jobs


def search_adzuna(query: str, results_per_page: int = 20) -> list[dict]:
    """Query the Adzuna API for a single search phrase."""
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        log.info("ADZUNA_APP_ID/ADZUNA_APP_KEY not set, skipping Adzuna.")
        return []

    url = ADZUNA_URL_TEMPLATE.format(country=JOB_SEARCH_COUNTRY, page=1)
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": query,
        "results_per_page": results_per_page,
        "content-type": "application/json",
        "max_days_old": 14,
    }

    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        log.warning("Adzuna request failed for query=%r: %s", query, e)
        return []

    jobs = []
    for item in data.get("results", []):
        title = item.get("title", "")
        company = (item.get("company") or {}).get("display_name", "")
        location = (item.get("location") or {}).get("display_name", "United States")
        jobs.append(
            {
                "id": _job_id("adzuna", title, company, location, str(item.get("id", ""))),
                "title": title,
                "company": company,
                "location": location,
                "description": (item.get("description") or "")[:4000],
                "url": item.get("redirect_url", ""),
                "posted_date": item.get("created", ""),
                "source": "Adzuna",
                "remote": "remote" in (item.get("title", "") + item.get("description", "")).lower(),
            }
        )
    return jobs


def search_all_sources(queries: list[str], num_pages: int = 1) -> list[dict]:
    """Run every query against every configured source and dedupe by job id."""
    seen_ids = set()
    all_jobs: list[dict] = []

    for query in queries:
        for job in search_jsearch(query, num_pages=num_pages) + search_adzuna(query):
            if job["id"] in seen_ids or not job["title"] or not job["company"]:
                continue
            seen_ids.add(job["id"])
            all_jobs.append(job)

    return all_jobs
