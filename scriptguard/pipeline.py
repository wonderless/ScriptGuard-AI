"""Agent orchestration with google-adk (SequentialAgent + ParallelAgent + LoopAgent + Runner).

Per-script architecture:

    ScriptAnalystAgent
        -> ParallelAgent(ComparableTitlesAgent, GenreTrendsAgent)   [real concurrent research]
        -> MarketResearchFormatterAgent
        -> ParallelAgent(4 personas: round 1 opinions, independent)
        -> ParallelAgent(4 personas: round 2 opinions, real debate vs round 1)
        -> GreenlightModeratorAgent                                 [synthesizes the verdict]
        -> LoopAgent(CoverageCriticAgent, ExitCheckAgent, CoverageReviserAgent)  [self-QA]

At the slate level (several scripts): each script runs the pipeline above independently,
then SlateRankingAgent prioritizes them as a portfolio.
"""

import asyncio
import json
import platform
import re
import threading
import time
import uuid

if platform.system() == "Windows":
    # Avoids the cosmetic "Fatal error on SSL transport" traceback that Windows'
    # ProactorEventLoop throws when closing async HTTP clients (httpx) between pipeline runs.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    """Reuses a single event loop for every pipeline run in the process (e.g. every
    Streamlit click), instead of creating/closing one per call with asyncio.run().
    Repeatedly closing and reopening the loop is what triggers the cosmetic 'Fatal error
    on SSL transport' when destroying async HTTP clients mid-use."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop

from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from scriptguard.agents.greenlight_committee import (
    PERSONA_KEYS,
    greenlight_round1_agent,
    greenlight_round2_agent,
    moderator_agent,
)
from scriptguard.agents.market_research import (
    market_research_formatter_agent,
    market_research_parallel_agent,
)
from scriptguard.agents.qa_critic import coverage_qa_loop_agent
from scriptguard.agents.script_analyst import script_analyst_agent
from scriptguard.agents.slate_ranking import slate_ranking_agent
from scriptguard.schemas import (
    CoverageReport,
    CoverageVerdict,
    MarketResearch,
    PersonaOpinion,
    QACritique,
    ScriptAnalysis,
    SlateRanking,
)

APP_NAME = "scriptguard_ai"

RETRYABLE_MARKERS = ("503", "UNAVAILABLE", "overloaded", "high demand", "429", "RESOURCE_EXHAUSTED")
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 5


def _is_retryable(exc: Exception) -> bool:
    message = str(exc)
    return any(marker in message for marker in RETRYABLE_MARKERS)


class RateLimitExceeded(Exception):
    """The app-wide max runs-per-hour limit was reached."""

    def __init__(self, retry_after_seconds: float):
        self.retry_after_seconds = retry_after_seconds
        minutes = max(1, round(retry_after_seconds / 60))
        super().__init__(
            f"Reached the maximum of {MAX_RUNS_PER_HOUR} runs per hour. "
            f"Try again in ~{minutes} minute(s)."
        )


MAX_RUNS_PER_HOUR = 5
RATE_LIMIT_WINDOW_SECONDS = 3600

# Process-wide global counter (not per Streamlit session): Streamlit Community Cloud
# serves every visitor from a single process, so a st.session_state limit wouldn't cap
# the app's aggregate usage across different users.
_run_timestamps: list[float] = []
_rate_limit_lock = threading.Lock()


def _check_and_register_run() -> None:
    """Registers a run and raises RateLimitExceeded if the per-hour limit was exceeded.

    Each call counts as ONE run (one click of "Generate slate coverage"), regardless of
    how many scripts the slate includes."""
    now = time.monotonic()
    with _rate_limit_lock:
        while _run_timestamps and now - _run_timestamps[0] > RATE_LIMIT_WINDOW_SECONDS:
            _run_timestamps.pop(0)
        if len(_run_timestamps) >= MAX_RUNS_PER_HOUR:
            retry_after = RATE_LIMIT_WINDOW_SECONDS - (now - _run_timestamps[0])
            raise RateLimitExceeded(retry_after)
        _run_timestamps.append(now)


coverage_pipeline_agent = SequentialAgent(
    name="CoveragePipelineAgent",
    description="Analyzes a script, researches the market in parallel, runs a debating "
    "greenlight committee, synthesizes the verdict, and audits/corrects it.",
    sub_agents=[
        script_analyst_agent,
        market_research_parallel_agent,
        market_research_formatter_agent,
        greenlight_round1_agent,
        greenlight_round2_agent,
        moderator_agent,
        coverage_qa_loop_agent,
    ],
)


def _parse_model(value, model_cls: type[BaseModel]) -> BaseModel:
    """Converts whatever ended up in session.state into a Pydantic instance, tolerating
    that some agents (the ones combining tools) return plain text instead of the object
    already parsed by output_schema."""
    if isinstance(value, model_cls):
        return value
    if isinstance(value, BaseModel):
        return model_cls.model_validate(value.model_dump())
    if isinstance(value, dict):
        return model_cls.model_validate(value)
    if isinstance(value, str):
        cleaned = re.sub(r"^```(json)?|```$", "", value.strip(), flags=re.MULTILINE).strip()
        return model_cls.model_validate(json.loads(cleaned))
    raise TypeError(f"Could not parse {value!r} as {model_cls.__name__}")


async def _run_single_script_pipeline(script_text: str) -> CoverageReport:
    session_service = InMemorySessionService()
    user_id = "hackathon_user"
    session_id = str(uuid.uuid4())

    await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
        state={"script_text": script_text},
    )

    runner = Runner(
        agent=coverage_pipeline_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    initial_message = types.Content(
        role="user",
        parts=[types.Part(text="Generate the coverage report for the uploaded script.")],
    )

    async for _event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=initial_message,
    ):
        pass  # the relevant state lives in session.state, not in the last event

    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    state = session.state

    script_analysis = _parse_model(state["script_analysis"], ScriptAnalysis)
    market_research = _parse_model(state["market_research"], MarketResearch)
    coverage_verdict = _parse_model(state["coverage_verdict"], CoverageVerdict)
    qa_critique = _parse_model(state["qa_critique"], QACritique)
    committee_round1 = [_parse_model(state[f"opinion_{key}_r1"], PersonaOpinion) for key in PERSONA_KEYS]
    committee_round2 = [_parse_model(state[f"opinion_{key}_r2"], PersonaOpinion) for key in PERSONA_KEYS]
    dissenting_personas = [op.persona for op in committee_round2 if op.verdict_lean != coverage_verdict.verdict]

    return CoverageReport(
        **coverage_verdict.model_dump(),
        script_analysis=script_analysis,
        market_research=market_research,
        confidence=qa_critique.confidence,
        qa_notes=qa_critique.notes,
        unsupported_claims=qa_critique.unsupported_claims if qa_critique.status == "NEEDS_REVISION" else [],
        committee_round1=committee_round1,
        committee_round2=committee_round2,
        dissenting_personas=dissenting_personas,
    )


async def _run_with_retries(coro_factory):
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001 — only retry known transient errors
            last_exc = exc
            if not _is_retryable(exc) or attempt == MAX_RETRIES - 1:
                raise
            wait_seconds = BASE_BACKOFF_SECONDS * (2**attempt)
            await asyncio.sleep(wait_seconds)
    raise last_exc  # pragma: no cover


async def _run_slate_ranking(reports: list[CoverageReport]) -> SlateRanking:
    session_service = InMemorySessionService()
    user_id = "hackathon_user"
    session_id = str(uuid.uuid4())

    summaries = [
        {
            "title": r.script_analysis.title,
            "verdict": r.verdict,
            "confidence": r.confidence,
            "summary": r.summary,
            "market_positioning": r.market_positioning,
            "comparable_titles": [c.title for c in r.market_research.comparable_titles],
        }
        for r in reports
    ]

    await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
        state={"slate_summaries": json.dumps(summaries, ensure_ascii=False)},
    )

    runner = Runner(
        agent=slate_ranking_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    initial_message = types.Content(
        role="user",
        parts=[types.Part(text="Prioritize this slate of scripts.")],
    )

    async for _event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=initial_message,
    ):
        pass

    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    return _parse_model(session.state["slate_ranking"], SlateRanking)


def run_coverage_pipeline(script_text: str) -> CoverageReport:
    """Synchronous entry point: runs the full pipeline for one script, with automatic
    retries on transient Gemini errors (503/429)."""
    _check_and_register_run()
    return _get_loop().run_until_complete(_run_with_retries(lambda: _run_single_script_pipeline(script_text)))


def run_slate_triage(script_texts: list[str]) -> tuple[list[CoverageReport], SlateRanking]:
    """Synchronous entry point: runs the coverage pipeline for each script in the slate,
    then prioritizes them as a portfolio."""
    _check_and_register_run()

    async def _run_all():
        reports = []
        for script_text in script_texts:
            report = await _run_with_retries(lambda st=script_text: _run_single_script_pipeline(st))
            reports.append(report)
        ranking = await _run_with_retries(lambda: _run_slate_ranking(reports))
        return reports, ranking

    return _get_loop().run_until_complete(_run_all())
