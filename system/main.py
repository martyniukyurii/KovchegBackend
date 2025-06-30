import asyncio
import json
import os
import time
import sys
from datetime import datetime
from pathlib import Path

# Додаємо tools до Python path для логера
sys.path.append(str(Path(__file__).parent.parent / "tools"))
from logger import Logger

from parsers.olx_parser import OLXParser
from parsers.m2bomber_parser import M2BomberParser

class PropertyParserManager:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.links_file = Path(__file__).parent / "links_data.json"  # Використовуємо новий файл в system
        self.results_dir = self.project_root / "parsed_results"
        
        # Ініціалізуємо логер
        self.logger = Logger()
        
        # Створюємо папку для результатів якщо її немає
        self.results_dir.mkdir(exist_ok=True)
        
        self.logger.info(f"Ініціалізовано PropertyParserManager")
        self.logger.info(f"Файл посилань: {self.links_file}")
        self.logger.info(f"Папка результатів: {self.results_dir}")
        
    def load_links_data(self):
        """Завантажуємо дані з файлу посилань"""
        try:
            with open(self.links_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.logger.info(f"Завантажено {len(data)} посилань з файлу")
                return data
        except Exception as e:
            self.logger.error(f"Помилка при завантаженні файлу посилань: {e}")
            return []
            
    def save_results(self, results, parser_name):
        """Зберігаємо результати парсингу"""
        if not results:
            self.logger.warning(f"Немає результатів для збереження для {parser_name}")
            return None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{parser_name}_results_{timestamp}.json"
        filepath = self.results_dir / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Результати збережено в {filepath}")
            self.logger.info(f"Всього оброблено: {len(results)} оголошень")
            return filepath
        except Exception as e:
            self.logger.error(f"Помилка при збереженні результатів: {e}")
            return None
            
    async def run_olx_parser(self):
        """Запускаємо OLX парсер"""
        self.logger.info("=" * 60)
        self.logger.info(f"Запуск OLX парсера - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)
        
        # Завантажуємо посилання
        links_data = self.load_links_data()
        if not links_data:
            self.logger.warning("Немає даних для парсингу")
            return []
            
        # Ініціалізуємо парсер
        parser = OLXParser()
        
        try:
            # Ініціалізуємо браузер
            await parser.init_browser()
            
            # Запускаємо парсинг
            results = await parser.parse_all_olx_urls(links_data)
            
            # Зберігаємо результати
            if results:
                self.save_results(results, "olx")
                self.print_parsing_summary(results)
            else:
                self.logger.warning("Не вдалося отримати жодного результату")
                
            return results
            
        except Exception as e:
            self.logger.error(f"Помилка при роботі OLX парсера: {e}")
            return []
        finally:
            # Закриваємо браузер
            await parser.close_browser()
            
    def print_parsing_summary(self, results):
        """Виводимо короткий звіт про парсинг"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("ЗВІТ ПРО ПАРСИНГ")
        self.logger.info("=" * 60)
        
        total = len(results)
        self.logger.info(f"Всього оброблено оголошень: {total}")
        
        if total == 0:
            return
            
        # Статистика по типах нерухомості
        property_types = {}
        prices = []
        with_phone = 0
        with_location = 0
        
        for result in results:
            # Типи нерухомості
            prop_type = result.get('property_type', 'unknown')
            property_types[prop_type] = property_types.get(prop_type, 0) + 1
            
            # Ціни
            if result.get('price'):
                prices.append(result['price'])
                
            # Статистика телефонів та локацій
            if result.get('phone'):
                with_phone += 1
            if result.get('location'):
                with_location += 1
                
        self.logger.info(f"\nПо типах нерухомості:")
        for prop_type, count in property_types.items():
            self.logger.info(f"  {prop_type}: {count}")
            
        self.logger.info(f"\nСтатистика:")
        self.logger.info(f"  З вказаною ціною: {len(prices)} ({len(prices)/total*100:.1f}%)")
        self.logger.info(f"  З номером телефону: {with_phone} ({with_phone/total*100:.1f}%)")
        self.logger.info(f"  З визначеною локацією: {with_location} ({with_location/total*100:.1f}%)")
        
        if prices:
            avg_price = sum(prices) / len(prices)
            min_price = min(prices)
            max_price = max(prices)
            self.logger.info(f"  Середня ціна: ${avg_price:,.0f}")
            self.logger.info(f"  Мін ціна: ${min_price:,.0f}")
            self.logger.info(f"  Макс ціна: ${max_price:,.0f}")
            
        self.logger.info("=" * 60)
        
    async def run_m2bomber_parser(self):
        """Запускаємо M2Bomber парсер"""
        self.logger.info("=" * 60)
        self.logger.info(f"Запуск M2Bomber парсера - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)
        
        # Завантажуємо посилання
        links_data = self.load_links_data()
        if not links_data:
            self.logger.warning("Немає даних для парсингу")
            return []
            
        # Ініціалізуємо парсер
        parser = M2BomberParser()
        
        try:
            # Запускаємо парсинг
            results = await parser.parse_all_m2bomber_urls(links_data)
            
            # Зберігаємо результати
            if results:
                self.save_results(results, "m2bomber")
                self.print_parsing_summary(results)
            else:
                self.logger.warning("Не вдалося отримати жодного результату")
                
            return results
            
        except Exception as e:
            self.logger.error(f"Помилка при роботі M2Bomber парсера: {e}")
            return []
        finally:
            # Парсер сам закриває браузер
            pass
            
    async def run_single_cycle(self):
        """Виконуємо один цикл парсингу всіх сайтів"""
        start_time = time.time()
        
        # Запускаємо OLX парсер
        olx_results = await self.run_olx_parser()
        
        # Запускаємо M2Bomber парсер
        m2bomber_results = await self.run_m2bomber_parser()
        
        end_time = time.time()
        duration = end_time - start_time
        
        self.logger.info(f"\nЦикл парсингу завершено за {duration:.1f} секунд")
        self.logger.info(f"Наступний запуск через 5 хвилин...")
        
        return {
            'olx_results': olx_results,
            'm2bomber_results': m2bomber_results,
            'duration': duration,
            'timestamp': datetime.now().isoformat()
        }
        
    async def run_continuous(self):
        """Запускаємо парсери кожні 5 хвилин"""
        self.logger.info("Запуск системи парсингу нерухомості")
        self.logger.info("Парсери будуть запускатися кожні 5 хвилин")
        self.logger.info("Для зупинки натисніть Ctrl+C")
        self.logger.info("-" * 60)
        
        cycle_count = 0
        
        try:
            while True:
                cycle_count += 1
                self.logger.info(f"\n🔄 ЦИКЛ #{cycle_count}")
                
                # Запускаємо один цикл парсингу
                await self.run_single_cycle()
                
                # Чекаємо 5 хвилин (300 секунд)
                await asyncio.sleep(300)
                
        except KeyboardInterrupt:
            self.logger.info("\n\n⏹️  Зупинка системи парсингу...")
            self.logger.info("Дякую за використання!")
        except Exception as e:
            self.logger.error(f"\n❌ Критична помилка: {e}")
            self.logger.error("Система зупиняється...")

async def main():
    """Головна функція"""
    # Ініціалізуємо менеджер (логер буде створений в __init__)
    manager = PropertyParserManager()
    
    if not manager.links_file.exists():
        manager.logger.error(f"❌ Файл посилань не знайдено: {manager.links_file}")
        manager.logger.error("Переконайтеся, що файл існує та містить валідний JSON")
        return
        
    # Перевіряємо наявність OpenAI ключа
    if not os.getenv('OPENAI_API_KEY'):
        manager.logger.warning("⚠️  OPENAI_API_KEY не знайдено в environment variables")
        manager.logger.warning("Локацію буде визначено без OpenAI")
        
    manager.logger.info("✅ Ініціалізація завершена успішно")
    
    # Запускаємо систему
    await manager.run_continuous()

if __name__ == "__main__":
    # Встановлюємо event loop policy для Windows якщо потрібно
    if os.name == 'nt':  # Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
    # Запускаємо головну функцію
    asyncio.run(main())
