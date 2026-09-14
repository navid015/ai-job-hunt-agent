"""Gradio app: upload/analyze a resume, view today's recommended jobs, or
trigger a search manually. The daily 5pm run itself is driven by a GitHub
Actions cron job (see .github/workflows/daily_job_search.yml) that calls
scripts/run_daily_job.py against this same persisted state.
"""

import html
import logging

import gradio as gr

from src.config import DAILY_JOB_COUNT
from src.history_store import load_profile, save_profile, load_latest_results
from src.resume_analyzer import analyze_resume, profile_to_markdown
from src.resume_parser import parse_resume
from src.pipeline import run_daily_search, NoProfileError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def handle_resume_upload(file):
    if file is None:
        return "", "pick a file first."

    try:
        text = parse_resume(file.name if hasattr(file, "name") else file)
        profile = analyze_resume(text)
        save_profile(profile)
        return profile_to_markdown(profile), "saved."
    except Exception as e:
        logging.exception("Resume analysis failed")
        return "", f"error: {e}"


def show_saved_profile():
    profile = load_profile()
    if not profile:
        return "_nothing saved yet — upload a resume in the first tab._"
    return profile_to_markdown(profile)


def _truncate(text: str, max_len: int = 130) -> str:
    text = text or ""
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


def _score_bucket(score) -> str:
    try:
        score = int(score)
    except (TypeError, ValueError):
        return "low"
    if score >= 70:
        return "high"
    if score >= 45:
        return "mid"
    return "low"


def _safe_url(url: str) -> str:
    url = (url or "").strip()
    return url if url.startswith("http://") or url.startswith("https://") else ""


def render_job_cards(jobs: list[dict]) -> str:
    if not jobs:
        return '<div class="jr-empty">nothing yet — analyze a resume, then run a search.</div>'

    cards = []
    for j in jobs:
        score = j.get("fit_score", "")
        title = html.escape(str(j.get("title", "")))
        company = html.escape(str(j.get("company", "")))
        source = html.escape(str(j.get("source", "")))
        location = html.escape(str(j.get("location", "")))
        why = html.escape(_truncate(j.get("fit_reason", "")))
        url = _safe_url(j.get("url", ""))

        meta_bits = [b for b in (company, source, location) if b]
        meta = " · ".join(meta_bits)

        apply_html = (
            f'<a class="jr-apply-link" href="{html.escape(url)}" target="_blank" '
            f'rel="noopener noreferrer">apply →</a>'
            if url
            else '<span class="jr-apply-link jr-apply-link--disabled">no link</span>'
        )

        cards.append(
            f"""<div class="jr-card">
  <div class="jr-score jr-score--{_score_bucket(score)}">{html.escape(str(score))}</div>
  <div class="jr-body">
    <div class="jr-title-line">{title}</div>
    <div class="jr-meta">{meta}</div>
    <div class="jr-why">{why}</div>
  </div>
  <div class="jr-apply">{apply_html}</div>
</div>"""
        )

    return f'<div class="jr-jobs">{"".join(cards)}</div>'


def load_today_results():
    data = load_latest_results()
    jobs = data.get("jobs", [])
    status = f"last run: {data.get('generated_at') or '—'}  ·  {data.get('count', 0)} jobs"
    return render_job_cards(jobs), status


def run_now():
    try:
        result = run_daily_search(top_n=DAILY_JOB_COUNT)
    except NoProfileError as e:
        return render_job_cards([]), str(e)
    except Exception as e:
        logging.exception("Manual run failed")
        return render_job_cards([]), f"error: {e}"

    status = (
        f"{result['candidates_found']} found  ·  {result['unseen_after_dedupe']} new  ·  "
        f"kept top {result['final_count']}"
    )
    return render_job_cards(result["jobs"]), status


CUSTOM_CSS = """
:root {
  --jr-bg: #f5f1e8;
  --jr-surface: #fffdf8;
  --jr-ink: #211d16;
  --jr-muted: #78705e;
  --jr-line: #e3dac2;
  --jr-accent: #1f6f66;
  --jr-amber: #b8791f;
  --jr-red: #a5432c;
  --jr-gray: #9b9384;
}

/* Gradio's page/app background stays dark independent of the 'dark' class
   removal above, and shows through above/around the centered container --
   pin it explicitly so there's no stray black bar. */
html, body, gradio-app, .app {
  background: var(--jr-bg) !important;
}

.gradio-container {
  background: var(--jr-bg) !important;
  color: var(--jr-ink) !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
  max-width: 960px !important;
  margin: 0 auto !important;
}

/* Force one consistent look regardless of the visitor's system dark-mode
   preference -- Gradio's own dark-mode palette otherwise bleeds through on
   headings, tabs, and the file dropzone and fights the custom theme. */
#jr-header h1 {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
  letter-spacing: -0.02em;
  font-size: 1.5rem !important;
  margin: 0 0 2px 0 !important;
  color: var(--jr-ink) !important;
}
#jr-header { margin-bottom: 6px; }

.tab-nav button {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
  color: var(--jr-muted) !important;
}
.tab-nav button.selected, .tab-nav button[aria-selected="true"] {
  color: var(--jr-ink) !important;
}

button.primary {
  background: var(--jr-accent) !important;
  border-color: var(--jr-accent) !important;
  color: var(--jr-surface) !important;
}
button.secondary {
  background: var(--jr-surface) !important;
  border-color: var(--jr-line) !important;
  color: var(--jr-ink) !important;
}

#jr-upload .wrap {
  background: var(--jr-surface) !important;
  border: 1px dashed var(--jr-line) !important;
  color: var(--jr-ink) !important;
}
#jr-upload label { color: var(--jr-ink) !important; }

.prose, .prose * { color: var(--jr-ink); }

#jr-status {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
  font-size: 0.8rem !important;
  color: var(--jr-muted) !important;
}

.jr-jobs { display: flex; flex-direction: column; gap: 8px; }
.jr-card {
  background: var(--jr-surface);
  border: 1px solid var(--jr-line);
  border-radius: 6px;
  padding: 10px 12px;
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.jr-score {
  flex: 0 0 40px;
  height: 40px;
  border-radius: 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-weight: 700;
  font-size: 1rem;
  color: #fffdf8;
}
.jr-score--high { background: var(--jr-accent); }
.jr-score--mid { background: var(--jr-amber); }
.jr-score--low { background: var(--jr-gray); }
.jr-body { flex: 1; min-width: 0; }
.jr-title-line { font-weight: 600; font-size: 0.95rem; }
.jr-meta {
  font-size: 0.75rem;
  color: var(--jr-muted);
  margin-top: 2px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.jr-why { font-size: 0.84rem; margin-top: 5px; color: #38332a; line-height: 1.35; }
.jr-apply { flex: 0 0 auto; align-self: center; }
.jr-apply-link {
  display: inline-block;
  padding: 5px 11px;
  border-radius: 4px;
  border: 1px solid var(--jr-ink);
  color: var(--jr-ink) !important;
  text-decoration: none !important;
  font-size: 0.78rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.jr-apply-link:hover { background: var(--jr-ink); color: var(--jr-surface) !important; }
.jr-apply-link--disabled { opacity: 0.4; border-style: dashed; }
.jr-empty { color: var(--jr-muted); font-size: 0.88rem; padding: 24px 4px; text-align: center; }
"""

with gr.Blocks(title="Navid's Job Searcher Agent") as demo:
    with gr.Column(elem_id="jr-header"):
        gr.Markdown("# Navid's Job Searcher Agent")

    with gr.Tab("resume"):
        resume_file = gr.File(
            label="resume (pdf / docx / txt)", file_types=[".pdf", ".docx", ".txt"], elem_id="jr-upload"
        )
        analyze_btn = gr.Button("analyze", variant="primary")
        analysis_status = gr.Markdown(elem_id="jr-status")
        profile_view = gr.Markdown()
        analyze_btn.click(handle_resume_upload, inputs=resume_file, outputs=[profile_view, analysis_status])

    with gr.Tab("profile"):
        refresh_profile_btn = gr.Button("refresh")
        saved_profile_view = gr.Markdown()
        refresh_profile_btn.click(show_saved_profile, outputs=saved_profile_view)
        demo.load(show_saved_profile, outputs=saved_profile_view)

    with gr.Tab("jobs"):
        with gr.Row():
            run_now_btn = gr.Button("run search now", variant="primary")
            refresh_results_btn = gr.Button("refresh")
        results_status = gr.Markdown(elem_id="jr-status")
        results_html = gr.HTML()

        run_now_btn.click(run_now, outputs=[results_html, results_status])
        refresh_results_btn.click(load_today_results, outputs=[results_html, results_status])
        demo.load(load_today_results, outputs=[results_html, results_status])

if __name__ == "__main__":
    import os

    # Render (and most PaaS free tiers) inject $PORT and expect the app to
    # bind 0.0.0.0 on it; default to Gradio's usual port for local runs.
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        theme=gr.themes.Base(),
        css=CUSTOM_CSS,
        # keep one deliberate light look regardless of the visitor's system
        # dark-mode preference, instead of half-matching Gradio's own dark palette
        js="() => { document.body.classList.remove('dark'); document.documentElement.classList.remove('dark'); }",
    )
