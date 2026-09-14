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
   Resume upload ──▶ │   Gradio app (app.py)   │  hosted on Render (free web service)
                     └──────────┬──────────────┘
                                │ analyze + save profile
                                ▼
                     ┌─────────────────────────┐
                     │ HF Hub dataset repo      │  ◀── shared persistent storage only
                     │ (resume_profile.json,    │      (no app hosted on HF)
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

The Render web service (interactive) and the GitHub Actions cron job
(scheduled, headless) both read/write the **same** state through a private
Hugging Face Hub dataset repo. Hugging Face Spaces is used purely as shared
storage here, not as the app host: HF now requires a paid PRO subscription to
run a CPU-backed Gradio Space (its free "ZeroGPU" Spaces refuse to start
without genuine GPU-decorated code, which this app has no real use for), so
the interactive UI is hosted on Render's free tier instead.

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
| `render.yaml` | Render Blueprint describing the free web service |

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

### 3. Deploy the Gradio app to Render (free)

1. Push this repo to GitHub (see below) if you haven't already.
2. Sign in at https://render.com (free, no credit card required) and connect your GitHub account.
3. **New → Web Service** → pick this repo. Render auto-detects `render.yaml`
   in this repo, or if you create the service manually, set:
   - Runtime: **Python 3**
   - Build command: `pip install -r requirements.txt`
   - Start command: `python app.py`
   - Plan: **Free**
4. Add the 6 environment variables in the Render dashboard (**Environment**
   tab): `ANTHROPIC_API_KEY`, `RAPIDAPI_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`,
   `HF_TOKEN`, `HF_DATASET_REPO`.
5. Deploy. Render gives you a `https://<service-name>.onrender.com` URL — open
   it and upload your resume once under **"1. Upload resume"**.

> Free web services on Render spin down after 15 minutes of inactivity and
> take ~30-50 seconds to wake back up on the next visit. That only affects the
> interactive UI — the daily job search itself runs on GitHub Actions
> regardless of whether the Render service is awake.

### 4. Set up the daily 5pm schedule (GitHub Actions)

In your GitHub repo, go to **Settings → Secrets and variables → Actions** and
add the same six secrets as above. The workflow in
`.github/workflows/daily_job_search.yml` will then run automatically at 5pm
Central time and update `latest_results.json` in your HF dataset repo, which
the Render app's **"3. Today's recommended jobs"** tab reads on every page load.

You can also trigger it manually any time from the repo's **Actions** tab
(`workflow_dispatch`), or from the app's **"Run search now"** button.

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
| **Render (app hosting)** | Free web service, 750 instance-hours/month, no credit card | Fine for a personal tool. Spins down after 15 min idle, ~30-50s cold start on the next visit — doesn't affect the daily scheduled search, only the interactive UI |
| **Hugging Face Hub (dataset storage only)** | Free | No issue at this file size. Note: HF now requires a **paid PRO plan** to host a CPU-backed Gradio *Space* — its free "ZeroGPU" Spaces won't start without real GPU-decorated code, which is why this project uses HF only for storage and Render for the app itself |
| **GitHub Actions** | Unlimited minutes on public repos, 2,000 min/month free on private repos | A daily run takes ~1-2 minutes — nowhere near the limit either way |

So: free tiers work end-to-end. JSearch's 200/month cap is the one you could hit if you increase `MAX_SEARCH_QUERIES_PER_RUN`, and the Anthropic side moves from "free trial credit" to "cheap pay-as-you-go" once that credit runs out.

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
