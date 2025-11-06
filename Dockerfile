FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install firefox
RUN playwright install-deps firefox

COPY . .

EXPOSE 8080

ENV PLAYWRIGHT_HEADLESS=true
ENV SERVER_HOST=0.0.0.0
ENV PORT=8080

CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}

