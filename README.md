# ScriptGuard AI

Multi-agent system that simulates a studio **greenlight committee** — 4 persona agents
with real industry biases (creative, international distribution, financial,
indie/festival) that analyze a script, **debate each other over 2 rounds**, and a
moderator synthesizes the verdict — combined with real parallel market research,
self-audited quality control, and prioritization of a full slate of scripts (not just
one at a time).

Built for the **Agentic Cinema: The Blockbuster Hackathon** (Google Cloud, Parallel track).

## Project status

**Functional end-to-end and validated with the real API** (Gemini + Parallel Search), not
just "it compiles":

- Short individual script (4 pages / ~420 words): ~24 seconds, coherent verdict.
- Individual script at real feature-length size (~20,300 words, roughly ~100 pages):
  **25.8 seconds**, no errors, no token issues — only the `ScriptAnalystAgent` processes
  the script's full text; the other 15 agents work on the already-summarized analysis, so
  runtime doesn't scale with script length.
- Slate of 3 scripts across distinct genres (adventure/sci-fi 20K words, comedy 6K,
  horror 9K): **81 seconds total**. The system detected real dissent within a committee
  (Financial Analyst disagreeing with the rest) and the portfolio ranking correctly
  identified cannibalization risk between two similarly-toned projects.

**Pending (out of scope for this work, on the author):** pushing the repo to GitHub as
public with the license visible in "About", deploying with a public URL (Streamlit
Community Cloud / Cloud Run), and recording the demo video — all of this takes minutes
and is done manually when the dev session wraps up.

## Why this isn't just another report generator

The first version of this project was a 4-step `SequentialAgent` producing a report with
a single generic verdict — functional, but indistinguishable from any other "AI script
coverage" tool someone else might build for this same hackathon. It was redesigned twice:

- **Parallel market research** (`ParallelAgent`): two agents with real access to
  Parallel's Search API research box-office comparables and genre trends
  **concurrently**, not in a single sequential call.
- **A Greenlight Committee that actually debates** (`ParallelAgent` x2 + synthesis):
  instead of a single orchestrator that "decides," 4 persona agents (Creative Producer,
  International Distribution, Financial Analyst, Indie/Festival Reader) give their
  initial opinion independently and then **react to each other's arguments** in a second
  round — each can change position if another's argument convinces them, or reinforce
  their own by responding to the strongest objection. The Moderator synthesizes the final
  verdict reflecting the debate's real outcome (consensus or explicit dissent), not an
  average.
- **Self-critique and revision** (`LoopAgent`): a QA agent audits every claim in the
  coverage against the real research (it doesn't blindly trust what the previous LLM
  generated) and, if it finds unsupported figures or trends, triggers an automatic
  revision of the report before it ships. The loop closes on its own once the report is
  approved (or a max iteration count is reached).
- **Slate prioritization**: you can upload several scripts at once. Each goes through its
  own greenlight committee, and then a "Head of Acquisitions" agent prioritizes them as a
  portfolio (genre diversification, repeated-comparables risk, budget balance) — the real
  use case of an acquisitions team, not an isolated read.

## Architecture

```mermaid
flowchart TD
    PDF["Script PDF(s)"] --> SA

    subgraph PIPE["Per-script pipeline (SequentialAgent)"]
        SA["ScriptAnalystAgent<br/>(Gemini)"] --> PAR

        subgraph PAR["MarketResearchParallelAgent<br/>(ParallelAgent — run concurrently)"]
            direction LR
            CT["ComparableTitlesAgent<br/>+ parallel_search tool"]
            GT["GenreTrendsAgent<br/>+ parallel_search tool"]
        end

        PAR --> FMT["MarketResearchFormatterAgent<br/>(Gemini, no tools)"]

        subgraph R1["GreenlightRound1Agent (ParallelAgent) — independent opinions"]
            direction LR
            P1["Creative Producer"]
            D1["Intl. Distribution"]
            F1["Financial Analyst"]
            I1["Indie/Festival Reader"]
        end

        subgraph R2["GreenlightRound2Agent (ParallelAgent) — real debate"]
            direction LR
            P2["Creative Producer<br/>reacts to the other 3"]
            D2["Intl. Distribution<br/>reacts to the other 3"]
            F2["Financial Analyst<br/>reacts to the other 3"]
            I2["Indie/Festival Reader<br/>reacts to the other 3"]
        end

        FMT --> R1 --> R2 --> MOD["GreenlightModeratorAgent<br/>synthesizes consensus or dissent"]

        subgraph LOOP["CoverageQALoopAgent (LoopAgent, max 3 iterations)"]
            direction TB
            CRIT["CoverageCriticAgent<br/>audits vs. real research"] --> EXIT["ExitCheckAgent<br/>exit_loop tool"]
            EXIT --> REV["CoverageReviserAgent<br/>revises or copies through unchanged"]
            REV -.repeats if NEEDS_REVISION.-> CRIT
        end

        MOD --> LOOP
    end

    LOOP --> REPORT["CoverageReport<br/>(verdict + confidence + full debate)"]
    REPORT --> RANK["SlateRankingAgent<br/>(Gemini, no tools)"]
    RANK --> UI["Streamlit: slate ranking<br/>+ per-script debate transcript"]
```

All research/committee/formatting agents use **Gemini** via `google-genai`, orchestrated
with **Google ADK** (17 agents in total, coordinated through 1 `SequentialAgent` + 3
`ParallelAgent` + 1 `LoopAgent`). Research uses the **official Parallel SDK**
(`parallel-web`) as a real tool invoked at runtime.

> Technical note 1: ADK doesn't reliably support combining `tools` + structured output
> (`output_schema`) on the same `LlmAgent` except with Gemini 3.0, so agents with tools
> write free text and a separate formatter agent (no tools) converts it to
> Pydantic-validated JSON.

> Technical note 2: on Windows, `pipeline.py` reuses a single asyncio event loop across
> every run in the process (every Streamlit click) instead of creating and closing a new
> one per call — repeatedly closing/reopening the loop triggered a cosmetic traceback
> ("Fatal error on SSL transport") when destroying async HTTP clients mid-use. Verified
> without that traceback after 2+ consecutive runs in the same process.

## Known limitations (honesty first)

- The QA agent audits **internal consistency** (is the figure in the coverage backed by
  the research collected?), it doesn't do additional external fact-checking of those
  figures — it trusts that Parallel's Search API returned real data.
- The slate ranking is only as good as the individual coverage of each script feeding it;
  it doesn't recompute additional research at the portfolio level.
- The committee debate has exactly 2 fixed rounds (independent + reaction), not a
  variable number of rounds until consensus — a deliberate decision so behavior stays
  deterministic and testable instead of an open-ended loop. Both rounds always run,
  whether or not the 4 members agree.
- Cost/time scales linearly with the number of scripts in the slate: each additional
  script adds ~25-30 seconds, 16 Gemini calls, and 2 to 6 real Parallel searches. A large
  slate (10+ scripts) can take several minutes.
- Max 3 scripts per run and a hard cap of 5 runs per hour (app-wide, not per user) — a
  deliberate cost-control guardrail for a publicly-hosted demo, not a technical ceiling of
  the pipeline itself.
- No "demo mode" without API keys: running the project requires your own Gemini and
  Parallel keys with active billing.

## Requirements

- Python 3.11+ (also tested on 3.10)
- A Gemini API key (`GOOGLE_API_KEY`) — works with an AI Studio key or one generated from
  Google Cloud Console with billing enabled (recommended, avoids 429s from the free tier)
- A Parallel API key (`PARALLEL_API_KEY`) — https://platform.parallel.ai

## Installation

```bash
git clone <this-repo-url>
cd "ScriptGuard AI"
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

Set up your API keys:

```bash
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
```

Edit `.env` and fill in:

```
GOOGLE_API_KEY=your_gemini_api_key
PARALLEL_API_KEY=your_parallel_api_key
```

## Running it

```bash
streamlit run app.py
```

Open the URL Streamlit shows in your browser (`http://localhost:8501` by default), upload
one or more PDF scripts (a full slate if you have several) and click **Generate slate
coverage**. Each script runs its own 16-agent pipeline (plus the slate-ranking agent at
the end); in real tests, an individual script takes ~25 seconds regardless of length, and
a slate of 3 scripts across distinct genres took ~81 seconds total (see [Project
status](#project-status)).

## Project structure

```
ScriptGuard AI/
├── app.py                              # Streamlit interface (slate + individual coverage)
├── requirements.txt
├── .env.example
├── scriptguard/
│   ├── schemas.py                      # Pydantic: ScriptAnalysis, MarketResearch, PersonaOpinion,
│   │                                   #   QACritique, CoverageReport, SlateRanking
│   ├── pdf_utils.py                    # PDF text extraction
│   ├── pipeline.py                     # Agent composition (Sequential+Parallel+Loop) + Runner
│   └── agents/
│       ├── script_analyst.py           # Narrative analysis
│       ├── market_research.py          # ParallelAgent: comparables + trends
│       ├── greenlight_committee.py     # 2x ParallelAgent (4 personas, 2 rounds) + moderator
│       ├── qa_critic.py                # LoopAgent: critic + exit check + reviser
│       └── slate_ranking.py            # Portfolio prioritization
```

## Stack

- [Google ADK](https://github.com/google/adk-python) — multi-agent orchestration
  (`SequentialAgent`, `ParallelAgent`, `LoopAgent`)
- [google-genai](https://github.com/googleapis/python-genai) — Gemini client
- [Parallel Search API](https://docs.parallel.ai) (`parallel-web`) — real-time market research
- Pydantic — shared state schemas between agents
- pypdf — PDF script text extraction
- Streamlit — web interface

## License

MIT — see [LICENSE](LICENSE).
