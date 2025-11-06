FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install firefox
RUN playwright install-deps firefox

COPY . .

EXPOSE 8080

ENV PLAYWRIGHT_HEADLESS=true
ENV SERVER_HOST=0.0.0.0

CMD uvicorn app:app --host 0.0.0.0 --port $PORT

