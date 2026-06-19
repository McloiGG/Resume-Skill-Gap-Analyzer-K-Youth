# Week 2: Resume Skill Gap Analyzer AI Component

## Project Overview

This repository contains the Week 2 AI component of the Resume Skill Gap Analyzer. It adds three workflows on top of the job data produced earlier:

1. Prompt Gemini or local Ollama models through one Python function.
2. Tag job descriptions with normalized technical skills using Gemini.
3. Compare a resume with tagged job skills and return deterministic skill gaps and demand statistics.

SQLite access for the tagging and skill-gap workflows is mediated through a FastMCP server. The application scripts call the generic `query_db` MCP tool, which executes SQL loaded from the `queries/` directory.

The tagging workflow uses Gemini because model extraction is useful for converting free-form job descriptions into technical-skill labels. The final skill-gap list is intentionally determined by Python normalization and boundary-aware regular expressions. Gemini validation and its cache can affect token, time, and validation metrics, but they cannot change the returned gaps or demand statistics.

## Setup Instructions

### Prerequisites

- Python `3.14`
- [`uv`](https://docs.astral.sh/uv/) for dependency and environment management
- A Gemini API key from Google AI Studio
- Ollama for optional local model experiments in `prompt_model.py`

### Operating System Compatibility

The Week 2 implementation is cross-platform by design and can run on Windows, macOS, and Linux. It uses `pathlib` for filesystem paths, Python's standard SQLite library inside the MCP server, FastMCP standard-input/output transport, and HTTP APIs for Gemini and Ollama. It does not depend on Windows path separators or Windows-only Python APIs.

The project was developed primarily on Windows. On macOS and Linux, install the same prerequisites and use the shell-specific environment-variable and file-removal commands shown below. Ollama availability and hardware performance vary by operating system and machine.

### Install Dependencies

From the repository root:

```powershell
cd week_2
uv sync
```

The Week 2 dependencies declared in `pyproject.toml` are:

- `google-genai==2.8.0`: Gemini API client
- `fastmcp==3.4.2`: MCP client and SQLite server
- `pydantic==2.13.4`: structured result and response validation
- `ruff==0.15.*`: linting and static checks

### Configure Gemini

Set either `GEMINI_API_KEY` or `GOOGLE_API_KEY` in the current shell.

Windows PowerShell:

```powershell
$env:GEMINI_API_KEY = "your-api-key"
```

or:

```powershell
$env:GOOGLE_API_KEY = "your-api-key"
```

macOS/Linux with Bash or Zsh:

```bash
export GEMINI_API_KEY="your-api-key"
```

or:

```bash
export GOOGLE_API_KEY="your-api-key"
```

These commands configure only the current shell session. Do not commit API keys or `.env` files.

The default model used by both `tag_data.py` and `find-skill-gaps.py` is `gemini-3.1-flash-lite`. Its configured rate limits are read from `rate_limits.txt` rather than being hard-coded into the workflow.

### Configure Ollama

Ollama is only required for local-model calls through `prompt_model.py`. Confirm that the service and models are available:

```powershell
ollama --version
ollama ls
```

Example models used during development include:

- `llama3.1`
- `phi3`
- `deepseek-r1:1.5b`
- `phi4-mini`
- `qwen3.5:4b`

No Ollama Python package is required. The script calls the Ollama HTTP API at `http://127.0.0.1:11434` by default. Override it when necessary:

Windows PowerShell:

```powershell
$env:OLLAMA_HOST = "http://127.0.0.1:11434"
```

macOS/Linux:

```bash
export OLLAMA_HOST="http://127.0.0.1:11434"
```

## Usage

Run all commands from `week_2` after completing the setup.

### Prompt a Model

Gemini example:

```powershell
uv run prompt_model.py gemini-3.1-flash-lite "Say hello in one sentence"
```

Ollama examples:

```powershell
uv run prompt_model.py llama3.1 "How many letters are in strawberry?"
uv run prompt_model.py qwen3.5 "Say hello"
uv run prompt_model.py phi4-mini "Say hello"
```

Expected output:

```text
--- RESPONSE ---

<model response or graceful error message>
```

### Tag Job Data

The supplied database is `data/jobs_d1.db`. Run:

```powershell
uv run tag_data.py
```

The script processes only rows whose `tech_stack` is null or blank. Each update is logged:

```text
Analyzed Job 1: Python, SQL, Docker
```

The final summary includes updated rows, duplicate removal, direct-match quality, prompt-token estimates, planned call reduction, actual Gemini tokens, and elapsed time. Running the script again after all rows are tagged produces:

```text
No data to tag
Total tokens used: 0, took <time>ms
```

### Find Resume Skill Gaps

The default input is `data/resume_d3.txt`. If that file is absent, the CLI falls back to `data/resume.txt`.

```powershell
uv run find_skill_gaps.py
```

The first output line contains the sorted lowercase gaps, elapsed seconds, and tokens used by optional Gemini validation. Later sections contain demand statistics, optimization metrics, cache hits, jailbreak detection, truncation state, and errors.

The public function accepts explicit paths and does not apply the CLI fallback:

```python
from find_skill_gaps import find_skill_gaps

result = find_skill_gaps("data/resume_d3.txt", "data/jobs_d1.db")
print(result.gaps)
```

## API / Function Reference

### `prompt_model(model: str, prompt: str) -> str`

Prompts a supported model and returns text.

- `model`: a Gemini model ID or Ollama model name
- `prompt`: non-empty prompt text
- Returns: model response text or a provider-specific error string

Known Gemini model IDs are routed through `google-genai`. Other names are sent to Ollama's `/api/generate` endpoint with streaming and thinking disabled.

### `tag_data(db_url: str)`

Populates missing `jobs.tech_stack` values using Gemini batches.

- `db_url`: path to a SQLite database containing the `jobs` table
- Returns: `(tokens, time_ms)`
- Side effect: updates missing `tech_stack` values through FastMCP

The default CLI calls:

```python
tag_data("data/jobs_d1.db")
```

The tagger validates Gemini JSON against source IDs, normalizes skills, removes duplicates and soft skills, retries invalid batches, falls back to deterministic description patterns, and finally stores `Not specified` if no technical skill can be found.

### `find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult`

Reads a resume and tagged jobs, then returns deterministic skill gaps.

- `input_file_path`: exact path to the extracted resume text
- `db_url`: exact path to the tagged SQLite database
- Returns: `SkillGapResult`

Important result fields include:

- `gaps`: sorted lowercase skills required by jobs but not matched in the resume
- `tokens` and `time`: optional Gemini token use and elapsed seconds
- `demand_by_gap`: number of jobs requiring each gap
- `demand_percentage_by_gap`: job-demand percentage for each gap
- `top_demand_gaps` and `demand_difference`: practical demand summary
- `baseline_tokens` and `optimized_tokens`: estimated prompt sizes
- `planned_calls_without_batching` and `planned_calls_with_batching`: batching evidence
- `cache_hits`: validated Gemini batches reused from `.skill_gap_cache/`
- `jailbreak_detected`, `jailbreak_matches`, and `input_truncated`: input-safety metadata
- `error`: graceful validation or environment error information

The final gaps and demand statistics are computed entirely from deterministic Python matching. Clearing `.skill_gap_cache/`, changing Gemini output, or losing Gemini access cannot change those fields for identical resume and database inputs.

### `query_db(sql_query, parameters=None)`

`db_server.py` exposes a generic FastMCP tool that executes parameterized SQLite statements.

Application scripts do not import `sqlite3` directly. They start a FastMCP client over standard input/output, load SQL from `queries/`, and call `query_db`. The database path is passed to the MCP server through `TAG_DATA_DB_PATH`.

## Data / Assumptions

### Database

`data/jobs_d1.db` contains the following logical schema:

```sql
CREATE TABLE jobs (
    source_id TEXT PRIMARY KEY,
    job_title TEXT NOT NULL,
    company TEXT NOT NULL,
    description TEXT NOT NULL,
    tech_stack TEXT
);
```

`tech_stack` stores normalized comma-separated technical skills. Tagging targets only null or blank values.

### Resume Inputs

- Default: `data/resume_d3.txt`
- CLI fallback: `data/resume.txt`
- Jailbreak test fixture: `data/jailbreak_resume_test.txt`

Resume text is treated as untrusted data. The skill-gap workflow:

- removes control characters
- limits input to 100,000 characters
- ignores the certifications section
- detects and removes common prompt-injection lines
- uses boundary-aware regular expressions for direct matches

### Skill Normalization

Job skills are lowercased, deduplicated, and filtered for obvious soft skills and `Not specified`.

Slash-separated skills are split, except:

- `A/B testing`
- `CI/CD`

`C/C++` is handled explicitly. If the resume contains `C/C++`, the final gaps cannot contain `c`, `c++`, or `c/c++`.

The following aliases are equivalent for resume matching:

- `power bi` and `powerbi`
- `data studio` and `datastudio`
- `node.js` and `nodejs`

The database's normalized spelling is preserved in the returned gaps.

### Data Flow

```text
Job descriptions
    -> Gemini tagging
    -> MCP query_db
    -> jobs.tech_stack

Resume text + tagged skills
    -> sanitization and normalization
    -> deterministic boundary-aware matching
    -> sorted gaps and demand statistics
    -> optional Gemini validation and cache metrics
```

The Gemini validation prompt receives candidate skill arrays, not the raw resume or full database rows. MCP tools are not exposed directly to Gemini.

## Testing

### Static Checks

From `week_2`:

```powershell
uv run ruff check prompt_model.py tag_data.py find_skill_gaps.py db_server.py
uv run python -m py_compile prompt_model.py tag_data.py find_skill_gaps.py db_server.py
```

### Model Prompting

```powershell
uv run prompt_model.py llama3.1 "Say hello"
uv run prompt_model.py gemini-3.1-flash-lite "Say hello"
```

Confirm Ollama is running before the local test and set a Gemini API key before the Gemini test.

### Tagging

Use a fresh copy of `data/jobs_d1.db` when testing database mutation:

```powershell
uv run tag_data.py
uv run tag_data.py
```

Verify that the first run logs each updated job and the second run reports `No data to tag`.

### Skill-Gap Determinism

Run twice:

```powershell
uv run find_skill_gaps.py
uv run find_skill_gaps.py
```

For stronger cache-independent verification, run once, delete the validation cache, and run again.

Windows PowerShell:

```powershell
uv run find_skill_gaps.py
Remove-Item -Recurse -Force .skill_gap_cache
uv run find_skill_gaps.py
```

macOS/Linux:

```bash
uv run find_skill_gaps.py
rm -rf .skill_gap_cache
uv run find_skill_gaps.py
```

The following fields must be identical for the same resume and database:

- `gaps`
- `demand_by_gap`
- `demand_percentage_by_gap`
- `top_demand_gaps`
- `demand_difference`

Token, time, cache-hit, and validation-error fields may differ.

### Input Safety

Temporarily call the public function with the supplied malicious fixture:

```powershell
uv run python -c "from find_skill_gaps import find_skill_gaps; print(find_skill_gaps('data/jailbreak_resume_test.txt', 'data/jobs_d1.db'))"
```

Expected behavior:

- no stack trace
- `jailbreak_detected=True`
- detected patterns listed in `jailbreak_matches`
- malicious instructions do not override the result schema or candidate matching

Additional validation covered invalid JSON, empty Gemini output, mismatched source IDs, extra skills, missing files, invalid databases, malformed cache entries, API failures, and missing or malformed rate limits.

## Bonus Features and Optimization Evidence

### Token Counting

Actual Gemini calls use `usage_metadata.total_token_count` when available. The fallback estimate is four tokens per whitespace-separated word and includes both prompt and response text.

### Prompt Optimization

Baseline and optimized prompt estimates use the same batches so prompt reduction is measured separately from batching. The optimized prompt uses compact JSON candidate arrays and shorter instructions.

These values are estimates, not guaranteed billing-token counts. They exclude retries unless a real Gemini response reports those tokens in `tokens`.

### Batching and Time Optimization

Batch size and retry delay are derived from `rate_limits.txt`:

```text
retry delay = ceil(60 / requests per minute)
minimum batch size = ceil(total items / requests per day)
selected batch size = max(minimum batch size, reliability floor 3)
```

For seven jobs and the configured `gemini-3.1-flash-lite` quota:

```text
retry delay = ceil(60 / 15) = 4 seconds
minimum batch size = ceil(7 / 500) = 1
selected batch size = max(1, 3) = 3
planned calls = 7 -> 3
```

Retries can make actual request counts higher than the planned three calls.

### Other Bonuses

- Gemini-only tagging and optional skill validation
- FastMCP-mediated SQLite access
- token and elapsed-time reporting
- tagging quality metrics
- practical gap-demand statistics
- prompt-injection detection and input sanitization
- validated Gemini response cache for reduced repeat calls
- additional local-model experimentation through Ollama

## Limitations

- Tagging quality depends on Gemini output and the source job descriptions.
- The deterministic tagging fallback uses a limited set of regular-expression patterns and may store `Not specified` for vague descriptions.
- Skill matching is exact and alias-driven; semantically equivalent skills outside the configured aliases may be treated as different.
- Prompt-token comparison values are heuristic estimates and should not be presented as exact provider billing values.
- Gemini validation is skipped when its API key or rate-limit configuration is unavailable. Deterministic gap results still work.
- `.skill_gap_cache/` improves repeat validation speed but is not the source of deterministic gap results.
- The generic MCP server can execute both read and write SQL supplied by application code. A production implementation should expose narrower read-only and update-specific tools.
- Local Ollama performance depends on model size, RAM, CPU, GPU, and whether the service is already loaded.
- Chat history is not retained. Every model call is an independent request.
- The current scripts prioritize assignment clarity over a larger package structure and comprehensive automated test suite.

## Architecture Reflection

### Design Choices

The system separates four responsibilities:

1. `prompt_model.py` handles provider routing and graceful model errors.
2. `tag_data.py` converts unstructured descriptions into technical-skill labels.
3. `find_skill_gaps.py` owns deterministic matching, statistics, and input safety.
4. `db_server.py` isolates SQLite access behind FastMCP.

This separation prevents Gemini variability from controlling the final skill-gap result. The LLM is used where language extraction is useful, while Python controls validation, normalization, database mutations, direct-match correctness, sorting, and demand statistics.

### Trade-offs

The design favors reliability and assignment traceability over minimal code size. Strict JSON validation, retries, cache validation, token metrics, input hardening, and graceful failure paths add complexity. In return, malformed AI output cannot silently corrupt database IDs or alter deterministic gap results.

The generic MCP SQL tool demonstrates indirect database access and supports parameterized statements, but it grants more capability than the individual workflows require. It is practical for this project but broader than an ideal production interface.

### Improvements

With more time, the next improvements would be:

- split the large workflow files into parsing, model, metrics, cache, and database modules
- add automated unit and integration tests with mocked Gemini and MCP clients
- introduce a canonical skill taxonomy for aliases such as `LLM`/`LLMs` and `REST API`/`REST APIs`
- expose narrowly scoped read-only and update-specific MCP tools
- record actual request counts and retry timing for stronger performance benchmarking
- add structured logging and machine-readable benchmark reports
- support richer resume formats through a separate document-extraction layer