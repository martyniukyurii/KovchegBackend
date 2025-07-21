FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Додаткові системні залежності
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Додання існуючого користувача pwuser в Docker групу
RUN groupadd -f docker \
    && usermod -aG docker pwuser || true

# Робоча директорія
WORKDIR /app

# Копіювання залежностей
COPY requirements.txt .

# Встановлення Python залежностей
RUN pip install --no-cache-dir -r requirements.txt

# Копіювання коду
COPY . .

# Зміна власника файлів
RUN chown -R pwuser:pwuser /app

# Перехід до користувача pwuser
USER pwuser

# Встановлення Playwright браузерів під pwuser (вже встановлені в базовому образі)
# RUN playwright install chromium firefox

# Відкриття порту
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Команда запуску з обмеженням ресурсів
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"] 