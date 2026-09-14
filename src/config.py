"""Central configuration: env vars, model choice, and fixed candidate facts."""

import os

# --- Anthropic ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

# --- Job source APIs ---
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")  # JSearch (aggregates LinkedIn/Indeed/Glassdoor/ZipRecruiter/Monster)
ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")

# --- Persistence (Hugging Face Hub dataset repo used as shared storage between
# the Gradio Space and the GitHub Actions scheduled job) ---
HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_DATASET_REPO = os.environ.get("HF_DATASET_REPO", "")  # e.g. "your-username/job-hunt-agent-data"

# Local fallback storage (used automatically if HF_DATASET_REPO is not set,
# e.g. when running everything locally without Hugging Face persistence)
LOCAL_DATA_DIR = os.environ.get("LOCAL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))

RESUME_PROFILE_FILE = "resume_profile.json"
SEEN_JOBS_FILE = "seen_jobs.json"
LATEST_RESULTS_FILE = "latest_results.json"

# --- Search behavior ---
DAILY_JOB_COUNT = int(os.environ.get("DAILY_JOB_COUNT", "30"))
SEEN_JOB_MEMORY_DAYS = int(os.environ.get("SEEN_JOB_MEMORY_DAYS", "45"))  # don't re-recommend within this window
JOB_SEARCH_COUNTRY = "us"

# JSearch's RapidAPI free tier caps out at 200 requests/month (1 query = 1
# request here, since num_pages=1). Capping queries per run at 6 keeps a daily
# cron job at ~180 requests/month, safely under that cap with room for manual
# "run now" clicks too. Raise this if you're on a paid JSearch plan.
MAX_SEARCH_QUERIES_PER_RUN = int(os.environ.get("MAX_SEARCH_QUERIES_PER_RUN", "6"))

# --- Fixed candidate facts that must never be re-derived or forgotten ---
# The user holds a US Green Card (lawful permanent resident): no visa sponsorship
# is ever required, and they are authorized to work indefinitely for any US
# employer. They are NOT a US citizen, so postings that strictly require US
# citizenship (typically certain federal, defense, or security-clearance roles)
# should be filtered out rather than recommended.
WORK_AUTHORIZATION_STATEMENT = (
    "The candidate is a US Green Card holder (lawful permanent resident). "
    "They do NOT require visa sponsorship now or in the future and are authorized "
    "to work indefinitely for any employer in the United States. They are not a "
    "US citizen, so roles that explicitly require US citizenship or an active/eligible "
    "security clearance restricted to citizens should be excluded from recommendations."
)

TARGET_ROLE_FAMILY = "AI/ML (machine learning, applied AI, MLOps, data science, AI engineering)"
