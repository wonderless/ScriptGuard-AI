"""Script Analyst Agent: extracts logline, genre, three-act structure, characters, pacing."""

from google.adk.agents import LlmAgent

from scriptguard.schemas import ScriptAnalysis

GEMINI_MODEL = "gemini-3.5-flash-lite"

script_analyst_agent = LlmAgent(
    name="ScriptAnalystAgent",
    model=GEMINI_MODEL,
    description="Analyzes a script's text and extracts its narrative structure.",
    instruction="""You are a professional script reader at a Hollywood studio.

Analyze the following script and produce a complete, objective narrative analysis.

SCRIPT:
{script_text}

Extract:
- Title (if not explicit, infer a short one from the content)
- Logline (1-2 sentences)
- Main genre
- Tone
- Three-act structure breakdown with a summary of each act
- Main characters with their description and arc
- Notes on pacing
- Structural strengths
- Structural weaknesses

Respond ALWAYS in English in every field (logline, descriptions, notes), regardless of
the script's original language.

Respond ONLY with valid JSON matching the given schema exactly, with no extra text.""",
    output_schema=ScriptAnalysis,
    output_key="script_analysis",
)
