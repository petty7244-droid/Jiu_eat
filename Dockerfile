FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PORT=8000

WORKDIR /app

# pyodbc is retained for local MSSQL compatibility; this image uses PostgreSQL.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libodbc2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser backend ./backend
COPY --chown=appuser:appuser frontend ./frontend
USER appuser

EXPOSE 8000

# Tokens are process-local: keep one worker and one Northflank instance.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
