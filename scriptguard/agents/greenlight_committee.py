"""Greenlight Committee: replaces the generic single orchestrator with 4 persona agents
carrying real industry biases who evaluate the script in PARALLEL (round 1, independent),
then DEBATE in a second round (each reacts to the others' initial opinions), and a
Moderator synthesizes the final verdict reflecting the debate's actual outcome — not a
mechanical average of positions.
"""

from google.adk.agents import LlmAgent, ParallelAgent

from scriptguard.schemas import CoverageVerdict, PersonaOpinion

GEMINI_MODEL = "gemini-3.5-flash-lite"

PERSONAS = {
    "producer": {
        "label": "Creative Producer",
        "priority": "narrative quality, character depth, and artistic execution",
        "concern": "that the script is generic, poorly executed, or sacrifices story for commercial formula",
    },
    "distribution": {
        "label": "International Distribution Executive",
        "priority": "commercial potential: fit with real comparables, genre/market trends, "
        "and appeal to international audiences",
        "concern": "that the script has no clear commercial hook or doesn't fit what the market is buying right now",
    },
    "finance": {
        "label": "Financial Analyst",
        "priority": "financial risk: the relationship between likely budget and the real ROI of "
        "the comparables, and financing viability",
        "concern": "that the project requires a budget the comparables don't justify, or that the expected "
        "return is uncertain",
    },
    "indie": {
        "label": "Indie/Festival Reader",
        "priority": "originality, cultural authenticity, and festival/critical potential",
        "concern": "that the project dilutes what makes it unique to resemble another generic commercial product",
    },
}

PERSONA_KEYS = list(PERSONAS.keys())


def _round1_instruction(key: str) -> str:
    persona = PERSONAS[key]
    return f"""You are {persona['label']}, a member of a studio greenlight committee.
Your priority is: {persona['priority']}.
Your main concern tends to be: {persona['concern']}.

Evaluate this script:

NARRATIVE ANALYSIS:
{{script_analysis}}

MARKET RESEARCH:
{{market_research}}

Give your initial opinion as part of the committee. Defend YOUR particular perspective —
don't try to be neutral or cover every angle, that's what the full committee is for.

Respond ALWAYS in English, and ONLY with valid JSON matching the given schema exactly:
persona (your role name, "{persona['label']}"), verdict_lean (RECOMMEND/CONSIDER/PASS
from your perspective), argument (your main argument, 1-2 sentences), concern (your main
doubt, 1-2 sentences)."""


def _round2_instruction(key: str) -> str:
    persona = PERSONAS[key]
    others = [other_key for other_key in PERSONAS if other_key != key]
    others_block = "\n".join(
        f"- {PERSONAS[other_key]['label']}: {{opinion_{other_key}_r1}}" for other_key in others
    )
    return f"""You are {persona['label']}, in the second round of the greenlight committee's debate.

Your initial opinion was: {{opinion_{key}_r1}}

Initial opinions from the rest of the committee:
{others_block}

React: if another member's argument seems valid to you and changes your evaluation,
adjust your verdict_lean and say so EXPLICITLY in your argument (what made you change
your mind). If you still disagree, reinforce your position by directly responding to the
strongest objection you've seen raised by another member.

Respond ALWAYS in English, and ONLY with valid JSON matching the given schema exactly:
persona (your role name, "{persona['label']}"), verdict_lean, argument, concern."""


def _make_persona_agent(key: str, round_num: int) -> LlmAgent:
    instruction = _round1_instruction(key) if round_num == 1 else _round2_instruction(key)
    return LlmAgent(
        name=f"{key.capitalize()}PersonaR{round_num}Agent",
        model=GEMINI_MODEL,
        description=f"Opinion of {PERSONAS[key]['label']} in round {round_num} of the greenlight committee.",
        instruction=instruction,
        output_schema=PersonaOpinion,
        output_key=f"opinion_{key}_r{round_num}",
    )


greenlight_round1_agent = ParallelAgent(
    name="GreenlightRound1Agent",
    description="Initial, independent opinions from the 4 greenlight committee members.",
    sub_agents=[_make_persona_agent(key, 1) for key in PERSONA_KEYS],
)

greenlight_round2_agent = ParallelAgent(
    name="GreenlightRound2Agent",
    description="Second round: each member reacts to the others' initial opinions (real debate).",
    sub_agents=[_make_persona_agent(key, 2) for key in PERSONA_KEYS],
)

_committee_block = "\n".join(
    f"- {PERSONAS[key]['label']} — Round 1: {{opinion_{key}_r1}} | Round 2 (after debate): {{opinion_{key}_r2}}"
    for key in PERSONA_KEYS
)

moderator_agent = LlmAgent(
    name="GreenlightModeratorAgent",
    model=GEMINI_MODEL,
    description="Synthesizes the greenlight committee's debate into a final coverage verdict.",
    instruction=f"""You are the Moderator of the greenlight committee (Head Story Analyst). The
committee debated this script over 2 rounds:

{_committee_block}

NARRATIVE ANALYSIS:
{{script_analysis}}

MARKET RESEARCH:
{{market_research}}

Synthesize a final verdict (RECOMMEND/CONSIDER/PASS) that reflects the REAL outcome of
the debate, not a mechanical average of positions. If the committee didn't reach
consensus, say so explicitly in the justification: which position prevailed, which
member(s) dissented, and why the winning position was prioritized over the other(s).

Respond ALWAYS in English, and ONLY with valid JSON matching the given schema exactly.""",
    output_schema=CoverageVerdict,
    output_key="coverage_verdict",
)
