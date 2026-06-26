FROM python:3.14-bookworm

WORKDIR /app

ENV UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.11.20 /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen

COPY src/ ./src/

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8001", "app:app"]
