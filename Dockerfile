FROM python:3.11-slim

# تثبيت dependencies الخاصة بـ Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# تثبيت Playwright ومتصفح Firefox
RUN pip install playwright && \
    playwright install firefox && \
    playwright install-deps

# نسخ ملفات المشروع
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# تعيين متغير البيئة لمسار المتصفحات
ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers

# تشغيل التطبيق
CMD ["python", "app.py"]