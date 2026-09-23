FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml .
# Fail the build loudly if a dependency cannot be installed (no silent fallback). [dev] adds pytest/ruff.
RUN uv pip install --system -r pyproject.toml --extra dev

COPY . .

EXPOSE 8000
