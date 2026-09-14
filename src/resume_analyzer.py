"""Deep resume analysis via Claude, producing a structured candidate profile.

The profile is what the job-search pipeline searches and ranks against every
day, so it captures not just keywords but seniority, target titles, and a
narrative summary an LLM can use to judge job-description fit.
"""

import json

import anthropic

from src.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    WORK_AUTHORIZATION_STATEMENT,
    TARGET_SENIORITY_PREFERENCE,
)

_PROFILE_TOOL = {
    "name": "record_candidate_profile",
    "description": "Record a structured analysis of a candidate's resume.",
    "input_schema": {
        "type": "object",
        "properties": {
            "candidate_name": {"type": "string"},
            "current_title": {"type": "string"},
            "years_experience": {"type": "number", "description": "Total professional experience, in years"},
            "seniority_level": {
                "type": "string",
                "enum": ["intern", "entry", "mid", "senior", "staff/lead", "manager/director"],
            },
            "core_skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Technical skills, languages, frameworks, platforms",
            },
            "domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Subject-matter domains, e.g. NLP, computer vision, MLOps, recommender systems, data engineering",
            },
            "notable_achievements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-6 standout, quantified achievements worth matching against job requirements",
            },
            "education": {"type": "string"},
            "target_titles": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "8-12 job titles to search for, ordered best-fit first. Per the candidate's "
                    "stated seniority preference, these must be Junior/Associate/Entry-level or "
                    "early-to-mid career title variants (e.g. 'Junior Machine Learning Engineer', "
                    "'Associate AI Engineer', 'ML Engineer I', 'AI Engineer (Early Career)') -- "
                    "never Senior/Staff/Lead/Principal titles, even if the candidate's resume "
                    "itself shows deeper experience."
                ),
            },
            "search_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "10-20 concise keywords/phrases for querying job search APIs, biased the same "
                    "way as target_titles toward junior/associate/entry-level and early-career roles"
                ),
            },
            "summary": {
                "type": "string",
                "description": "3-5 sentence narrative summary of the candidate, written for another AI to use when judging job fit",
            },
        },
        "required": [
            "current_title",
            "years_experience",
            "seniority_level",
            "core_skills",
            "domains",
            "target_titles",
            "search_keywords",
            "summary",
        ],
    },
}

_SYSTEM_PROMPT = f"""You are an expert technical recruiter specializing in AI/ML hiring in the \
United States. Analyze the candidate's resume thoroughly and deeply, then call the \
record_candidate_profile tool exactly once with your findings.

Important fixed context about this candidate that is NOT in the resume text: \
{WORK_AUTHORIZATION_STATEMENT}

{TARGET_SENIORITY_PREFERENCE}

Focus the analysis on what will matter for matching this person to real AI/ML job \
postings: concrete skills and tools, seniority signals (scope, years, leadership), \
and domains of depth (not just tools listed once). The `seniority_level` field should \
still honestly reflect what the resume shows -- but `target_titles` and `search_keywords` \
must follow the candidate's stated targeting preference above, not the resume's own level."""


def analyze_resume(resume_text: str) -> dict:
    """Call Claude to deeply analyze a resume and return a structured profile dict."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        tools=[_PROFILE_TOOL],
        tool_choice={"type": "tool", "name": "record_candidate_profile"},
        messages=[
            {
                "role": "user",
                "content": f"Here is the candidate's resume text:\n\n<resume>\n{resume_text}\n</resume>",
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "record_candidate_profile":
            profile = dict(block.input)
            profile["work_authorization"] = WORK_AUTHORIZATION_STATEMENT
            return profile

    raise RuntimeError("Claude did not return a structured profile. Please try again.")


def profile_to_markdown(profile: dict) -> str:
    """Render the profile as readable markdown for display in the UI."""
    lines = [
        f"### {profile.get('candidate_name') or 'Candidate'} — {profile.get('current_title', '')}",
        f"**Seniority:** {profile.get('seniority_level', '—')}  |  **Experience:** {profile.get('years_experience', '—')} years",
        "",
        f"{profile.get('summary', '')}",
        "",
        "**Core skills:** " + ", ".join(profile.get("core_skills", [])),
        "",
        "**Domains:** " + ", ".join(profile.get("domains", [])),
        "",
        "**Target titles searched daily:**",
    ]
    for t in profile.get("target_titles", []):
        lines.append(f"- {t}")
    if profile.get("notable_achievements"):
        lines.append("")
        lines.append("**Notable achievements:**")
        for a in profile["notable_achievements"]:
            lines.append(f"- {a}")
    lines.append("")
    lines.append(f"**Work authorization:** {profile.get('work_authorization', '')}")
    return "\n".join(lines)


def profile_to_json(profile: dict) -> str:
    return json.dumps(profile, indent=2)
