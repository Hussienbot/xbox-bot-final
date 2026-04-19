FROM python:3.10-slim

WORKDIR /app

# تثبيت dependencies النظام المطلوبة لـ Playwright
RUN apt-get update && apt-get install -y \
    libx11-xcb-dev \
    libxcomposite-dev \
    libxdamage-dev \
    libxext-dev \
    libxfixes-dev \
    libxrandr-dev \
    libgbm-dev \
    libasound-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تثبيت متصفح Chromium
RUN playwright install chromium
RUN playwright install-deps

COPY . .

CMD ["python", "xbox_bot.py"]
