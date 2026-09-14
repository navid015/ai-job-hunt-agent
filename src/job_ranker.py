"""Rank candidate job postings against the resume profile using Claude.

Claude scores each job for genuine interview-chance fit (not just keyword
overlap) and flags postings that must be excluded because they require US
citizenship, which the candidate -- a Green Card holder, not a citizen --
cannot satisfy.
"""

import logging

import anthropic

from src.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    WORK_AUTHORIZATION_STATEMENT,
    TARGET_SENIORITY_PREFERENCE,
    TARGET_ROLE_FAMILY,
    EXPERIENCE_EVALUATION_GUIDANCE,
)

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
                        "exclude_seniority_mismatch": {
                            "type": "boolean",
                            "description": (
                                "true if the posting is Senior/Staff/Lead/Principal/Manager/Director-level, "
                                "or explicitly requires 5+ years of experience, when the candidate is "
                                "targeting Junior/Associate/entry/early-career roles"
                            ),
                        },
                    },
                    "required": [
                        "job_id",
                        "fit_score",
                        "reason",
                        "exclude_citizenship_required",
                        "exclude_seniority_mismatch",
                    ],
                },
            }
        },
        "required": ["scores"],
    },
}


def _system_prompt(profile: dict) -> str:
    return f"""You are an expert AI/ML technical recruiter scoring job postings for a specific \
candidate's chance of getting an interview call. A high score means the posting's ACTUAL \
requirements (level, years of experience, must-have skills) genuinely line up with what this \
candidate can credibly offer today -- not aspirational stretch matches, and not superficial \
keyword overlap.

Candidate profile:
- Current title: {profile.get('current_title')}
- Seniority: {profile.get('seniority_level')}
- Years of experience: {profile.get('years_experience')}
- Core skills: {', '.join(profile.get('core_skills', []))}
- Domains: {', '.join(profile.get('domains', []))}
- Notable achievements: {'; '.join(profile.get('notable_achievements', []))}
- Summary: {profile.get('summary')}

Fixed candidate fact: {WORK_AUTHORIZATION_STATEMENT}

Fixed candidate targeting preference: {TARGET_SENIORITY_PREFERENCE}

Target role family: {TARGET_ROLE_FAMILY}

{EXPERIENCE_EVALUATION_GUIDANCE}

Scoring rubric -- use the full range, don't cluster everything in the middle:
- 80-100: Genuine strong match at the candidate's target level. The posting's core requirements \
(skills, tools, years of experience expected) are ones this candidate credibly meets today. This \
is the band a well-targeted junior/associate/entry-level posting that fits should land in -- do \
not reserve it only for hypothetical perfect matches.
- 60-79: Good match with a minor gap (e.g. wants one tool/skill the candidate lacks, or slightly \
more years than they have).
- 40-59: Partial match -- meaningful gaps in required skills, or level is a bit of a stretch.
- 0-39: Poor match -- wrong domain entirely, or a large seniority/experience gap.

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
    """Score every job, drop citizenship- or seniority-mismatched postings, return the top_n."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    if not jobs:
        return []

    all_scores: dict[str, dict] = {}
    batch_count = 0
    failed_batches = 0
    last_error: Exception | None = None
    for i in range(0, len(jobs), _BATCH_SIZE):
        batch = jobs[i : i + _BATCH_SIZE]
        batch_count += 1
        try:
            all_scores.update(_score_batch(profile, batch))
        except Exception as e:
            log.warning("Scoring batch failed (%s), skipping %d jobs", e, len(batch))
            failed_batches += 1
            last_error = e

    if failed_batches == batch_count and batch_count > 0:
        raise RuntimeError(
            f"All {batch_count} scoring batch(es) failed ({last_error}); "
            "no jobs were kept. This is almost certainly transient (a timeout or "
            "network issue calling Claude) -- try running the search again."
        )

    scored_jobs = []
    for job in jobs:
        score = all_scores.get(job["id"])
        if not score or score.get("exclude_citizenship_required") or score.get("exclude_seniority_mismatch"):
            continue
        job = {**job, "fit_score": score["fit_score"], "fit_reason": score["reason"]}
        scored_jobs.append(job)

    scored_jobs.sort(key=lambda j: j["fit_score"], reverse=True)
    return scored_jobs[:top_n]
