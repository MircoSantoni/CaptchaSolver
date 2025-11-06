FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install firefox
RUN playwright install-deps firefox

COPY . .

RUN chmod +x start.sh

EXPOSE 8080

ENV PLAYWRIGHT_HEADLESS=true
ENV SERVER_HOST=0.0.0.0

CMD ./start.sh

