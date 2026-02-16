FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg2 and sentence-transformers
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
# Install CPU-only torch to avoid large CUDA dependencies
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.2.2+cpu \
    && pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

COPY . /app/

# Default command (can be overridden in docker-compose)
CMD ["python", "main.py"]
