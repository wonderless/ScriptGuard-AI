"""Self-critique/revision loop: a critic agent audits the coverage against the real
research before it ships, and the loop corrects itself or closes on its own.

ADK LoopAgent pattern: [critic, exit_check, reviser] run in sequence within each
iteration.
- critic: audits the report against the real research and writes a QACritique.
- exit_check: ONLY decides whether to close the loop (calls the `exit_loop` tool); never
  touches coverage_verdict, so the tool call's auto-generated summary text doesn't
  overwrite it.
- reviser: rewrites coverage_verdict (corrected if needed, unchanged if already
  approved). Having no tools, it can use output_schema reliably.
This ordering is safe regardless of whether ADK stops the loop as soon as exit_loop is
called or only at the end of the iteration: coverage_verdict never ends up in an invalid
state either way.
"""

from google.adk.agents import LlmAgent, LoopAgent
from google.adk.tools.tool_context import ToolContext

from scriptguard.schemas import CoverageVerdict, QACritique

GEMINI_MODEL = "gemini-3.5-flash-lite"


def exit_loop(tool_context: ToolContext) -> dict:
    """Signals that the coverage report was approved and the review loop should end."""
    tool_context.actions.escalate = True
    tool_context.actions.skip_summarization = True
    return {}


coverage_critic_agent = LlmAgent(
    name="CoverageCriticAgent",
    model=GEMINI_MODEL,
    description="Audits the coverage looking for claims not backed by the real research.",
    instruction="""You are the quality-control editor at a film studio. Your job is to
catch claims in the coverage that are NOT backed by the real research, before the report
reaches an executive who will make an investment decision based on it.

CURRENT COVERAGE REPORT (JSON):
{coverage_verdict}

SCRIPT ANALYSIS (source of truth for the narrative):
{script_analysis}

REAL MARKET RESEARCH (source of truth for the market, with URLs):
{market_research}

Review strengths, weaknesses, market_positioning, and justification in the report. Flag
as "unsupported_claims" any figure, trend, or comparable mentioned in the coverage that
does NOT appear (or can't reasonably be derived from) market_research or script_analysis.
Ignore wording differences; only flag substantive claims without backing.

Assign:
- status=APPROVED if there are no unsupported claims (or they're minor/stylistic)
- status=NEEDS_REVISION if there's at least one substantive unsupported claim
- confidence=HIGH/MEDIUM/LOW based on how well-backed the report is overall

Respond ALWAYS in English, and ONLY with valid JSON matching the given schema exactly.""",
    output_schema=QACritique,
    output_key="qa_critique",
)

exit_check_agent = LlmAgent(
    name="ExitCheckAgent",
    model=GEMINI_MODEL,
    description="Closes the QA loop if the critic already approved the report.",
    instruction="""QA CRITIQUE:
{qa_critique}

If status=APPROVED: call the `exit_loop` tool right now.
If status=NEEDS_REVISION: don't call any tool, respond only with the word CONTINUE.""",
    tools=[exit_loop],
)

coverage_reviser_agent = LlmAgent(
    name="CoverageReviserAgent",
    model=GEMINI_MODEL,
    description="Rewrites the coverage, fixing the unsupported claims flagged by QA.",
    instruction="""QA CRITIQUE:
{qa_critique}

CURRENT COVERAGE REPORT:
{coverage_verdict}

If the critique has status=APPROVED: return the current report as-is, unchanged.

If status=NEEDS_REVISION: rewrite the report, fixing every claim listed in
unsupported_claims (remove it or soften it so it stays consistent only with verifiable
data from the context). Don't invent replacements; if you drop a figure, adjust the
surrounding text so it still reads naturally.

Respond ALWAYS in English, and ONLY with valid JSON matching the given schema exactly.""",
    output_schema=CoverageVerdict,
    output_key="coverage_verdict",
)

coverage_qa_loop_agent = LoopAgent(
    name="CoverageQALoopAgent",
    description="Audits and corrects the coverage until it's approved or the max iterations are reached.",
    sub_agents=[coverage_critic_agent, exit_check_agent, coverage_reviser_agent],
    max_iterations=3,
)
