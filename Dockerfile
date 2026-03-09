FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy both backend and frontend so that backend/main.py can serve frontend/index.html
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Ensure required directory permissions
RUN chmod -R 755 /app

# Cloud Run injects the PORT environment variable. We default to 8080 locally.
CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
