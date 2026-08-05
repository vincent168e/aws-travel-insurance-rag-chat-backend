FROM python:3.13-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-cache -r pyproject.toml

COPY . .

# Ensure appuser owns the application directory
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.api.index:app", "--host", "0.0.0.0", "--port", "8000"]