"""ScriptGuard AI — Streamlit interface: upload one or more PDF scripts and generate
individual coverage + slate prioritization, with real parallel market research and
agent self-QA."""

import html
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from scriptguard.pdf_utils import extract_text_from_pdf
from scriptguard.pipeline import RateLimitExceeded, run_slate_triage
from scriptguard.schemas import CoverageReport

load_dotenv()

st.set_page_config(page_title="ScriptGuard AI", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --sg-bg: #0B0E14;
        --sg-surface: #161A23;
        --sg-surface-elevated: #1E232E;
        --sg-border: #2A303C;
        --sg-text: #F2F1ED;
        --sg-text-muted: #8B93A1;
        --sg-accent: #C9A227;
        --sg-recommend: #4ADE80;
        --sg-consider: #FBBF24;
        --sg-pass: #F87171;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    h1, h2, h3, .sg-serif {
        font-family: 'Playfair Display', serif !important;
    }

    /* Streamlit paints the alert background on the inner notification node, so
       radius/border must go there; its semantic amber/blue tints already read
       well on the dark ground and are kept to distinguish warning from info. */
    div[data-testid="stAlert"] > div {
        border-radius: 10px;
    }
    div[data-testid="stAlert"] p {
        color: var(--sg-text) !important;
    }

    /* Streamlit renders inline code in a green that fights the gold accent. */
    div[data-testid="stMarkdownContainer"] code {
        color: var(--sg-text) !important;
        background: var(--sg-surface-elevated) !important;
        border: 1px solid var(--sg-border);
        border-radius: 5px;
        padding: 0.05em 0.35em;
        font-size: 0.85em;
    }

    hr, div[data-testid="stDivider"] {
        border: none;
        border-top: 1px solid var(--sg-border) !important;
        margin: 1.75rem 0 !important;
        opacity: 1 !important;
    }

    /* Own grid instead of st.columns: guarantees equal card heights per row
       and predictable breakpoints (4 -> 2x2 -> 1) rather than Streamlit's
       single 640px stacking rule. */
    .sg-stage-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        align-items: stretch;
    }
    @media (max-width: 1100px) {
        .sg-stage-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }
    @media (max-width: 640px) {
        .sg-stage-grid {
            grid-template-columns: 1fr;
        }
    }

    .sg-stage-card {
        background: var(--sg-surface);
        border: 1px solid var(--sg-border);
        border-radius: 12px;
        padding: 1.25rem 1.35rem;
        min-height: 230px;
        height: 100%;
        display: flex;
        flex-direction: column;
        overflow-wrap: break-word;
        transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
    }
    .sg-stage-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 10px 24px rgba(0, 0, 0, 0.35);
        background: var(--sg-surface-elevated);
    }
    .sg-stage-badge {
        width: 30px;
        height: 30px;
        border-radius: 50%;
        background: rgba(201, 162, 39, 0.15);
        border: 1px solid var(--sg-accent);
        color: var(--sg-accent);
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: 'Playfair Display', serif;
        font-weight: 700;
        font-size: 0.95rem;
        margin-bottom: 0.7rem;
    }
    .sg-stage-title {
        color: var(--sg-text);
        font-weight: 600;
        font-size: 1rem;
        margin-bottom: 0.2rem;
    }
    .sg-stage-caption {
        color: var(--sg-accent);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        line-height: 1.35;
        /* Reserve two lines so body copy starts at the same offset in every
           card, whether the agent count wraps or not. */
        min-height: 2.7em;
        margin-bottom: 0.6rem;
    }
    .sg-stage-body {
        color: var(--sg-text-muted);
        font-size: 0.88rem;
        line-height: 1.45;
    }

    .sg-badge-row {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
    }
    .sg-badge-verdict {
        display: inline-block;
        padding: 0.3rem 0.85rem;
        border-radius: 999px;
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .sg-badge-confidence {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 999px;
        background: transparent;
        border: 1px solid currentColor;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    /* Shared panel used by every prose section, so nothing sits as bare text. */
    .sg-panel {
        background: var(--sg-surface);
        border: 1px solid var(--sg-border);
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
        overflow-wrap: break-word;
    }
    .sg-panel-title {
        color: var(--sg-text-muted);
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        margin-bottom: 0.55rem;
    }
    .sg-panel-body {
        color: var(--sg-text);
        font-size: 0.94rem;
        line-height: 1.55;
    }
    .sg-panel--accent {
        border-left: 3px solid var(--sg-accent);
    }
    .sg-panel--good {
        border-left: 3px solid var(--sg-recommend);
    }
    .sg-panel--bad {
        border-left: 3px solid var(--sg-pass);
    }
    .sg-panel--muted .sg-panel-body {
        color: var(--sg-text-muted);
        font-size: 0.86rem;
    }
    .sg-panel--good .sg-panel-title {
        color: var(--sg-recommend);
    }
    .sg-panel--bad .sg-panel-title {
        color: var(--sg-pass);
    }

    /* Bulleted lists inside panels: marker colour carries the panel's meaning. */
    .sg-list {
        margin: 0;
        padding: 0;
        list-style: none;
    }
    .sg-list li {
        position: relative;
        padding-left: 1.05rem;
        margin-bottom: 0.45rem;
        color: var(--sg-text);
        font-size: 0.92rem;
        line-height: 1.5;
    }
    .sg-list li:last-child {
        margin-bottom: 0;
    }
    .sg-list li::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0.62em;
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: var(--sg-text-muted);
    }
    .sg-panel--good .sg-list li::before {
        background: var(--sg-recommend);
    }
    .sg-panel--bad .sg-list li::before {
        background: var(--sg-pass);
    }

    /* Sub-cards for acts, characters and comparable titles. */
    .sg-item {
        background: var(--sg-surface-elevated);
        border: 1px solid var(--sg-border);
        border-radius: 8px;
        padding: 0.7rem 0.9rem;
        margin-bottom: 0.6rem;
    }
    .sg-item:last-child {
        margin-bottom: 0;
    }
    .sg-item-head {
        color: var(--sg-text);
        font-weight: 600;
        font-size: 0.92rem;
        margin-bottom: 0.25rem;
    }
    .sg-item-tag {
        color: var(--sg-accent);
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        margin-right: 0.45rem;
    }
    .sg-item-body {
        color: var(--sg-text-muted);
        font-size: 0.88rem;
        line-height: 1.5;
    }
    .sg-meta-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem 1.5rem;
        color: var(--sg-text-muted);
        font-size: 0.85rem;
    }
    .sg-meta-row strong {
        color: var(--sg-text);
        font-weight: 600;
    }

    .sg-debate-card {
        background: var(--sg-surface);
        border: 1px solid var(--sg-border);
        border-left-width: 4px;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }
    .sg-debate-header {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        margin-bottom: 0.7rem;
        flex-wrap: wrap;
    }
    .sg-debate-persona {
        font-family: 'Playfair Display', serif;
        font-weight: 600;
        font-size: 1.05rem;
        color: var(--sg-text);
    }
    .sg-tag-changed {
        display: inline-block;
        padding: 0.15rem 0.6rem;
        border-radius: 999px;
        background: rgba(201, 162, 39, 0.15);
        color: var(--sg-accent);
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .sg-tag-dissent {
        display: inline-block;
        padding: 0.15rem 0.6rem;
        border-radius: 999px;
        background: rgba(248, 113, 113, 0.15);
        color: var(--sg-pass);
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .sg-debate-rounds {
        display: flex;
        align-items: stretch;
        gap: 0.9rem;
    }
    .sg-debate-round {
        flex: 1;
        min-width: 0;
    }
    .sg-debate-round-label {
        color: var(--sg-text-muted);
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.3rem;
    }
    .sg-debate-round-text {
        color: var(--sg-text);
        font-size: 0.9rem;
        line-height: 1.45;
    }
    .sg-debate-connector {
        display: flex;
        align-items: center;
        justify-content: center;
        flex: 0 0 auto;
        color: var(--sg-text-muted);
        font-size: 1.1rem;
        padding-top: 1.3rem;
    }
    /* Glyph lives in CSS so it can flip direction when the rounds stack. */
    .sg-debate-connector::before {
        content: "→";
    }
    .sg-debate-concern {
        margin-top: 0.7rem;
        padding-top: 0.6rem;
        border-top: 1px solid var(--sg-border);
        color: var(--sg-text-muted);
        font-size: 0.85rem;
        line-height: 1.4;
    }

    /* Only the upload panel (marked with .sg-uploader-marker, placed as the
       first element inside it) gets the surface card treatment. Every
       st.columns() cell — and the whole page's own top-level block — also
       renders a stVerticalBlockBorderWrapper, so :has() alone would match
       every ancestor up the tree; requiring the marker inside the FIRST
       direct child element-container of the wrapper's own block scopes the
       match to the immediate uploader wrapper only. */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(
        > div[data-testid="stVerticalBlock"]
        > div[data-testid="stElementContainer"]:first-child
        .sg-uploader-marker
    ) {
        background: var(--sg-surface);
        border: 1px solid var(--sg-border) !important;
        border-radius: 12px !important;
        padding: 1.25rem 1.35rem;
    }

    /* Note: the dropzone is a <section>, not a <div> — a div[...] selector
       silently never matches it. */
    [data-testid="stFileUploaderDropzone"] {
        background: var(--sg-surface-elevated) !important;
        border: 1px dashed var(--sg-border) !important;
        border-radius: 10px !important;
    }
    [data-testid="stFileUploaderDropzone"] span,
    [data-testid="stFileUploaderDropzone"] small,
    [data-testid="stFileUploaderDropzone"] svg {
        color: var(--sg-text-muted) !important;
        fill: var(--sg-text-muted) !important;
    }

    /* The palette must not depend solely on .streamlit/config.toml: running
       from another working directory drops that file and would otherwise
       leave dark cards stranded on a white page. */
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stHeader"] {
        background: var(--sg-bg) !important;
    }
    [data-testid="stMarkdownContainer"],
    [data-testid="stWidgetLabel"] p {
        color: var(--sg-text);
    }
    /* Streamlit's red/yellow running bar clashes with the palette. */
    [data-testid="stDecoration"] {
        background: linear-gradient(90deg, var(--sg-accent), rgba(201, 162, 39, 0.15)) !important;
    }

    button[data-testid="stBaseButton-primary"] {
        background: var(--sg-accent) !important;
        border: 1px solid var(--sg-accent) !important;
        border-radius: 8px !important;
    }
    button[data-testid="stBaseButton-primary"] p {
        color: var(--sg-bg) !important;
        font-weight: 600;
    }
    /* "Browse files" has bare text, not a <p>, so the colour has to be set on
       the button itself as well as on the <p> other buttons wrap theirs in. */
    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-secondary"] p {
        color: var(--sg-text) !important;
    }
    button[data-testid="stBaseButton-secondary"] {
        background: var(--sg-surface) !important;
        border: 1px solid var(--sg-border) !important;
        border-radius: 8px !important;
    }
    button[data-testid="stBaseButton-secondary"]:hover {
        border-color: var(--sg-accent) !important;
        background: var(--sg-surface-elevated) !important;
    }
    /* A disabled primary should read as unavailable, not as the gold call to
       action, so it drops the accent fill entirely. */
    button[data-testid="stBaseButton-primary"]:disabled {
        background: var(--sg-surface-elevated) !important;
        border-color: var(--sg-border) !important;
    }
    button[data-testid="stBaseButton-primary"]:disabled p,
    button[data-testid="stBaseButton-secondary"]:disabled,
    button[data-testid="stBaseButton-secondary"]:disabled p {
        color: var(--sg-text-muted) !important;
    }

    /* Streamlit's flex columns stretch to the tallest sibling by default;
       let Strengths/Weaknesses-style column pairs size to their own content. */
    div[data-testid="stHorizontalBlock"] {
        align-items: stretch;
        flex-wrap: wrap;
    }
    /* Streamlit only stacks columns below ~640px, which leaves 4 cramped
       columns through the whole tablet range; a min-width lets them reflow
       to 2x2 instead of squeezing. */
    div[data-testid="stColumn"] {
        min-width: 200px;
    }

    @media (max-width: 640px) {
        .sg-stage-card {
            min-height: 0;
            padding: 1rem 1.1rem;
        }
        /* Cards are stacked here, so reserving a second caption line to align
           them side by side would only leave a gap. */
        .sg-stage-caption {
            min-height: 0;
        }
        .sg-debate-card {
            padding: 0.9rem 1rem;
        }
        div[data-testid="stColumn"] {
            min-width: 100%;
        }
        /* Stacked buttons of differing label lengths otherwise form a ragged
           left edge; full width keeps the panel tidy. */
        [data-testid="stButton"] button,
        [data-testid="stDownloadButton"] button {
            width: 100%;
        }
    }

    /* Round 1 / Round 2 sit side by side on wide screens and stack below it,
       with the connector arrow turning to point down. */
    @media (max-width: 900px) {
        .sg-debate-rounds {
            flex-direction: column;
            gap: 0.5rem;
        }
        .sg-debate-connector {
            padding-top: 0;
            justify-content: flex-start;
        }
        .sg-debate-connector::before {
            content: "↓";
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _html(markup: str) -> str:
    """Flattens a triple-quoted HTML block to one line with no leading indentation.

    Streamlit's markdown renderer treats 4+ leading spaces as an indented code
    block, which mid-parses raw HTML and leaves fragments as literal text —
    this sidesteps that entirely by removing all line breaks/indentation.
    """
    return " ".join(line.strip() for line in markup.strip().splitlines())

st.markdown(
    _html(
        """
        <div style="padding: 1.5rem 0 1rem 0;">
            <h1 class="sg-serif" style="margin-bottom: 0.35rem; font-size: clamp(2rem, 5vw, 2.6rem); color: var(--sg-text);">
                ScriptGuard AI
            </h1>
            <div style="width: 64px; height: 3px; background: var(--sg-accent); margin-bottom: 0.9rem;"></div>
            <p style="color: var(--sg-text-muted); font-size: 1.05rem; max-width: 780px; line-height: 1.5;">
                Script coverage generated by a committee of persona agents that debates over 2
                rounds, with real parallel market research, self-QA critique, and slate prioritization.
            </p>
        </div>
        """
    ),
    unsafe_allow_html=True,
)

if not os.getenv("GOOGLE_API_KEY"):
    st.warning("Missing GOOGLE_API_KEY in the .env file")
if not os.getenv("PARALLEL_API_KEY"):
    st.warning("Missing PARALLEL_API_KEY in the .env file")

st.session_state.setdefault("processing", False)
st.session_state.setdefault("results", None)
st.session_state.setdefault("run_source", None)

st.markdown(
    "<h3 class='sg-serif' style='color: var(--sg-text); margin-bottom: 1rem;'>"
    "How it works — 17 agents orchestrated with Google ADK</h3>",
    unsafe_allow_html=True,
)

STAGES = [
    (
        "1",
        "Narrative analysis",
        "1 agent",
        "Gemini analyzes the full script: three-act structure, characters, "
        "genre, tone, and pacing.",
    ),
    (
        "2",
        "Market research",
        "3 agents — 2 in parallel + 1 formatter",
        "2 agents in parallel (<code>ParallelAgent</code>) research box-office "
        "comparables and genre trends via Parallel's Search API; a third "
        "converts those notes into structured JSON.",
    ),
    (
        "3",
        "Greenlight Committee",
        "9 agents — 4 personas × 2 rounds + 1 moderator",
        "4 persona agents (Creative Producer, Intl. Distribution, Financial "
        "Analyst, Indie/Festival Reader) give their opinion and then debate "
        "in a second round, reacting to each other; a moderator synthesizes "
        "the final verdict.",
    ),
    (
        "4",
        "QA + Prioritization",
        "4 agents — 3 in the QA loop + 1 for prioritization",
        "A 3-agent <code>LoopAgent</code> audits the report against the real "
        "research (up to 3 iterations) and, if you upload several scripts, an "
        "additional agent prioritizes the whole slate as a portfolio.",
    ),
]

st.markdown(
    _html(
        '<div class="sg-stage-grid">'
        + "".join(
            f"""
            <div class="sg-stage-card">
                <div class="sg-stage-badge">{num}</div>
                <div class="sg-stage-title">{title}</div>
                <div class="sg-stage-caption">{caption}</div>
                <div class="sg-stage-body">{body}</div>
            </div>
            """
            for num, title, caption, body in STAGES
        )
        + "</div>"
    ),
    unsafe_allow_html=True,
)

st.markdown(
    "<p style='color: var(--sg-text-muted); font-size: 0.85rem; margin-top: 0.9rem;'>"
    "Orchestrated with Google ADK (<code>SequentialAgent</code> + <code>ParallelAgent</code> x3 + "
    "<code>LoopAgent</code>) on top of Gemini, with real Parallel research on every run.</p>",
    unsafe_allow_html=True,
)
st.divider()


def esc(text: str) -> str:
    """Escapes '$' so Streamlit doesn't interpret it as LaTeX when rendering agent-generated text."""
    return text.replace("$", r"\$")


def esc_html(text: str) -> str:
    """Escapes agent-generated text for interpolation into the raw HTML blocks below.

    Script and agent text is untrusted input: a stray '<' would break the markup,
    and tags in a script would otherwise be injected into the page. Unlike esc(),
    '$' is left alone — Streamlit does not run the markdown/LaTeX pass inside a raw
    HTML block, so a backslash escape would render literally in box-office figures.
    """
    return html.escape(str(text))


VERDICT_HEX = {"RECOMMEND": "#4ADE80", "CONSIDER": "#FBBF24", "PASS": "#F87171"}
CONFIDENCE_HEX = {"HIGH": "#4ADE80", "MEDIUM": "#FBBF24", "LOW": "#F87171"}


def _panel(title: str, body_html: str, modifier: str = "") -> str:
    """Wraps a section in the shared surface card. `body_html` is already-escaped markup."""
    return _html(
        f'<div class="sg-panel {modifier}">'
        f'<div class="sg-panel-title">{esc_html(title)}</div>'
        f"{body_html}"
        f"</div>"
    )


def _list(items: list) -> str:
    return '<ul class="sg-list">' + "".join(f"<li>{esc_html(i)}</li>" for i in items) + "</ul>"


def verdict_badge(verdict: str) -> str:
    color = VERDICT_HEX[verdict]
    return (
        f'<span class="sg-badge-verdict" '
        f'style="background: {color}26; color: {color};">{verdict}</span>'
    )


def confidence_badge(confidence: str) -> str:
    color = CONFIDENCE_HEX[confidence]
    return (
        f'<span class="sg-badge-confidence" '
        f'style="color: {color};">confidence · {confidence}</span>'
    )


def render_report_detail(report: CoverageReport) -> None:
    st.markdown(
        f'<div class="sg-badge-row" style="margin-bottom: 0.4rem;">'
        f"{verdict_badge(report.verdict)}{confidence_badge(report.confidence)}</div>",
        unsafe_allow_html=True,
    )
    st.subheader(esc(report.script_analysis.title))
    st.markdown(
        _panel("Summary", f'<div class="sg-panel-body">{esc_html(report.summary)}</div>', "sg-panel--accent"),
        unsafe_allow_html=True,
    )

    if report.unsupported_claims:
        st.warning(
            "The QA agent flagged claims not sufficiently backed by the research "
            "(already corrected in this report, shown here for audit reference):\n\n"
            + "\n".join(f"- {esc(c)}" for c in report.unsupported_claims)
        )
    st.markdown(
        _panel("QA note", f'<div class="sg-panel-body">{esc_html(report.qa_notes)}</div>', "sg-panel--muted"),
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(_panel("Strengths", _list(report.strengths), "sg-panel--good"), unsafe_allow_html=True)
    with col2:
        st.markdown(_panel("Weaknesses", _list(report.weaknesses), "sg-panel--bad"), unsafe_allow_html=True)

    st.markdown(
        _panel(
            "Market positioning",
            f'<div class="sg-panel-body">{esc_html(report.market_positioning)}</div>',
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        _panel(
            "Verdict justification",
            f'<div class="sg-panel-body">{esc_html(report.justification)}</div>',
            "sg-panel--accent",
        ),
        unsafe_allow_html=True,
    )
    if report.dissenting_personas:
        st.info(
            "The committee did NOT reach unanimous consensus. Dissenting from the final verdict: "
            + ", ".join(esc(p) for p in report.dissenting_personas)
        )

    with st.expander("Greenlight Committee Debate (2 rounds)", expanded=False):
        opinions_by_persona_r1 = {op.persona: op for op in report.committee_round1}
        for op2 in report.committee_round2:
            op1 = opinions_by_persona_r1.get(op2.persona)
            changed = op1 is not None and op1.verdict_lean != op2.verdict_lean
            dissenting = op2.persona in report.dissenting_personas
            border_color = VERDICT_HEX[op2.verdict_lean]

            tags = ""
            if changed:
                tags += '<span class="sg-tag-changed">Changed position</span>'
            if dissenting:
                tags += '<span class="sg-tag-dissent">Dissenting</span>'

            round1_block = ""
            connector = ""
            if op1 is not None:
                round1_block = _html(
                    f"""
                    <div class="sg-debate-round">
                        <div class="sg-debate-round-label">Round 1 · {esc_html(op1.verdict_lean)}</div>
                        <div class="sg-debate-round-text">{esc_html(op1.argument)}</div>
                    </div>
                    """
                )
                connector = '<div class="sg-debate-connector"></div>'

            st.markdown(
                _html(
                    f"""
                    <div class="sg-debate-card" style="border-left-color: {border_color};">
                        <div class="sg-debate-header">
                            <span class="sg-debate-persona">{esc_html(op2.persona)}</span>
                            {verdict_badge(op2.verdict_lean)}
                            {tags}
                        </div>
                        <div class="sg-debate-rounds">
                            {round1_block}
                            {connector}
                            <div class="sg-debate-round">
                                <div class="sg-debate-round-label">Round 2 · Debate</div>
                                <div class="sg-debate-round-text">{esc_html(op2.argument)}</div>
                            </div>
                        </div>
                        <div class="sg-debate-concern"><strong>Concern:</strong> {esc_html(op2.concern)}</div>
                    </div>
                    """
                ),
                unsafe_allow_html=True,
            )

    with st.expander("Full narrative analysis"):
        sa = report.script_analysis
        st.markdown(
            _panel("Logline", f'<div class="sg-panel-body">{esc_html(sa.logline)}</div>', "sg-panel--accent")
            + _panel(
                "Genre & tone",
                _html(
                    f'<div class="sg-meta-row">'
                    f"<span><strong>Genre:</strong> {esc_html(sa.genre)}</span>"
                    f"<span><strong>Tone:</strong> {esc_html(sa.tone)}</span>"
                    f"</div>"
                ),
            ),
            unsafe_allow_html=True,
        )

        acts = "".join(
            _html(
                f'<div class="sg-item">'
                f'<div class="sg-item-head">'
                f'<span class="sg-item-tag">Act {act.act_number}</span>{esc_html(act.title)}'
                f"</div>"
                f'<div class="sg-item-body">{esc_html(act.summary)}</div>'
                f"</div>"
            )
            for act in sa.three_act_structure
        )
        st.markdown(_panel("Three-act structure", acts), unsafe_allow_html=True)

        chars = "".join(
            _html(
                f'<div class="sg-item">'
                f'<div class="sg-item-head">{esc_html(char.name)}</div>'
                f'<div class="sg-item-body">{esc_html(char.description)}</div>'
                f'<div class="sg-item-body" style="margin-top:0.3rem;">'
                f'<span class="sg-item-tag">Arc</span>{esc_html(char.arc)}'
                f"</div>"
                f"</div>"
            )
            for char in sa.main_characters
        )
        st.markdown(_panel("Main characters", chars), unsafe_allow_html=True)
        st.markdown(
            _panel("Pacing", f'<div class="sg-panel-body">{esc_html(sa.pacing_notes)}</div>'),
            unsafe_allow_html=True,
        )

    with st.expander("Full market research"):
        mr = report.market_research
        comps = "".join(
            _html(
                f'<div class="sg-item">'
                f'<div class="sg-item-head">'
                f'{esc_html(title.title)} <span class="sg-item-tag">{esc_html(title.year)}</span>'
                f"</div>"
                f'<div class="sg-item-body">{esc_html(title.box_office_or_reception)}</div>'
                f'<div class="sg-item-body" style="margin-top:0.3rem;">'
                f'<span class="sg-item-tag">Why comparable</span>{esc_html(title.similarity_notes)}'
                f"</div>"
                f"</div>"
            )
            for title in mr.comparable_titles
        )
        st.markdown(_panel("Comparable films", comps), unsafe_allow_html=True)
        st.markdown(
            _panel("Genre trends", f'<div class="sg-panel-body">{esc_html(mr.genre_trends)}</div>')
            + _panel("Market insights", _list(mr.market_insights), "sg-panel--accent"),
            unsafe_allow_html=True,
        )
        if mr.sources:
            links = "".join(
                # Agent-supplied URLs: only http(s) becomes a link, so a
                # javascript: or data: URI can never end up in an href.
                _html(
                    f"<li><a href=\"{esc_html(s)}\" target=\"_blank\" rel=\"noopener noreferrer\" "
                    f'style="color: var(--sg-accent);">{esc_html(s)}</a></li>'
                    if str(s).startswith(("http://", "https://"))
                    else f"<li>{esc_html(s)}</li>"
                )
                for s in mr.sources
            )
            st.markdown(
                _panel("Sources", f'<ul class="sg-list">{links}</ul>', "sg-panel--muted"),
                unsafe_allow_html=True,
            )


MAX_SCRIPTS = 3
SAMPLE_SCRIPT_PATH = Path(__file__).parent / "sample_scripts" / "cold_storage_sample.pdf"


@st.cache_data
def _load_sample_pdf_bytes() -> bytes:
    return SAMPLE_SCRIPT_PATH.read_bytes()


def _start_processing(source: str) -> None:
    st.session_state.processing = True
    st.session_state.results = None
    st.session_state.run_source = source


with st.container(border=True):
    st.markdown('<span class="sg-uploader-marker"></span>', unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        f"Upload one or more PDF scripts (max {MAX_SCRIPTS} per run)",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files and len(uploaded_files) > MAX_SCRIPTS:
        st.error(
            f"You uploaded {len(uploaded_files)} PDFs, the max per run is {MAX_SCRIPTS}. "
            "Remove some and try again."
        )
        uploaded_files = None

    col_generate, col_sample, col_download = st.columns(3)
    with col_generate:
        st.button(
            "Generate slate coverage",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.processing or not uploaded_files,
            on_click=_start_processing,
            args=("upload",),
        )
    with col_sample:
        st.button(
            "Try with a sample script",
            use_container_width=True,
            disabled=st.session_state.processing,
            on_click=_start_processing,
            args=("sample",),
        )
    with col_download:
        st.download_button(
            "Download sample script (PDF)",
            data=_load_sample_pdf_bytes(),
            file_name="cold_storage_sample.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

if st.session_state.processing:
    if st.session_state.run_source == "sample":
        script_texts = [extract_text_from_pdf(_load_sample_pdf_bytes())]
    else:
        script_texts = []
        with st.spinner(f"Extracting text from {len(uploaded_files)} PDF(s)..."):
            for f in uploaded_files:
                text = extract_text_from_pdf(f.read())
                if text:
                    script_texts.append(text)
                else:
                    st.warning(f"Couldn't extract text from {f.name} (scanned PDF?), skipping it.")

    if not script_texts:
        st.error("No PDF produced readable text.")
        st.session_state.processing = False
    else:
        status_msg = (
            f"Analyzing {len(script_texts)} script(s), researching the market in parallel, "
            "auditing quality, and prioritizing the slate... this can take a few minutes."
        )
        with st.spinner(status_msg):
            try:
                reports, ranking = run_slate_triage(script_texts)
            except RateLimitExceeded as exc:
                st.session_state.processing = False
                st.warning(str(exc))
                st.stop()
            except Exception as exc:  # noqa: BLE001 — surface any pipeline failure to the user
                st.session_state.processing = False
                st.error(f"Error generating coverage: {exc}")
                st.stop()

        st.session_state.results = (reports, ranking)
        st.session_state.processing = False

if st.session_state.results is not None:
    reports, ranking = st.session_state.results
    reports_by_title = {r.script_analysis.title: r for r in reports}

    st.header("Slate prioritization")
    for entry in ranking.ranked_slate:
        st.markdown(
            f'<div style="margin-bottom: 0.6rem;">'
            f'<span style="color: var(--sg-text); font-weight: 600;">#{entry.rank} — {esc_html(entry.title)}</span> '
            f'<span class="sg-badge-row">{verdict_badge(entry.verdict)}{confidence_badge(entry.confidence)}</span>'
            f'<br><span style="color: var(--sg-text-muted); font-size: 0.9rem;">{esc_html(entry.one_line_rationale)}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("**Portfolio observations**")
    for insight in ranking.portfolio_insights:
        st.markdown(f"- {esc(insight)}")

    st.markdown("**Executive recommendation**")
    st.write(esc(ranking.overall_recommendation))

    st.divider()
    st.header("Individual coverage per script")
    for entry in ranking.ranked_slate:
        report = reports_by_title.get(entry.title)
        if report is None:
            continue
        st.markdown(f"## #{entry.rank} — {esc(report.script_analysis.title)}")
        render_report_detail(report)
        st.divider()
