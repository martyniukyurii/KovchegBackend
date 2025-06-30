#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path

# Додаємо system до Python path
sys.path.append(str(Path(__file__).parent / "system"))

from system.main import PropertyParserManager

# Завантажуємо змінні середовища з .env файлу
def load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
                    
async def test_single_run():
    """Тестуємо один запуск парсера"""
    print("🧪 Тестування OLX парсера...")
    print("=" * 60)
    
    # Завантажуємо змінні середовища
    load_env()
    
    # Перевіряємо OpenAI ключ
    if os.getenv('OPENAI_API_KEY'):
        print("✅ OpenAI ключ завантажено")
    else:
        print("⚠️ OpenAI ключ не знайдено")
    
    # Ініціалізуємо менеджер
    manager = PropertyParserManager()
    
    # Запускаємо один цикл тестування
    await manager.run_single_cycle()
    
    print("\n🏁 Тестування завершено!")

if __name__ == "__main__":
    asyncio.run(test_single_run()) 