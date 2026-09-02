# Railway: repo 루트에서 빌드 (Root Directory 미설정 시에도 동작)
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

RUN mkdir -p /app/storage/jobs

ENV JOB_STORAGE_DIR=/app/storage/jobs
ENV OPENAI_MAX_CONCURRENCY=2

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
