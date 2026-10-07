# Image for the reproducible verification run and the local web app.
# The C003 snapshot is not copied in; mount it read-only at /app/data/c003-products.jsonl.
FROM python:3.12.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY pyproject.toml constraints.txt README.md ./
COPY src ./src
RUN pip install --no-cache-dir -c constraints.txt -e ".[dev]"

COPY scripts ./scripts
COPY tests ./tests
COPY data ./data
RUN chown -R app:app /app

USER app
EXPOSE 8000
CMD ["python", "scripts/reproduce.py", "--output-dir", "/tmp/reproduce"]
