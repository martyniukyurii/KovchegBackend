#!/bin/bash

echo "=== Запуск KovchegBackend в Production режимі ==="

# Перевірка чи є Docker
if ! command -v docker &> /dev/null; then
    echo "Docker не встановлено. Встановлюємо..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "Docker встановлено. Перезайдіть в систему або виконайте: newgrp docker"
fi

# Перевірка чи є docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose не встановлено. Встановлюємо..."
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Зупинка старих контейнерів
echo "Зупинка старих контейнерів..."
docker-compose down --remove-orphans

# Очищення системи
echo "Очищення Docker системи..."
docker system prune -f
docker volume prune -f

# Створення директорії для логів
mkdir -p monitoring_logs

# Перевірка .env файлу
if [ ! -f ".env" ]; then
    echo "УВАГА: .env файл не знайдено!"
    if [ -f ".env.example" ]; then
        echo "Копіюємо з .env.example..."
        cp .env.example .env
        echo "Відредагуйте .env файл перед запуском!"
    fi
fi

# Збірка та запуск
echo "Збірка контейнерів..."
docker-compose build --no-cache

echo "Запуск сервісів..."
docker-compose up -d

# Перевірка статусу
echo "Перевірка статусу сервісів..."
sleep 10
docker-compose ps

# Показати логи останніх 50 рядків
echo "Останні логи:"
docker-compose logs --tail=50

echo ""
echo "=== Сервіс запущено ==="
echo "API доступне на: http://localhost:8000"
echo "Логи: docker-compose logs -f kovcheg-api"
echo "Зупинка: docker-compose down"
echo ""
echo "Моніторинг ресурсів:"
echo "- docker stats kovcheg-backend"
echo "- tail -f monitoring_logs/resource_monitor.log" 