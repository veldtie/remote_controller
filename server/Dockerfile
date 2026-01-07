FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements-signaling.txt ./
RUN pip install --no-cache-dir -r requirements-signaling.txt

COPY signaling_server.py ./
COPY healthcheck.py ./

EXPOSE 8000

CMD ["sh", "-c", "uvicorn signaling_server:app --host ${RC_SIGNALING_HOST:-0.0.0.0} --port ${RC_SIGNALING_PORT:-8000}"]
