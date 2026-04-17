FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpoppler-cpp-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p downloads results static

# Shell form ensures $PORT expands correctly
CMD gunicorn --bind 0.0.0.0:${PORT:-8080} --timeout 120 --workers 1 --access-logfile - --error-logfile - server:app
