FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml .
RUN uv pip install --system -r pyproject.toml || echo 'Ignoring missing dependencies resolution for now'

COPY . .

EXPOSE 8000