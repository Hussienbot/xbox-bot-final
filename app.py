FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget \
    gnupq \
    && rm -rf /var/lib/apt/lists/*

# تثبيت Playwright ومتصفح Firefox
RUN pip install playwright && \
    playwright install firefox && \
    playwright install-deps

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers

CMD ["python", "app.py"]
