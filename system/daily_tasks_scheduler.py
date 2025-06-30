#!/usr/bin/env python3
"""
Планувальник щоденних задач для агентів.
Автоматично генерує задачі раз на день та видаляє застарілі записи.
"""

import asyncio
import schedule
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
import sys
import os

# Додавання шляху до проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.endpoints.ai_assistant import AIAssistantEndpoints
from system.parsers.main_parser import MainParser
from tools.logger import get_logger

# Налаштування логування
logger = get_logger(__name__)


class DailyTasksScheduler:
    """Планувальник щоденних задач для агентів."""
    
    def __init__(self):
        self.ai_assistant = AIAssistantEndpoints()
        self.main_parser = MainParser()
        self.is_running = False

    async def generate_daily_tasks_for_all_agents(self) -> Dict[str, Any]:
        """
        Генерування щоденних задач для всіх активних агентів.
        Викликається автоматично кожен день о 6:00 ранку.
        """
        logger.info("Початок генерації щоденних задач для всіх агентів")
        
        try:
            # Створення фейкового request об'єкта для API
            class FakeRequest:
                pass
            
            fake_request = FakeRequest()
            
            # Викликаємо метод масового генерування задач
            result = await self.ai_assistant.bulk_generate_daily_tasks(
                request=fake_request,
                date=None,  # Сьогоднішня дата
                agent_ids=None  # Всі активні агенти
            )
            
            if result.get("success"):
                data = result["data"]
                logger.info(
                    f"Успішно згенеровано задачі: {data['successful']} успішних, "
                    f"{data['failed']} невдалих з {data['total_agents']} агентів"
                )
                
                # Логування деталей для невдалих генерацій
                for failed_result in data.get("results", []):
                    if failed_result.get("status") == "failed":
                        logger.warning(
                            f"Не вдалося згенерувати задачі для агента {failed_result['agent_id']}: "
                            f"{failed_result.get('error', 'Unknown error')}"
                        )
            else:
                logger.error(f"Помилка при масовій генерації задач: {result.get('message')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Критична помилка при генерації щоденних задач: {str(e)}")
            return {"success": False, "error": str(e)}

    async def cleanup_expired_tasks(self) -> Dict[str, Any]:
        """
        Очищення застарілих задач (старіших за 3 місяці).
        Викликається автоматично кожен день о 2:00 ночі.
        """
        logger.info("Початок очищення застарілих задач")
        
        try:
            result = await self.ai_assistant.cleanup_expired_tasks()
            
            if result.get("success"):
                data = result["data"]
                deleted_count = data.get("deleted_count", 0)
                logger.info(f"Успішно видалено {deleted_count} застарілих задач")
                
                if deleted_count > 0:
                    logger.info(
                        f"Деталі очищення: {data.get('deleted_expired', 0)} з expires_at, "
                        f"{data.get('deleted_old', 0)} старих без expires_at"
                    )
            else:
                logger.error(f"Помилка при очищенні застарілих задач: {result.get('message')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Критична помилка при очищенні застарілих задач: {str(e)}")
            return {"success": False, "error": str(e)}

    async def run_parsers_all_sites(self) -> Dict[str, Any]:
        """
        Запуск парсингу всіх сайтів (OLX та M2Bomber).
        Викликається автоматично кожен день о 8:00 ранку.
        """
        logger.info("Початок парсингу всіх сайтів")
        
        try:
            result = await self.main_parser.parse_all_sites()
            
            if result.get('errors'):
                logger.warning(f"Парсинг завершений з помилками: {len(result['errors'])} помилок")
                for error in result['errors']:
                    logger.error(f"Помилка парсингу: {error}")
            else:
                logger.info("Парсинг всіх сайтів завершений успішно")
            
            # Логування результатів
            olx_success = sum(1 for status in result.get('olx_results', {}).values() if status == 'success')
            m2bomber_success = sum(1 for status in result.get('m2bomber_results', {}).values() if status == 'success')
            
            logger.info(f"Результати парсингу: OLX {olx_success} категорій, M2Bomber {m2bomber_success} категорій")
            
            return result
            
        except Exception as e:
            logger.error(f"Критична помилка при парсингу всіх сайтів: {str(e)}")
            return {"success": False, "error": str(e)}

    async def run_parsers_olx_only(self) -> Dict[str, Any]:
        """
        Запуск парсингу тільки OLX.
        Викликається автоматично кожен день о 12:00.
        """
        logger.info("Початок парсингу тільки OLX")
        
        try:
            result = await self.main_parser.parse_olx_only()
            
            if result.get('errors'):
                logger.warning(f"Парсинг OLX завершений з помилками: {len(result['errors'])} помилок")
                for error in result['errors']:
                    logger.error(f"Помилка парсингу OLX: {error}")
            else:
                logger.info("Парсинг OLX завершений успішно")
            
            # Логування результатів
            success_count = sum(1 for status in result.get('results', {}).values() if status == 'success')
            logger.info(f"OLX парсинг: {success_count} категорій успішно")
            
            return result
            
        except Exception as e:
            logger.error(f"Критична помилка при парсингу OLX: {str(e)}")
            return {"success": False, "error": str(e)}

    async def run_parsers_m2bomber_only(self) -> Dict[str, Any]:
        """
        Запуск парсингу тільки M2Bomber.
        Викликається автоматично кожен день о 16:00.
        """
        logger.info("Початок парсингу тільки M2Bomber")
        
        try:
            result = await self.main_parser.parse_m2bomber_only()
            
            if result.get('errors'):
                logger.warning(f"Парсинг M2Bomber завершений з помилками: {len(result['errors'])} помилок")
                for error in result['errors']:
                    logger.error(f"Помилка парсингу M2Bomber: {error}")
            else:
                logger.info("Парсинг M2Bomber завершений успішно")
            
            # Логування результатів
            success_count = sum(1 for status in result.get('results', {}).values() if status == 'success')
            logger.info(f"M2Bomber парсинг: {success_count} категорій успішно")
            
            return result
            
        except Exception as e:
            logger.error(f"Критична помилка при парсингу M2Bomber: {str(e)}")
            return {"success": False, "error": str(e)}

    def run_async_task(self, coro):
        """
        Запуск асинхронної задачі в синхронному контексті schedule.
        """
        def wrapper():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(coro)
                loop.close()
                return result
            except Exception as e:
                logger.error(f"Помилка при виконанні асинхронної задачі: {str(e)}")
                return {"success": False, "error": str(e)}
        
        return wrapper

    def setup_schedule(self):
        """
        Налаштування розкладу виконання задач.
        """
        logger.info("Налаштування розкладу щоденних задач та парсингу")
        
        # Очищення застарілих задач щодня о 2:00 ночі
        schedule.every().day.at("02:00").do(
            self.run_async_task(self.cleanup_expired_tasks)
        )
        
        # Генерація задач щодня о 6:00 ранку
        schedule.every().day.at("06:00").do(
            self.run_async_task(self.generate_daily_tasks_for_all_agents)
        )
        
        # Парсинг всіх сайтів кожні 5 хвилин
        schedule.every(5).minutes.do(
            self.run_async_task(self.run_parsers_all_sites)
        )
        
        logger.info("Розклад налаштовано:")
        logger.info("- Очищення застарілих: щодня о 02:00")
        logger.info("- Генерація задач: щодня о 06:00")
        logger.info("- Парсинг всіх сайтів: кожні 5 хвилин")

    def start_scheduler(self):
        """
        Запуск планувальника.
        """
        if self.is_running:
            logger.warning("Планувальник вже запущений")
            return
        
        self.is_running = True
        self.setup_schedule()
        
        logger.info("Планувальник щоденних задач запущений")
        
        try:
            while self.is_running:
                schedule.run_pending()
                time.sleep(60)  # Перевірка кожну хвилину
        except KeyboardInterrupt:
            logger.info("Отримано сигнал переривання, зупинка планувальника")
            self.stop_scheduler()
        except Exception as e:
            logger.error(f"Критична помилка в планувальнику: {str(e)}")
            self.stop_scheduler()

    def stop_scheduler(self):
        """
        Зупинка планувальника.
        """
        self.is_running = False
        schedule.clear()
        logger.info("Планувальник зупинений")


def main():
    """
    Головна функція для запуску планувальника.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Планувальник щоденних задач для агентів та парсерів")
    parser.add_argument("--mode", choices=["daemon", "generate", "cleanup", "parse-all", "parse-olx", "parse-m2bomber"], 
                       default="daemon", help="Режим роботи")
    parser.add_argument("--date", type=str, help="Дата для генерації (YYYY-MM-DD)")
    parser.add_argument("--categories", nargs='+', help="Категорії для парсингу (prodazh, orenda, commerce, houses)")
    
    args = parser.parse_args()
    
    scheduler = DailyTasksScheduler()
    
    if args.mode == "daemon":
        # Запуск в режимі демона
        logger.info("Запуск планувальника в режимі демона")
        scheduler.start_scheduler()
        
    elif args.mode == "generate":
        # Ручна генерація задач
        logger.info("Ручна генерація задач")
        async def run_generation():
            class FakeRequest:
                pass
            result = await scheduler.ai_assistant.bulk_generate_daily_tasks(
                FakeRequest(), args.date, None
            )
            print(f"Результат: {result}")
        
        asyncio.run(run_generation())
        
    elif args.mode == "cleanup":
        # Ручне очищення
        logger.info("Ручне очищення застарілих задач")
        result = asyncio.run(scheduler.cleanup_expired_tasks())
        print(f"Результат: {result}")
        
    elif args.mode == "parse-all":
        # Ручний запуск парсингу всіх сайтів
        logger.info("Ручний запуск парсингу всіх сайтів")
        async def run_parsing():
            categories = args.categories if args.categories else None
            if categories:
                result = await scheduler.main_parser.parse_all_sites(categories)
            else:
                result = await scheduler.run_parsers_all_sites()
            print(f"Результат парсингу всіх сайтів: {result}")
        
        asyncio.run(run_parsing())
        
    elif args.mode == "parse-olx":
        # Ручний запуск парсингу OLX
        logger.info("Ручний запуск парсингу OLX")
        async def run_olx_parsing():
            categories = args.categories if args.categories else None
            if categories:
                result = await scheduler.main_parser.parse_olx_only(categories)
            else:
                result = await scheduler.run_parsers_olx_only()
            print(f"Результат парсингу OLX: {result}")
        
        asyncio.run(run_olx_parsing())
        
    elif args.mode == "parse-m2bomber":
        # Ручний запуск парсингу M2Bomber
        logger.info("Ручний запуск парсингу M2Bomber")
        async def run_m2bomber_parsing():
            categories = args.categories if args.categories else None
            if categories:
                result = await scheduler.main_parser.parse_m2bomber_only(categories)
            else:
                result = await scheduler.run_parsers_m2bomber_only()
            print(f"Результат парсингу M2Bomber: {result}")
        
        asyncio.run(run_m2bomber_parsing())


if __name__ == "__main__":
    main() 