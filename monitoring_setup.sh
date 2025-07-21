#!/bin/bash

# Monitoring and Auto-restart Setup для Oracle Cloud
# Цей скрипт налаштує моніторинг ресурсів та автоматичний перезапуск

echo "=== Налаштування моніторингу для Oracle Cloud ==="

# 1. Створення swap файлу (важливо для 24GB RAM)
echo "Створення swap файлу..."
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 2. Налаштування vm параметрів для кращої роботи з пам'яттю
echo "Налаштування VM параметрів..."
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
echo 'vm.vfs_cache_pressure=50' | sudo tee -a /etc/sysctl.conf
echo 'vm.overcommit_memory=1' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# 3. Створення директорії для логів моніторингу
mkdir -p ~/monitoring_logs

# 4. Скрипт моніторингу ресурсів
cat > ~/resource_monitor.sh << 'EOF'
#!/bin/bash

LOG_FILE=~/monitoring_logs/resource_monitor.log
ALERT_THRESHOLD_MEM=85  # Відсоток використання пам'яті
ALERT_THRESHOLD_CPU=90  # Відсоток використання CPU

# Функція логування
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> $LOG_FILE
}

# Перевірка використання пам'яті
check_memory() {
    MEM_USAGE=$(free | grep Mem | awk '{printf("%.0f", $3/$2 * 100.0)}')
    if [ $MEM_USAGE -gt $ALERT_THRESHOLD_MEM ]; then
        log_message "ALERT: High memory usage: ${MEM_USAGE}%"
        # Вбиваємо playwright процеси якщо вони є
        pkill -f playwright
        pkill -f chromium
        log_message "Killed playwright/chromium processes"
    fi
    log_message "Memory usage: ${MEM_USAGE}%"
}

# Перевірка використання CPU
check_cpu() {
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1}')
    CPU_USAGE=${CPU_USAGE%.*}  # Видаляємо десяткову частину
    if [ $CPU_USAGE -gt $ALERT_THRESHOLD_CPU ]; then
        log_message "ALERT: High CPU usage: ${CPU_USAGE}%"
    fi
    log_message "CPU usage: ${CPU_USAGE}%"
}

# Перевірка процесів Python
check_python_processes() {
    PYTHON_COUNT=$(ps aux | grep python | grep -v grep | wc -l)
    log_message "Python processes count: $PYTHON_COUNT"
    
    # Якщо забагато процесів python
    if [ $PYTHON_COUNT -gt 10 ]; then
        log_message "ALERT: Too many Python processes: $PYTHON_COUNT"
    fi
}

# Основна перевірка
log_message "=== Resource Check ==="
check_memory
check_cpu
check_python_processes

# Перевірка дискового простору
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
log_message "Disk usage: ${DISK_USAGE}%"
EOF

chmod +x ~/resource_monitor.sh

# 5. Скрипт автоматичного перезапуску FastAPI
cat > ~/restart_api.sh << 'EOF'
#!/bin/bash

LOG_FILE=~/monitoring_logs/restart_api.log
API_PORT=8000

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> $LOG_FILE
}

# Перевірка чи працює API
check_api() {
    if curl -f http://localhost:$API_PORT/health &>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Перезапуск API
restart_api() {
    log_message "Restarting API..."
    
    # Вбиваємо старі процеси
    pkill -f "uvicorn.*main:app"
    pkill -f "python.*main.py"
    sleep 5
    
    # Очищаємо playwright процеси
    pkill -f playwright
    pkill -f chromium
    
    cd ~/KovchegBackend
    # Запускаємо API в фоні
    nohup python -m uvicorn api.main:app --host 0.0.0.0 --port $API_PORT > ~/monitoring_logs/api.log 2>&1 &
    
    sleep 10
    
    if check_api; then
        log_message "API restarted successfully"
    else
        log_message "ERROR: Failed to restart API"
    fi
}

# Основна логіка
if ! check_api; then
    log_message "API is down, restarting..."
    restart_api
else
    log_message "API is running normally"
fi
EOF

chmod +x ~/restart_api.sh

# 6. Налаштування systemd автозапуску
echo "Налаштування автозапуску..."
sudo cp ~/KovchegBackend/kovcheg-autostart.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kovcheg-autostart.service

# 7. Налаштування cron для автоматичного моніторингу
echo "Налаштування cron завдань..."
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/resource_monitor.sh") | crontab -
(crontab -l 2>/dev/null; echo "*/2 * * * * ~/restart_api.sh") | crontab -
(crontab -l 2>/dev/null; echo "0 2 * * * sudo systemctl restart cron") | crontab -

echo "=== Налаштування завершено ==="
echo "Створені файли:"
echo "- ~/resource_monitor.sh - моніторинг ресурсів"
echo "- ~/restart_api.sh - автоматичний перезапуск API"
echo "- ~/monitoring_logs/ - директорія для логів"
echo "- /etc/systemd/system/kovcheg-autostart.service - автозапуск"
echo ""
echo "Автоматичні завдання:"
echo "- ✅ Автозапуск після перезавантаження сервера"
echo "- ✅ Моніторинг ресурсів кожні 5 хвилин"
echo "- ✅ Перевірка API кожні 2 хвилини"
echo "- ✅ Перезапуск cron щодня о 2:00"
echo ""
echo "Тепер можна запускати: ./start_production.sh" 