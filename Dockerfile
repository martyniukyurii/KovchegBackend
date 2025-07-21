FROM python:3.11-slim

# Встановлення системних залежностей
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    gcc \
    python3-dev \
    build-essential \
    # Залежності для Chromium
    libnss3 \
    libnspr4 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libgtk-3-0 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Встановлення Node.js для Playwright
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs

# Створення користувача (безпека)
RUN useradd -m -u 1000 appuser

# Робоча директорія
WORKDIR /app

# Копіювання залежностей
COPY requirements.txt .

# Встановлення Python залежностей
RUN pip install --no-cache-dir -r requirements.txt

# Копіювання коду
COPY . .

# Зміна власника файлів
RUN chown -R appuser:appuser /app

# Перехід до користувача appuser
USER appuser

# Встановлення Playwright браузерів під appuser (без системних залежностей)
RUN playwright install chromium

# Відкриття порту
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Команда запуску з обмеженням ресурсів
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"] 