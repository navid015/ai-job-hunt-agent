"""Gradio app: upload/analyze a resume, view today's recommended jobs, or
trigger a search manually. The daily 5pm run itself is driven by a GitHub
Actions cron job (see .github/workflows/daily_job_search.yml) that calls
scripts/run_daily_job.py against this same persisted state.
"""

import logging

import gradio as gr

from src.config import DAILY_JOB_COUNT, WORK_AUTHORIZATION_STATEMENT
from src.history_store import load_profile, save_profile, load_latest_results
from src.resume_analyzer import analyze_resume, profile_to_markdown
from src.resume_parser import parse_resume
from src.pipeline import run_daily_search, NoProfileError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def handle_resume_upload(file):
    if file is None:
        return "Please upload a resume file first.", ""

    try:
        text = parse_resume(file.name if hasattr(file, "name") else file)
        profile = analyze_resume(text)
        save_profile(profile)
        return profile_to_markdown(profile), "✅ Resume analyzed and saved."
    except Exception as e:
        logging.exception("Resume analysis failed")
        return "", f"❌ {e}"


def show_saved_profile():
    profile = load_profile()
    if not profile:
        return "_No resume analyzed yet. Upload one in the tab above._"
    return profile_to_markdown(profile)


def jobs_to_rows(jobs: list[dict]) -> list[list[str]]:
    return [
        [
            j.get("fit_score", ""),
            j.get("title", ""),
            j.get("company", ""),
            j.get("location", ""),
            j.get("source", ""),
            j.get("fit_reason", ""),
            j.get("url", ""),
        ]
        for j in jobs
    ]


def load_today_results():
    data = load_latest_results()
    jobs = data.get("jobs", [])
    status = (
        f"Last generated: {data.get('generated_at') or '—'}  |  {data.get('count', 0)} jobs"
    )
    return jobs_to_rows(jobs), status


def run_now():
    try:
        result = run_daily_search(top_n=DAILY_JOB_COUNT)
    except NoProfileError as e:
        return [], str(e)
    except Exception as e:
        logging.exception("Manual run failed")
        return [], f"❌ Run failed: {e}"

    status = (
        f"Found {result['candidates_found']} candidates, {result['unseen_after_dedupe']} "
        f"were new, kept top {result['final_count']}."
    )
    return jobs_to_rows(result["jobs"]), status


COLUMNS = ["Fit", "Title", "Company", "Location", "Source", "Why", "Apply link"]

with gr.Blocks(title="AI Job Hunt Agent") as demo:
    gr.Markdown(
        "# 🎯 AI Job Hunt Agent\n"
        "Upload your resume once. Every day at 5pm, this agent searches AI/ML jobs across "
        "LinkedIn, Indeed, Glassdoor, ZipRecruiter, Monster and more (via aggregator APIs), "
        f"and gives you a fresh top-{DAILY_JOB_COUNT} list — never repeating a job it already showed you.\n\n"
        f"> **Fixed profile fact:** {WORK_AUTHORIZATION_STATEMENT}"
    )

    with gr.Tab("1. Upload resume"):
        resume_file = gr.File(label="Resume (PDF, DOCX, or TXT)", file_types=[".pdf", ".docx", ".txt"])
        analyze_btn = gr.Button("Analyze resume", variant="primary")
        analysis_status = gr.Markdown()
        profile_view = gr.Markdown()
        analyze_btn.click(handle_resume_upload, inputs=resume_file, outputs=[profile_view, analysis_status])

    with gr.Tab("2. My profile"):
        refresh_profile_btn = gr.Button("Refresh")
        saved_profile_view = gr.Markdown()
        refresh_profile_btn.click(show_saved_profile, outputs=saved_profile_view)
        demo.load(show_saved_profile, outputs=saved_profile_view)

    with gr.Tab("3. Today's recommended jobs"):
        gr.Markdown(
            "Runs automatically every day at 5pm via a scheduled GitHub Action. "
            "You can also trigger a run manually here."
        )
        run_now_btn = gr.Button("Run search now", variant="primary")
        refresh_results_btn = gr.Button("Refresh (show last saved results)")
        results_status = gr.Markdown()
        results_table = gr.Dataframe(headers=COLUMNS, wrap=True, interactive=False)

        run_now_btn.click(run_now, outputs=[results_table, results_status])
        refresh_results_btn.click(load_today_results, outputs=[results_table, results_status])
        demo.load(load_today_results, outputs=[results_table, results_status])

if __name__ == "__main__":
    import os

    # Render (and most PaaS free tiers) inject $PORT and expect the app to
    # bind 0.0.0.0 on it; default to Gradio's usual port for local runs.
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
