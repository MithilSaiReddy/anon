FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

ENV HF_HUB_CACHE=/app/models
RUN python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_medium-v2.1', cache_dir='/app/models')" && \
    python -m spacy download en_core_web_lg
ENV HF_HUB_OFFLINE=1

ENV HOST=0.0.0.0
ENV PORT=8000
ENV APP_ENV=prod

COPY . .

RUN mkdir -p /app/temp /app/logs/prod

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
