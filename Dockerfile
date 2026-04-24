FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy both backend and frontend so that backend/main.py can serve frontend/index.html
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Ensure required directory permissions
RUN chmod -R 755 /app

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).status==200 else 1)"

# Cloud Run injects the PORT environment variable. We default to 8080 locally.
CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
