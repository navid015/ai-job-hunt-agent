---
title: AI Job Hunt Agent
emoji: 🎯
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.9.1
app_file: app.py
pinned: false
license: mit
short_description: Daily AI/ML job recommendations tailored to your resume
---

# AI Job Hunt Agent

An agentic job-search assistant for AI/ML roles in the US. Upload your resume
once; every day at 5pm it searches job boards, scores openings against your
actual background, and hands you a fresh top-30 list — never repeating a job
it already showed you.

## What it does

1. **Upload your resume** (PDF/DOCX/TXT) in the Gradio app.
2. **Claude analyzes it deeply** — skills, seniority, domains, achievements,
   target titles — and saves a structured profile.
3. **Every day at 5pm**, a scheduled job searches AI/ML openings across
   LinkedIn, Indeed, Glassdoor, ZipRecruiter, Monster, and more, scores each
   one against your profile, and keeps the **top 30 best-fit** postings.
4. **Jobs already recommended are never repeated** for 45 days (configurable).
5. The app remembers you're a **US Green Card holder** — no sponsorship is
   ever needed, and roles that strictly require US citizenship are filtered out.

## Why this doesn't scrape LinkedIn/Indeed/Glassdoor directly

Those sites' Terms of Service prohibit scraping, and it breaks constantly in
practice (LinkedIn in particular aggressively blocks and pursues scrapers).
Instead this project queries **aggregator APIs that legally syndicate the same
listings**:

- **[JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)** (via
  RapidAPI) — aggregates LinkedIn, Indeed, Glassdoor, ZipRecruiter, Monster,
  and company career pages.
- **[Adzuna](https://developer.adzuna.com/)** — an independent job API, used
  as a second source.

You'll need free/low-cost API keys for these (see setup below).

## Architecture

```
                     ┌─────────────────────────┐
   Resume upload ──▶ │   Gradio app (app.py)   │
                     └──────────┬──────────────┘
                                │ analyze + save profile
                                ▼
                     ┌─────────────────────────┐
                     │ HF Hub dataset repo      │  ◀── shared persistent storage
                     │ (resume_profile.json,    │
                     │  seen_jobs.json,         │
                     │  latest_results.json)    │
                     └──────────┬──────────────┘
                                │ read profile / write results
                                ▼
   GitHub Actions      ┌─────────────────────────┐
   cron @ 5pm   ─────▶ │  scripts/run_daily_job  │
                       │  -> src/pipeline.py     │
                       └──────────┬──────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
      job_sources.py       history_store.py      job_ranker.py
   (JSearch + Adzuna)   (dedupe vs. history)   (Claude scores fit,
                                                 drops citizenship-
                                                 restricted postings)
```

The Gradio Space (interactive) and the GitHub Actions cron job (scheduled,
headless) both read/write the **same** state through a private Hugging Face
Hub dataset repo, since HF Spaces has no built-in cron and free-tier Spaces
sleep when idle — GitHub Actions runs reliably regardless of whether the Space
is awake.

## Files

| File | Purpose |
|---|---|
| `app.py` | Gradio UI: upload resume, view profile, view/run today's jobs |
| `src/config.py` | Env vars, model choice, and the fixed Green-Card/no-sponsorship fact |
| `src/resume_parser.py` | Extracts text from PDF/DOCX/TXT resumes |
| `src/resume_analyzer.py` | Claude call that deeply analyzes the resume into a structured profile |
| `src/job_sources.py` | JSearch + Adzuna API clients, normalized job schema |
| `src/job_ranker.py` | Claude call that scores each job's real interview-chance fit |
| `src/history_store.py` | Shared persistence (HF Hub dataset repo, with local fallback) + dedupe logic |
| `src/pipeline.py` | Orchestrates one full daily run |
| `scripts/run_daily_job.py` | Entry point the GitHub Action runs |
| `.github/workflows/daily_job_search.yml` | Cron schedule (5pm) + manual trigger |

## Setup

### 1. Get API keys

- **Anthropic**: https://console.anthropic.com
- **JSearch (RapidAPI)**: subscribe to the free tier at
  https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
- **Adzuna**: register at https://developer.adzuna.com/ for an `app_id` + `app_key`
- **Hugging Face token**: https://huggingface.co/settings/tokens (needs **write** access)
- **Hugging Face dataset repo**: create a private dataset at
  https://huggingface.co/new-dataset, e.g. `your-username/job-hunt-agent-data`
  — this is where your resume profile and job history are stored.

### 2. Run locally

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in .env with the keys above
python app.py
```

Open the printed `http://127.0.0.1:7860` URL, upload your resume, then click
**"Run search now"** to test the full pipeline before relying on the schedule.

### 3. Deploy the Gradio app to Hugging Face Spaces

1. Create a new Space at https://huggingface.co/new-space (SDK: **Gradio**, CPU basic is enough).
2. Push this project's files to the Space repo (`git push`, same as any HF Space).
3. In the Space's **Settings → Variables and secrets**, add:
   `ANTHROPIC_API_KEY`, `RAPIDAPI_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`,
   `HF_TOKEN`, `HF_DATASET_REPO`.
4. Open the Space, upload your resume once under **"1. Upload resume"**.

### 4. Set up the daily 5pm schedule (GitHub Actions)

Push this same project to a GitHub repo, then in **Settings → Secrets and
variables → Actions**, add the same six secrets as above. The workflow in
`.github/workflows/daily_job_search.yml` will then run automatically at 5pm
Central time and update `latest_results.json` in your HF dataset repo, which
the Space's **"3. Today's recommended jobs"** tab reads on every page load.

You can also trigger it manually any time from the repo's **Actions** tab
(`workflow_dispatch`), or from the Space's **"Run search now"** button.

> The cron is set to 22:00 UTC (5pm US Central Daylight Time). Because GitHub
> Actions cron doesn't auto-adjust for daylight saving, shift it to `0 23 * * *`
> during US Standard Time months if you want it pinned exactly to 5pm year-round.

## Can I run this entirely on free tiers?

Mostly yes, with two things to know:

| Service | Free tier | Fits this project? |
|---|---|---|
| **Anthropic API** | One-time ~$5 trial credit for new accounts; no ongoing free monthly quota | Enough for a while (one resume analysis + small daily scoring batches), but you'll eventually add a payment method — usage here is cheap (a few dollars/month), not free forever |
| **JSearch (RapidAPI)** | 200 requests/month on the free Basic plan | Tight. 1 query = 1 request, so `MAX_SEARCH_QUERIES_PER_RUN` in `src/config.py` defaults to **6**, keeping a daily cron run at ~180 requests/month. Don't raise it unless you upgrade the plan |
| **Adzuna** | ~1,000 requests/month, self-serve | Comfortable headroom at 6 queries/day |
| **Hugging Face Spaces** | Free CPU Basic Space | Fine — this project doesn't need GPU. Free Spaces sleep when idle, which is exactly why the daily run uses GitHub Actions instead of relying on the Space being awake |
| **HF Hub dataset repo (storage)** | Free | No issue at this file size |
| **GitHub Actions** | Unlimited minutes on public repos, 2,000 min/month free on private repos | A daily run takes ~1-2 minutes — nowhere near the limit either way |

So: free tiers work end-to-end, JSearch's 200/month cap is the one you could hit if you increase `MAX_SEARCH_QUERIES_PER_RUN`, and the Anthropic side moves from "free trial credit" to "cheap pay-as-you-go" once that credit runs out.

## Notes and limitations

- **Cost**: each daily run makes a handful of Claude API calls (resume
  analysis is one-time; job scoring runs in batches of ~25 postings). Keep an
  eye on usage if you increase `DAILY_JOB_COUNT` or run manually very often.
- **Fewer than 30 jobs some days**: if fewer than 30 new, well-matched, non-repeated
  postings exist, the agent returns however many genuinely qualify rather than
  padding the list with weak matches.
- **Work authorization is fixed, not inferred**: the Green Card / no-sponsorship
  fact lives in `src/config.py` (`WORK_AUTHORIZATION_STATEMENT`) and is injected
  into every analysis and scoring call — it is never re-derived from the resume
  and won't drift.
