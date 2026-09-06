"""Slate Ranking Agent: prioritizes a set of already-analyzed scripts, the way a studio
acquisitions team would review its weekly slate (not a single isolated read, but a
portfolio-level decision)."""

from google.adk.agents import LlmAgent

from scriptguard.schemas import SlateRanking

GEMINI_MODEL = "gemini-3.5-flash-lite"

slate_ranking_agent = LlmAgent(
    name="SlateRankingAgent",
    model=GEMINI_MODEL,
    description="Prioritizes a slate of individually-evaluated scripts.",
    instruction="""You are the Head of Acquisitions at a film studio. You have the
individual coverage for several scripts (one per line, in compact JSON):

{slate_summaries}

Your job is to prioritize them as a portfolio, NOT just repeat each one's individual
verdict. Consider:
- Individual verdict and confidence
- Genre/tone diversification across the scripts (avoid recommending 3 identical ones)
- Risk that they share the same comparable films (niche cannibalization)
- Budget/risk balance if it can be inferred from market_positioning

Produce a ranking from 1 (highest priority) to N, each with a one-line rationale, plus
portfolio-level observations and an overall executive recommendation.

Respond ALWAYS in English, and ONLY with valid JSON matching the given schema exactly.""",
    output_schema=SlateRanking,
    output_key="slate_ranking",
)
