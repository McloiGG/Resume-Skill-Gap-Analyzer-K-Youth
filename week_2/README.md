# Week 2: AI Component Setup

## Project Overview

This folder contains the Week 2 AI setup work for the Resume Skill Gap Analyzer.
The current scope is the model prompting layer used by later tagging and skill-gap
steps. It supports Gemini models through the Google GenAI SDK and local models
through Ollama.

`find_skill_gaps.py` is intentionally left as a blank placeholder for now because
the current setup task does not implement Day 3-4 skill-gap logic yet.

## Setup Instructions

### Prerequisites

- Python `3.14.*`
- `uv`
- Ollama
- A Google AI Studio API key for Gemini models

This project has `.python-version` set to `3.14`, so run commands through `uv`
from this `week_2` directory.

### Dependencies

You said packages will be added and pinned manually with `uv`. For this setup
scope, add:

```powershell
uv add google-genai==<exact-version>
uv add ruff==0.15.17
```

No Ollama Python package is required. The local model path uses Ollama's HTTP API
at `127.0.0.1:11434`.

### Environment Variables

Set one of these variables before calling Gemini models:

```powershell
$env:GEMINI_API_KEY = "your-api-key"
```

or:

```powershell
$env:GOOGLE_API_KEY = "your-api-key"
```

Do not commit API keys, `.env` files, local databases, virtual environments, or
generated data.

### Ollama Setup

Confirm Ollama is running:

```powershell
curl.exe 127.0.0.1:11434
ollama -v
ollama ls
```

The required local models are:

- `llama3.1`
- `phi3`
- `deepseek-r1:1.5b`

Bonus model installed locally:

- `phi4-mini:latest`

The Notion brief specifies Ollama `0.21.*`. This project uses the stable Ollama
HTTP API, but verify your local version before final submission if strict version
checking is applied.

## Usage

Run commands from this `week_2` directory.

Prompt a local Ollama model:

```powershell
uv run prompt_model.py llama3.1 "tell me one Malaysian joke"
uv run prompt_model.py phi3 "say hello"
uv run prompt_model.py deepseek-r1 "say hello"
uv run prompt_model.py phi4-mini "say hello"
uv run prompt_model.py qwen3.5 "say hello"
```

Prompt a Gemini model after setting an API key:

```powershell
uv run prompt_model.py gemini-2.5-flash "say hello"
uv run prompt_model.py gemini-2.5-flash-lite "say hello"
uv run prompt_model.py gemini-3-flash-preview "say hello"
```

The output format is:

```text
--- RESPONSE ---

<model response or graceful error>
```

View the saved Gemini rate limits:

```powershell
cat rate_limits.txt
```

## API / Function Reference

### `prompt_model(model: str, prompt: str) -> str`

Prompts the selected model and returns text.

Inputs:

- `model`: one of the Gemini model IDs or a local Ollama model name.
- `prompt`: the text prompt to send to the model.

Output:

- A text response from the model.
- A graceful error string if the dependency, API key, local server, model, or
  remote provider fails.

Gemini model IDs are routed to `google-genai`. Other model names are routed to
Ollama's `/api/generate` endpoint with streaming disabled.

## Data / Assumptions

- `rate_limits.txt` stores Gemini rate limits in the required format:
  `<model> <RPM> <TPM> <RPD>`.
- The API key is provided through the environment and is never stored in code.
- Ollama is expected to run locally on `127.0.0.1:11434`.
- `OLLAMA_HOST` may be set to override the default Ollama host.
- Model aliases such as `phi4-mini` may resolve to installed tagged models such
  as `phi4-mini:latest`.

## Testing

Compile the script:

```powershell
uv run python -m py_compile prompt_model.py
```

Run Ruff:

```powershell
uv run ruff check prompt_model.py
```

Run local model smoke tests after confirming `ollama ls` shows the models:

```powershell
uv run prompt_model.py llama3.1 "tell me one Malaysian joke"
uv run prompt_model.py phi4-mini "say hello"
uv run prompt_model.py qwen3.5 "say hello"
```

Run a Gemini smoke test after setting an API key:

```powershell
uv run prompt_model.py gemini-2.5-flash "say hello"
```

## Limitations

- Gemini calls require `google-genai` and a valid API key.
- Ollama calls require the local server to be running and the requested model to
  be installed.
- Responses are not streamed, and Ollama thinking mode is disabled for faster one-shot project setup calls.
- This setup does not implement tagging or skill-gap detection yet.
- Local model quality and speed depend on available RAM, CPU, GPU, and model
  size.

## Architecture Reflection

The setup keeps provider-specific logic behind one `prompt_model` function so
later Week 2 code can call a single interface regardless of model provider.
Gemini is used for cloud-hosted models, while Ollama is called through its HTTP
API to avoid an extra Python dependency for local models.

The main trade-off is simplicity over advanced provider abstraction. The current
function handles setup, dispatch, and graceful errors without introducing a
larger client layer. If this project expands, the next improvement would be to
split Gemini and Ollama clients into separate modules and add tests with mocked
HTTP/API responses.
