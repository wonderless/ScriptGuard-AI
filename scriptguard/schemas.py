"""Pydantic schemas shared between agents (script analysis, market research, final coverage report)."""

from typing import List, Literal

from pydantic import BaseModel, Field


class Character(BaseModel):
    name: str
    description: str = Field(description="Who the character is and their role in the story")
    arc: str = Field(description="The character's arc/transformation over the course of the script")


class ActBreakdown(BaseModel):
    act_number: int
    title: str = Field(description="Short name for the act, e.g. 'Setup'")
    summary: str


class ScriptAnalysis(BaseModel):
    title: str
    logline: str = Field(description="One- or two-sentence summary of the central premise")
    genre: str
    tone: str
    three_act_structure: List[ActBreakdown]
    main_characters: List[Character]
    pacing_notes: str = Field(description="Notes on the script's pacing")
    structural_strengths: List[str]
    structural_weaknesses: List[str]


class ComparableTitle(BaseModel):
    title: str
    year: str
    box_office_or_reception: str = Field(description="Box office figures and/or critical/audience reception")
    similarity_notes: str = Field(description="Why it's comparable to this script")


class MarketResearch(BaseModel):
    comparable_titles: List[ComparableTitle]
    genre_trends: str = Field(description="Current genre/market trends")
    market_insights: List[str] = Field(description="Actionable insights for the production decision")
    sources: List[str] = Field(default_factory=list, description="URLs used as research sources")


class PersonaOpinion(BaseModel):
    """Opinion of one greenlight committee member in a single debate round."""

    persona: str = Field(description="Role name, e.g. 'Financial Analyst'")
    verdict_lean: Literal["RECOMMEND", "CONSIDER", "PASS"] = Field(
        description="This member's lean ONLY, not the committee's consensus"
    )
    argument: str = Field(description="Main argument supporting their position (1-2 sentences)")
    concern: str = Field(description="This member's main concern or doubt (1-2 sentences)")


class CoverageVerdict(BaseModel):
    """Raw output from the Greenlight Committee Moderator (without the embedded analyses)."""

    verdict: Literal["RECOMMEND", "CONSIDER", "PASS"]
    summary: str = Field(description="Executive summary of the coverage")
    strengths: List[str]
    weaknesses: List[str]
    market_positioning: str = Field(description="How the script is positioned against the current market")
    justification: str = Field(description="Justification of the verdict, combining narrative and market analysis")


class QACritique(BaseModel):
    """Output from the QA critic agent that audits the coverage before it ships."""

    status: Literal["APPROVED", "NEEDS_REVISION"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="Confidence that the report's claims are backed by the actual research"
    )
    unsupported_claims: List[str] = Field(
        default_factory=list,
        description="Claims in the coverage (figures, trends, comparables) NOT backed by market_research",
    )
    notes: str = Field(description="Brief explanation of the QA verdict")


class CoverageReport(CoverageVerdict):
    """Final report assembled in code from the verdict + the prior analyses + QA."""

    script_analysis: ScriptAnalysis
    market_research: MarketResearch
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    qa_notes: str
    unsupported_claims: List[str] = Field(default_factory=list)
    committee_round1: List[PersonaOpinion] = Field(description="Initial, independent opinions from the committee")
    committee_round2: List[PersonaOpinion] = Field(description="Opinions after the debate round")
    dissenting_personas: List[str] = Field(
        default_factory=list,
        description="Committee members whose final (round 2) position differs from the synthesized verdict",
    )


class SlateEntry(BaseModel):
    rank: int
    title: str
    verdict: Literal["RECOMMEND", "CONSIDER", "PASS"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    one_line_rationale: str = Field(description="Why the script ended up in this ranking position")


class SlateRanking(BaseModel):
    """Prioritization of a slate (set) of scripts, the way a studio acquisitions team would."""

    ranked_slate: List[SlateEntry]
    portfolio_insights: List[str] = Field(
        description="Portfolio-level observations: genre diversification, repeated-comparables risk, "
        "budget balance, etc."
    )
    overall_recommendation: str = Field(description="Executive recommendation on what to prioritize and why")
