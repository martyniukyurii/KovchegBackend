import asyncio
import json
import signal
import sys
from pathlib import Path
from datetime import datetime, time
from typing import List, Dict
import os
from dotenv import load_dotenv

# Завантажуємо змінні середовища
load_dotenv()

# Додаємо tools до Python path для логера та бази
sys.path.append(str(Path(__file__).parent.parent / "tools"))
from logger import Logger
from database import SyncDatabase

# Імпортуємо парсери та Telegram бота
from parsers.olx_parser import OLXParser
from parsers.m2bomber_parser import M2BomberParser
from telegram_bot import TelegramBot

class PropertyParserManager:
    def __init__(self):
        self.logger = Logger()
        self.db = SyncDatabase()
        self.telegram_bot = TelegramBot()
        self.is_running = True
        
        # Налаштування розкладу (не працювати з 2:00 до 7:00)
        self.quiet_start = time(2, 0)  # 2:00
        self.quiet_end = time(7, 0)    # 7:00
        
        # Завантажуємо дані посилань
        self.links_data = self.load_links_data()
        
        # Обробка сигналів для graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def signal_handler(self, signum, frame):
        """Обробник сигналів для graceful shutdown"""
        self.logger.info(f"🛑 Отримано сигнал {signum}. Завершуємо роботу...")
        self.is_running = False
        
    def load_links_data(self) -> List[Dict]:
        """Завантажуємо дані посилань з JSON файлу"""
        try:
            links_file = Path(__file__).parent / "links_data.json"
            with open(links_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.logger.info(f"📁 Завантажено {len(data)} посилань")
            return data
        except Exception as e:
            self.logger.error(f"❌ Помилка завантаження посилань: {e}")
            return []
    
    def is_quiet_time(self) -> bool:
        """Перевіряємо чи зараз тихий час (2:00-7:00)"""
        current_time = datetime.now().time()
        return self.quiet_start <= current_time <= self.quiet_end
    
    async def run_olx_parser(self) -> Dict:
        """Запуск OLX парсера"""
        self.logger.info("🚀 Запуск OLX парсера...")
        
        try:
            parser = OLXParser()
            await parser.init_browser()
            
            # Фільтруємо OLX посилання
            olx_links = [link for link in self.links_data if link.get('site') == 'OLX']
            
            results = await parser.parse_all_olx_urls(olx_links)
            
            await parser.close_browser()
            
            # Відправляємо в Telegram канали
            for result in results:
                try:
                    await self.telegram_bot.send_to_channel(result)
                    await asyncio.sleep(1)  # Пауза між повідомленнями
                except Exception as e:
                    self.logger.error(f"Помилка відправки в Telegram: {e}")
            
            return {
                'parser': 'OLX',
                'processed': len(results),
                'success': True,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"❌ Помилка OLX парсера: {e}")
            return {
                'parser': 'OLX',
                'processed': 0,
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def run_m2bomber_parser(self) -> Dict:
        """Запуск M2Bomber парсера"""
        self.logger.info("🚀 Запуск M2Bomber парсера...")
        
        try:
            parser = M2BomberParser()
            
            # Фільтруємо M2BOMBER посилання
            m2bomber_links = [link for link in self.links_data if link.get('site') == 'M2BOMBER']
            
            results = await parser.parse_all_m2bomber_urls(m2bomber_links)
            
            # Відправляємо в Telegram канали
            for result in results:
                try:
                    await self.telegram_bot.send_to_channel(result)
                    await asyncio.sleep(1)  # Пауза між повідомленнями
                except Exception as e:
                    self.logger.error(f"Помилка відправки в Telegram: {e}")
            
            return {
                'parser': 'M2BOMBER',
                'processed': len(results),
                'success': True,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"❌ Помилка M2Bomber парсера: {e}")
            return {
                'parser': 'M2BOMBER',
                'processed': 0,
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def run_single_cycle(self) -> Dict:
        """Запуск одного циклу парсингу"""
        cycle_start = datetime.now()
        self.logger.info(f"🔄 Початок циклу парсингу: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Перевіряємо тихий час
        if self.is_quiet_time():
            self.logger.info("😴 Тихий час (2:00-7:00). Пропускаємо цикл.")
            return {
                'cycle_start': cycle_start.isoformat(),
                'skipped': True,
                'reason': 'quiet_time',
                'duration': 0
            }
        
        results = []
        
        # Запускаємо парсери паралельно
        try:
            olx_task = asyncio.create_task(self.run_olx_parser())
            m2bomber_task = asyncio.create_task(self.run_m2bomber_parser())
            
            olx_result, m2bomber_result = await asyncio.gather(olx_task, m2bomber_task)
            
            results = [olx_result, m2bomber_result]
            
        except Exception as e:
            self.logger.error(f"❌ Помилка під час виконання циклу: {e}")
            results = []
        
        cycle_end = datetime.now()
        duration = (cycle_end - cycle_start).total_seconds()
        
        # Статистика
        total_processed = sum(r.get('processed', 0) for r in results)
        successful_parsers = sum(1 for r in results if r.get('success', False))
        
        self.logger.info(f"✅ Цикл завершено за {duration:.1f}с. Оброблено: {total_processed}, успішних парсерів: {successful_parsers}/2")
        
        return {
            'cycle_start': cycle_start.isoformat(),
            'cycle_end': cycle_end.isoformat(),
            'duration': duration,
            'results': results,
            'total_processed': total_processed,
            'successful_parsers': successful_parsers,
            'skipped': False
        }
    
    async def run_continuous(self):
        """Безперервний запуск парсерів кожні 5 хвилин"""
        self.logger.info("🚀 Запуск системи парсингу нерухомості")
        self.logger.info(f"📋 Завантажено {len(self.links_data)} посилань")
        self.logger.info("⏰ Парсери будуть запускатися кожні 5 хвилин")
        self.logger.info("😴 Тихий час: 2:00-7:00 (парсери не працюють)")
        self.logger.info("🛑 Для зупинки натисніть Ctrl+C")
        
        cycle_count = 0
        
        while self.is_running:
            try:
                cycle_count += 1
                self.logger.info(f"📊 Цикл #{cycle_count}")
                
                # Запускаємо один цикл
                cycle_result = await self.run_single_cycle()
                
                # Очікуємо 5 хвилин до наступного циклу
                if self.is_running:
                    self.logger.info("⏳ Очікування 5 хвилин до наступного циклу...")
                    for i in range(300):  # 300 секунд = 5 хвилин
                        if not self.is_running:
                            break
                        await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"❌ Критична помилка в головному циклі: {e}")
                if self.is_running:
                    self.logger.info("⏳ Очікування 30 секунд перед повторною спробою...")
                    await asyncio.sleep(30)
        
        # Закриваємо Telegram бота
        await self.telegram_bot.close()
        self.logger.info("👋 Система парсингу зупинена")

async def main():
    """Головна функція"""
    try:
        manager = PropertyParserManager()
        await manager.run_continuous()
    except KeyboardInterrupt:
        print("\n🛑 Зупинка системи...")
    except Exception as e:
        print(f"❌ Критична помилка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
