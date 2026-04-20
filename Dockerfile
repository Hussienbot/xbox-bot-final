FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# تثبيت Playwright ومتصفح WebKit (الأخف)
RUN pip install playwright && \
    playwright install webkit && \
    playwright install-deps

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers

CMD ["python", "app.py"]
