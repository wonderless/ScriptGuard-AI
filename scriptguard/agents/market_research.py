"""Market Research: two research agents run in PARALLEL (ParallelAgent) using Parallel's
real Search API, and a third agent synthesizes both into structured JSON.

Split into research (with tools) + formatter (no tools) because ADK doesn't reliably
support combining `tools` + `output_schema` on the same LlmAgent (only Gemini 3.0 handles
it well). The two research agents run concurrently via ParallelAgent, each writing to its
own session.state key.
"""

import os

from google.adk.agents import LlmAgent, ParallelAgent
from parallel import Parallel

from scriptguard.schemas import MarketResearch

GEMINI_MODEL = "gemini-3.5-flash-lite"

_parallel_client: Parallel | None = None


def _get_parallel_client() -> Parallel:
    global _parallel_client
    if _parallel_client is None:
        _parallel_client = Parallel(api_key=os.getenv("PARALLEL_API_KEY"))
    return _parallel_client


def parallel_search(objective: str, search_queries: list[str]) -> dict:
    """Searches the web for real, current information using Parallel's Search API.

    Args:
        objective (str): Concise, self-contained search objective, including the
            key entity or topic.
        search_queries (list[str]): 2-3 diverse search queries (3-6 words each),
            varying entities, synonyms, and angles.

    Returns:
        dict: Search results with title, URL, and text excerpts per result.
    """
    client = _get_parallel_client()
    response = client.search(
        objective=objective,
        search_queries=search_queries,
        mode="basic",
        max_chars_total=6000,
    )
    results = []
    for result in response.results:
        results.append(
            {
                "title": result.title,
                "url": result.url,
                "excerpts": result.excerpts,
            }
        )
    return {"results": results}


comparable_titles_agent = LlmAgent(
    name="ComparableTitlesAgent",
    model=GEMINI_MODEL,
    description="Researches real comparable films, with box office and reception figures, via web search.",
    instruction="""You are a comps (comparable titles) analyst at a film studio.

Use the `parallel_search` tool to research, based on this script analysis:
{script_analysis}

Find 3 to 5 REAL comparable films (same genre/tone), with:
- Release year
- Box office figures and/or budget if available
- Critical/audience reception
- Why they're comparable to this script

Make several `parallel_search` calls with different objectives if needed to cover
multiple titles. Write a clear text summary with all the information found (titles,
years, figures, comparables) and the EXACT source URLs. Don't invent figures: if you
can't find a data point, say so explicitly instead of estimating it.

Respond ALWAYS in English.""",
    tools=[parallel_search],
    output_key="research_notes_comps",
)

genre_trends_agent = LlmAgent(
    name="GenreTrendsAgent",
    model=GEMINI_MODEL,
    description="Researches current market trends for the script's genre, via web search.",
    instruction="""You are a market trends analyst at a film studio.

Use the `parallel_search` tool to research, based on this script analysis:
{script_analysis}

Find:
- Current genre/subgenre trends in the market (streaming, theatrical, VOD)
- What similar projects are gaining traction right now
- Actionable insights for deciding whether to produce this script

Make several `parallel_search` calls with different objectives if needed. Write a clear
text summary with all the information found and the EXACT source URLs. Don't invent
data: if you can't find something, say so explicitly.

Respond ALWAYS in English.""",
    tools=[parallel_search],
    output_key="research_notes_trends",
)

market_research_parallel_agent = ParallelAgent(
    name="MarketResearchParallelAgent",
    description="Runs comparable-titles research and market-trends research concurrently.",
    sub_agents=[comparable_titles_agent, genre_trends_agent],
)

market_research_formatter_agent = LlmAgent(
    name="MarketResearchFormatterAgent",
    model=GEMINI_MODEL,
    description="Converts the market research notes (comparables + trends) into structured JSON.",
    instruction="""Convert the following market research notes into structured JSON:

COMPARABLE TITLES NOTES (box office/reception):
{research_notes_comps}

MARKET TRENDS NOTES:
{research_notes_trends}

Respond ONLY with valid JSON matching the given schema exactly, with no extra text.
Include ALL source URLs mentioned in both sets of notes inside "sources". Don't invent
or fill in data the notes don't mention.

Respond ALWAYS in English.""",
    output_schema=MarketResearch,
    output_key="market_research",
)
