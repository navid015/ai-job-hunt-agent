"""Rank candidate job postings against the resume profile using Claude.

Claude scores each job for genuine interview-chance fit (not just keyword
overlap) and flags postings that must be excluded because they require US
citizenship, which the candidate -- a Green Card holder, not a citizen --
cannot satisfy.
"""

import logging

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, WORK_AUTHORIZATION_STATEMENT

log = logging.getLogger(__name__)

_BATCH_SIZE = 25

_RANK_TOOL = {
    "name": "record_job_scores",
    "description": "Record a fit score and short rationale for each job posting provided.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "fit_score": {
                            "type": "integer",
                            "description": "0-100: likelihood this candidate would get an interview call, based on real fit",
                        },
                        "reason": {"type": "string", "description": "One sentence on why this score"},
                        "exclude_citizenship_required": {
                            "type": "boolean",
                            "description": "true only if the posting explicitly requires US citizenship or a clearance restricted to citizens",
                        },
                    },
                    "required": ["job_id", "fit_score", "reason", "exclude_citizenship_required"],
                },
            }
        },
        "required": ["scores"],
    },
}


def _system_prompt(profile: dict) -> str:
    return f"""You are an expert AI/ML technical recruiter scoring job postings for a specific \
candidate's chance of getting an interview call. Be discriminating: a high score means the \
candidate's real, demonstrated skills and seniority genuinely match what the posting asks for -- \
not just superficial keyword overlap.

Candidate profile:
- Current title: {profile.get('current_title')}
- Seniority: {profile.get('seniority_level')}
- Years of experience: {profile.get('years_experience')}
- Core skills: {', '.join(profile.get('core_skills', []))}
- Domains: {', '.join(profile.get('domains', []))}
- Summary: {profile.get('summary')}

Fixed candidate fact: {WORK_AUTHORIZATION_STATEMENT}

For every job you are given, call record_job_scores exactly once covering all of them."""


def _score_batch(profile: dict, jobs: list[dict]) -> dict[str, dict]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    listing_text = "\n\n".join(
        f"job_id: {j['id']}\ntitle: {j['title']}\ncompany: {j['company']}\nlocation: {j['location']}\n"
        f"description: {j['description'][:1500]}"
        for j in jobs
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=_system_prompt(profile),
        tools=[_RANK_TOOL],
        tool_choice={"type": "tool", "name": "record_job_scores"},
        messages=[{"role": "user", "content": f"Score these job postings:\n\n{listing_text}"}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "record_job_scores":
            return {s["job_id"]: s for s in block.input.get("scores", [])}

    return {}


def rank_jobs(profile: dict, jobs: list[dict], top_n: int) -> list[dict]:
    """Score every job, drop citizenship-restricted postings, return the top_n."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    if not jobs:
        return []

    all_scores: dict[str, dict] = {}
    for i in range(0, len(jobs), _BATCH_SIZE):
        batch = jobs[i : i + _BATCH_SIZE]
        try:
            all_scores.update(_score_batch(profile, batch))
        except Exception as e:
            log.warning("Scoring batch failed (%s), skipping %d jobs", e, len(batch))

    scored_jobs = []
    for job in jobs:
        score = all_scores.get(job["id"])
        if not score or score.get("exclude_citizenship_required"):
            continue
        job = {**job, "fit_score": score["fit_score"], "fit_reason": score["reason"]}
        scored_jobs.append(job)

    scored_jobs.sort(key=lambda j: j["fit_score"], reverse=True)
    return scored_jobs[:top_n]
