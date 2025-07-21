"""
Фонові задачі для API сервера.
Автоматично генерує щоденні задачі для адмінів та очищує застарілі.
"""

import asyncio
from datetime import datetime
from typing import Optional
from tools.logger import Logger


class BackgroundTasksManager:
    """Менеджер фонових задач для API сервера."""
    
    def __init__(self):
        self.logger = Logger()
        self.is_running = False
        self.task = None
        self.ai_assistant = None
        
    async def start(self):
        """Запуск фонових задач."""
        if self.is_running:
            self.logger.warning("⚠️ Фонові задачі вже запущені")
            return
            
        # Імпортуємо тут щоб уникнути циклічних імпортів
        from api.endpoints.ai_assistant import AIAssistantEndpoints
        self.ai_assistant = AIAssistantEndpoints()
        
        self.is_running = True
        self.task = asyncio.create_task(self._background_scheduler())
        self.logger.info("🚀 Фонові задачі запущено")
        
    async def stop(self):
        """Зупинка фонових задач."""
        if not self.is_running:
            return
            
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
                
        self.logger.info("🔴 Фонові задачі зупинено")
        
    async def _background_scheduler(self):
        """Основний цикл планувальника фонових задач."""
        self.logger.info("📅 Планувальник щоденних задач запущено")
        
        last_cleanup_day = None
        last_generation_day = None
        
        while self.is_running:
            try:
                now = datetime.now()
                current_date = now.date()
                current_time = now.time()
                
                # Генерація задач щодня о 6:00 (тільки раз на день)
                if (current_time.hour == 6 and current_time.minute == 0 and 
                    last_generation_day != current_date):
                    
                    await self._generate_daily_tasks()
                    last_generation_day = current_date
                    
                    # Очікуємо 1 хвилину щоб не спрацьовувати двічі
                    await asyncio.sleep(60)
                    continue
                
                # Очищення застарілих задач щодня о 2:00 (тільки раз на день)
                elif (current_time.hour == 2 and current_time.minute == 0 and 
                      last_cleanup_day != current_date):
                    
                    await self._cleanup_expired_tasks()
                    last_cleanup_day = current_date
                    
                    # Очікуємо 1 хвилину щоб не спрацьовувати двічі
                    await asyncio.sleep(60)
                    continue
                
                # Перевірка кожну хвилину
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                self.logger.info("📅 Планувальник зупинено")
                break
            except Exception as e:
                self.logger.error(f"❌ Помилка в планувальнику: {e}")
                await asyncio.sleep(60)
                
    async def _generate_daily_tasks(self):
        """Генерація щоденних задач для всіх адмінів."""
        self.logger.info("🤖 Запуск генерації щоденних задач для всіх адмінів")
        
        try:
            # Викликаємо внутрішній метод напряму (без HTTP Request)
            from api.endpoints.ai_assistant import AIAssistantEndpoints
            from datetime import datetime
            
            target_date = datetime.utcnow().date()
            
            # Отримуємо всіх активних адмінів
            admins = await self.ai_assistant.db.admins.find({"status": {"$ne": "inactive"}, "role": "admin"})
            
            results = {
                "date": target_date.isoformat(),
                "total_admins": len(admins),
                "successful": 0,
                "failed": 0,
                "results": []
            }

            # Генерація задач для кожного адміна
            for admin in admins:
                admin_id = str(admin["_id"])
                try:
                    # Обробляємо JSONResponse якщо потрібно
                    task_result = await self.ai_assistant.generate_daily_tasks_for_admin(
                        admin_id, target_date, force_regenerate=False
                    )
                    
                    # Якщо це JSONResponse, парсимо його
                    if hasattr(task_result, 'body'):
                        import json
                        body = task_result.body.decode() if isinstance(task_result.body, bytes) else str(task_result.body)
                        task_result = json.loads(body)
                    
                    if isinstance(task_result, dict) and task_result.get("status") == "success":
                        results["successful"] += 1
                        results["results"].append({
                            "admin_id": admin_id,
                            "status": "success",
                            "tasks_count": len(task_result["data"]["tasks"]) if "data" in task_result and "tasks" in task_result["data"] else 0
                        })
                    else:
                        results["failed"] += 1
                        results["results"].append({
                            "admin_id": admin_id,
                            "status": "failed",
                            "error": task_result.get("message", "Unknown error") if isinstance(task_result, dict) else str(task_result)
                        })
                except Exception as e:
                    results["failed"] += 1
                    results["results"].append({
                        "admin_id": admin_id,
                        "status": "failed",
                        "error": str(e)
                    })
            
            result = {"status": "success", "data": results}
            
            if isinstance(result, dict) and result.get("status") == "success":
                data = result.get("data", {})
                self.logger.info(
                    f"✅ Успішно згенеровано задачі: {data.get('successful', 0)} успішних, "
                    f"{data.get('failed', 0)} невдалих з {data.get('total_admins', 0)} адмінів"
                )
                
                # Логування деталей для невдалих генерацій
                for failed_result in data.get("results", []):
                    if failed_result.get("status") == "failed":
                        self.logger.warning(
                            f"❌ Не вдалося згенерувати задачі для адміна {failed_result.get('admin_id')}: "
                            f"{failed_result.get('error', 'Unknown error')}"
                        )
            else:
                self.logger.error(f"❌ Помилка при масовій генерації задач: {result.get('message', 'Unknown error') if isinstance(result, dict) else str(result)}")
                
        except Exception as e:
            self.logger.error(f"❌ Критична помилка генерації задач: {e}")
            
    async def _cleanup_expired_tasks(self):
        """Очищення застарілих задач."""
        self.logger.info("🧹 Запуск очищення застарілих задач")
        
        try:
            # Викликаємо внутрішню логіку напряму
            from datetime import timedelta
            
            three_months_ago = datetime.utcnow() - timedelta(days=90)
            
            # Видалення застарілих задач
            expired_result = await self.ai_assistant.db.admin_daily_tasks.delete_many({
                "expires_at": {"$lt": datetime.utcnow()}
            })
            
            # Також видалення задач старших за 3 місяці (якщо expires_at не встановлено)
            old_result = await self.ai_assistant.db.admin_daily_tasks.delete_many({
                "created_at": {"$lt": three_months_ago},
                "expires_at": {"$exists": False}
            })
            
            # Отримуємо кількість видалених записів
            def get_deleted_count(obj):
                if hasattr(obj, "deleted_count"):
                    return obj.deleted_count
                elif isinstance(obj, int):
                    return obj
                return 0
            
            total_deleted = get_deleted_count(expired_result) + get_deleted_count(old_result)
            
            result = {
                "status": "success",
                "data": {
                    "deleted_count": total_deleted,
                    "deleted_expired": get_deleted_count(expired_result),
                    "deleted_old": get_deleted_count(old_result),
                    "cleanup_date": datetime.utcnow().isoformat()
                }
            }
            
            if isinstance(result, dict) and result.get("status") == "success":
                data = result.get("data", {})
                deleted_count = data.get("deleted_count", 0)
                self.logger.info(f"🗑️ Успішно видалено {deleted_count} застарілих задач")
                
                if deleted_count > 0:
                    self.logger.info(
                        f"📊 Деталі очищення: {data.get('deleted_expired', 0)} з expires_at, "
                        f"{data.get('deleted_old', 0)} старих без expires_at"
                    )
            else:
                self.logger.error(f"❌ Помилка при очищенні застарілих задач: {result.get('message', 'Unknown error') if isinstance(result, dict) else str(result)}")
                
        except Exception as e:
            self.logger.error(f"❌ Критична помилка очищення: {e}")

    # Методи для ручного виклику (для тестування)
    async def manual_generate_tasks(self) -> dict:
        """Ручна генерація задач (для тестування)."""
        await self._generate_daily_tasks()
        return {"status": "completed", "message": "Генерація задач завершена"}
        
    async def manual_cleanup_tasks(self) -> dict:
        """Ручне очищення задач (для тестування)."""
        await self._cleanup_expired_tasks()
        return {"status": "completed", "message": "Очищення задач завершено"}


# Глобальний екземпляр менеджера
background_manager = BackgroundTasksManager() 