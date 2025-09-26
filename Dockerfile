FROM python:3.13-slim

ENV UV_SYSTEM_PYTHON=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HERETIX_CONCURRENCY=6

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

CMD ["/app/.venv/bin/python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
