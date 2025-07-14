from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from fastapi import Request, Query, Path, Body
from fastapi import status
import asyncio
import json
import re
from bson import ObjectId
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from api.response import Response
from tools.database import Database


class AIAssistantEndpoints:
    """Ендпойнти для AI помічника агентів."""
    
    def __init__(self):
        self.db = Database()
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            dimensions=1536
        )
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=2000
        )

    async def get_property_client_matches(
        self,
        request: Request,
        property_id: str = Path(..., description="ID нерухомості для аналізу")
    ) -> Dict[str, Any]:
        """
        AI аналіз: топ клієнтів для конкретної нерухомості.
        Аналізує характеристики нерухомості та знаходить найбільш підходящих клієнтів.
        """
        try:
            # Конвертація property_id в ObjectId якщо потрібно
            if isinstance(property_id, str):
                try:
                    property_id = ObjectId(property_id)
                except:
                    pass
            
            # Отримання інформації про нерухомість
            property_data = await self.db.properties.find_one({"_id": property_id})
            if not property_data:
                return Response.error("Нерухомість не знайдено", status_code=404)

            # Отримання всіх активних клієнтів
            clients = await self.db.users.find({
                "user_type": "client",
                "client_status": "active",
                "client_preferences": {"$exists": True}
            })
            
            if not clients:
                return Response.success({
                    "property_id": str(property_id),
                    "property_title": property_data.get("title", ""),
                    "matched_clients": [],
                    "message": "Немає активних клієнтів з налаштованими вподобаннями"
                })

            # Підготовка тексту нерухомості для аналізу
            property_text = self._prepare_property_analysis_text(property_data)
            
            # Аналіз кожного клієнта
            client_matches = []
            for client in clients[:20]:  # Обмежуємо до 20 клієнтів для швидкості
                client_text = self._prepare_client_analysis_text(client)
                
                # AI аналіз відповідності
                match_analysis = await self._analyze_property_client_match(
                    property_text, client_text, property_data, client
                )
                
                if match_analysis["score"] > 0.6:  # Тільки хороші відповідності
                    client_matches.append({
                        "client_id": str(client["_id"]),
                        "client_name": client.get("name", ""),
                        "client_email": client.get("email", ""),
                        "client_phone": client.get("phone", ""),
                        "match_score": match_analysis["score"],
                        "match_reasons": match_analysis["reasons"],
                        "recommended_actions": match_analysis["actions"]
                    })

            # Сортування за рейтингом відповідності
            client_matches.sort(key=lambda x: x["match_score"], reverse=True)
            
            return Response.success({
                "property_id": str(property_id),
                "property_title": property_data.get("title", ""),
                "property_summary": self._get_property_summary(property_data),
                "matched_clients": client_matches[:10],  # Топ 10
                "total_analyzed": len(clients),
                "analysis_timestamp": datetime.utcnow().isoformat()
            })

        except Exception as e:
            return Response.error(
                message=f"Помилка при аналізі клієнтів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_daily_agent_tasks(
        self,
        request: Request,
        agent_id: Optional[str] = Query(None, description="ID агента (якщо не вказано, береться з токена)"),
        date: Optional[str] = Query(None, description="Дата в форматі YYYY-MM-DD (за замовчуванням сьогодні)")
    ) -> Dict[str, Any]:
        """
        Отримання щоденних задач агента (з автоматичним генеруванням якщо потрібно).
        """
        try:
            # Визначення дати
            if date:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
            else:
                target_date = datetime.utcnow().date()

            # Отримання ID агента з токена якщо не вказано
            if not agent_id:
                # TODO: Отримати з JWT токена
                agent_id = "current_agent"  # Заглушка

            # Пошук існуючих задач на цю дату
            existing_tasks = await self.db.agent_daily_tasks.find_one({
                "agent_id": agent_id,
                "date": target_date.isoformat()
            })

            if existing_tasks:
                return Response.success({
                    "agent_id": agent_id,
                    "date": target_date.isoformat(),
                    "tasks": existing_tasks["tasks"],
                    "generation_metadata": existing_tasks.get("generation_metadata", {}),
                    "last_updated": existing_tasks.get("last_updated"),
                    "source": "existing"
                })
            else:
                # Автоматичне генерування задач
                generated_tasks = await self.generate_daily_tasks_for_agent(agent_id, target_date)
                return generated_tasks

        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні завдань: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def generate_daily_tasks_for_agent(
        self, 
        agent_id: str, 
        target_date: datetime.date,
        force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """
        Генерування щоденних задач для агента з збереженням у БД.
        """
        try:
            # Перевірка чи існують задачі на цю дату
            if not force_regenerate:
                existing = await self.db.agent_daily_tasks.find_one({
                    "agent_id": agent_id,
                    "date": target_date.isoformat()
                })
                if existing:
                    return Response.success({
                        "agent_id": agent_id,
                        "date": target_date.isoformat(),
                        "tasks": existing["tasks"],
                        "message": "Задачі вже існують для цієї дати",
                        "source": "existing"
                    })

            # Збір даних для аналізу
            analysis_data = await self._collect_agent_analysis_data(agent_id, target_date)
            
            # AI генерація завдань
            generated_tasks = await self._generate_daily_tasks(analysis_data, target_date)
            
            # Підготовка документа для збереження
            tasks_document = {
                "agent_id": agent_id,
                "date": target_date.isoformat(),
                "tasks": generated_tasks,
                "generation_metadata": {
                    "generated_at": datetime.utcnow(),
                    "generation_method": "ai_auto",
                    "data_snapshot": analysis_data["summary"]
                },
                "last_updated": datetime.utcnow(),
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(days=90)  # 3 місяці
            }

            # Збереження в БД (upsert)
            await self.db.agent_daily_tasks.update_one(
                {"agent_id": agent_id, "date": target_date.isoformat()},
                {"$set": tasks_document},
                upsert=True
            )
            
            return Response.success({
                "agent_id": agent_id,
                "date": target_date.isoformat(),
                "tasks": generated_tasks,
                "generation_metadata": tasks_document["generation_metadata"],
                "analysis_summary": analysis_data["summary"],
                "source": "generated"
            })

        except Exception as e:
            return Response.error(
                message=f"Помилка при генерації завдань: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_daily_tasks(
        self,
        request: Request,
        agent_id: str = Path(..., description="ID агента"),
        date: str = Path(..., description="Дата в форматі YYYY-MM-DD"),
        tasks_update: Dict[str, Any] = Body(..., description="Оновлення задач")
    ) -> Dict[str, Any]:
        """
        Оновлення щоденних задач агента.
        """
        try:
            # Валідація дати
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            
            # Пошук існуючих задач
            existing_tasks = await self.db.agent_daily_tasks.find_one({
                "agent_id": agent_id,
                "date": date
            })
            
            if not existing_tasks:
                return Response.error("Задачі на цю дату не знайдено", status_code=404)

            # Підготовка оновлення
            update_data = {
                "last_updated": datetime.utcnow(),
                "generation_metadata.generation_method": "updated"
            }

            # Оновлення окремих задач
            if "tasks" in tasks_update:
                updated_tasks = existing_tasks["tasks"].copy()
                
                for task_update in tasks_update["tasks"]:
                    task_id = task_update.get("task_id")
                    if task_id:
                        # Знаходження задачі для оновлення
                        for i, task in enumerate(updated_tasks):
                            if task.get("task_id") == task_id:
                                # Оновлення полів задачі
                                for key, value in task_update.items():
                                    if key != "task_id":
                                        updated_tasks[i][key] = value
                                updated_tasks[i]["updated_at"] = datetime.utcnow().isoformat()
                                break
                        else:
                            # Додавання нової задачі
                            new_task = task_update.copy()
                            new_task["created_at"] = datetime.utcnow().isoformat()
                            new_task["status"] = new_task.get("status", "pending")
                            updated_tasks.append(new_task)
                
                update_data["tasks"] = updated_tasks

            # Додавання нових задач
            if "add_tasks" in tasks_update:
                if "tasks" not in update_data:
                    update_data["tasks"] = existing_tasks["tasks"].copy()
                
                for new_task in tasks_update["add_tasks"]:
                    new_task["task_id"] = f"task_{date}_{len(update_data['tasks']) + 1}"
                    new_task["created_at"] = datetime.utcnow().isoformat()
                    new_task["status"] = new_task.get("status", "pending")
                    update_data["tasks"].append(new_task)

            # Видалення задач
            if "remove_task_ids" in tasks_update:
                if "tasks" not in update_data:
                    update_data["tasks"] = existing_tasks["tasks"].copy()
                
                update_data["tasks"] = [
                    task for task in update_data["tasks"] 
                    if task.get("task_id") not in tasks_update["remove_task_ids"]
                ]

            # Збереження оновлень
            await self.db.agent_daily_tasks.update_one(
                {"agent_id": agent_id, "date": date},
                {"$set": update_data}
            )
            
            # Отримання оновленого документа
            updated_document = await self.db.agent_daily_tasks.find_one({
                "agent_id": agent_id,
                "date": date
            })
            
            return Response.success({
                "agent_id": agent_id,
                "date": date,
                "tasks": updated_document["tasks"],
                "last_updated": updated_document["last_updated"],
                "message": "Задачі успішно оновлено"
            })

        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні завдань: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def bulk_generate_daily_tasks(
        self,
        request: Request,
        date: Optional[str] = Query(None, description="Дата для генерації (за замовчуванням сьогодні)"),
        agent_ids: Optional[List[str]] = Query(None, description="Список ID агентів (якщо не вказано - всі активні)")
    ) -> Dict[str, Any]:
        """
        Масове генерування щоденних задач для всіх агентів (для cron job).
        """
        try:
            # Визначення дати
            if date:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
            else:
                target_date = datetime.utcnow().date()

            # Отримання списку агентів
            if agent_ids:
                agents = await self.db.agents.find({"_id": {"$in": [ObjectId(aid) for aid in agent_ids]}})
            else:
                # Всі активні агенти
                agents = await self.db.agents.find({"status": {"$ne": "inactive"}})

            results = {
                "date": target_date.isoformat(),
                "total_agents": len(agents),
                "successful": 0,
                "failed": 0,
                "results": []
            }

            # Генерація задач для кожного агента
            for agent in agents:
                agent_id = str(agent["_id"])
                try:
                    result = await self.generate_daily_tasks_for_agent(
                        agent_id, target_date, force_regenerate=False
                    )
                    
                    if result.get("success"):
                        results["successful"] += 1
                        results["results"].append({
                            "agent_id": agent_id,
                            "status": "success",
                            "tasks_count": len(result["data"]["tasks"])
                        })
                    else:
                        results["failed"] += 1
                        results["results"].append({
                            "agent_id": agent_id,
                            "status": "failed",
                            "error": result.get("message", "Unknown error")
                        })
                        
                except Exception as e:
                    results["failed"] += 1
                    results["results"].append({
                        "agent_id": agent_id,
                        "status": "failed",
                        "error": str(e)
                    })

            return Response.success(results)

        except Exception as e:
            return Response.error(
                message=f"Помилка при масовій генерації завдань: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def cleanup_expired_tasks(self) -> Dict[str, Any]:
        """
        Видалення задач старших за 3 місяці (для cron job).
        """
        try:
            three_months_ago = datetime.utcnow() - timedelta(days=90)
            
            # Видалення застарілих задач
            result = await self.db.agent_daily_tasks.delete_many({
                "expires_at": {"$lt": datetime.utcnow()}
            })
            
            # Також видалення задач старших за 3 місяці (якщо expires_at не встановлено)
            old_result = await self.db.agent_daily_tasks.delete_many({
                "created_at": {"$lt": three_months_ago},
                "expires_at": {"$exists": False}
            })
            
            total_deleted = result.deleted_count + old_result.deleted_count
            
            return Response.success({
                "deleted_count": total_deleted,
                "deleted_expired": result.deleted_count,
                "deleted_old": old_result.deleted_count,
                "cleanup_date": datetime.utcnow().isoformat()
            })

        except Exception as e:
            return Response.error(
                message=f"Помилка при очищенні застарілих завдань: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_daily_tasks(
        self,
        request: Request,
        agent_id: str = Path(..., description="ID агента"),
        date: str = Path(..., description="Дата в форматі YYYY-MM-DD"),
        tasks_update: Dict[str, Any] = Body(..., description="Оновлення задач")
    ) -> Dict[str, Any]:
        """
        Оновлення щоденних задач агента.
        """
        try:
            # Валідація дати
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            
            # Пошук існуючих задач
            existing_tasks = await self.db.agent_daily_tasks.find_one({
                "agent_id": agent_id,
                "date": date
            })
            
            if not existing_tasks:
                return Response.error("Задачі на цю дату не знайдено", status_code=404)

            # Підготовка оновлення
            update_data = {
                "last_updated": datetime.utcnow(),
                "generation_metadata.generation_method": "updated"
            }

            # Оновлення окремих задач
            if "tasks" in tasks_update:
                updated_tasks = existing_tasks["tasks"].copy()
                
                for task_update in tasks_update["tasks"]:
                    task_id = task_update.get("task_id")
                    if task_id:
                        # Знаходження задачі для оновлення
                        for i, task in enumerate(updated_tasks):
                            if task.get("task_id") == task_id:
                                # Оновлення полів задачі
                                for key, value in task_update.items():
                                    if key != "task_id":
                                        updated_tasks[i][key] = value
                                updated_tasks[i]["updated_at"] = datetime.utcnow().isoformat()
                                break
                        else:
                            # Додавання нової задачі
                            new_task = task_update.copy()
                            new_task["created_at"] = datetime.utcnow().isoformat()
                            new_task["status"] = new_task.get("status", "pending")
                            updated_tasks.append(new_task)
                
                update_data["tasks"] = updated_tasks

            # Додавання нових задач
            if "add_tasks" in tasks_update:
                if "tasks" not in update_data:
                    update_data["tasks"] = existing_tasks["tasks"].copy()
                
                for new_task in tasks_update["add_tasks"]:
                    new_task["task_id"] = f"task_{date}_{len(update_data['tasks']) + 1}"
                    new_task["created_at"] = datetime.utcnow().isoformat()
                    new_task["status"] = new_task.get("status", "pending")
                    update_data["tasks"].append(new_task)

            # Видалення задач
            if "remove_task_ids" in tasks_update:
                if "tasks" not in update_data:
                    update_data["tasks"] = existing_tasks["tasks"].copy()
                
                update_data["tasks"] = [
                    task for task in update_data["tasks"] 
                    if task.get("task_id") not in tasks_update["remove_task_ids"]
                ]

            # Збереження оновлень
            await self.db.agent_daily_tasks.update_one(
                {"agent_id": agent_id, "date": date},
                {"$set": update_data}
            )
            
            # Отримання оновленого документа
            updated_document = await self.db.agent_daily_tasks.find_one({
                "agent_id": agent_id,
                "date": date
            })
            
            return Response.success({
                "agent_id": agent_id,
                "date": date,
                "tasks": updated_document["tasks"],
                "last_updated": updated_document["last_updated"],
                "message": "Задачі успішно оновлено"
            })

        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні завдань: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def bulk_generate_daily_tasks(
        self,
        request: Request,
        date: Optional[str] = Query(None, description="Дата для генерації (за замовчуванням сьогодні)"),
        agent_ids: Optional[List[str]] = Query(None, description="Список ID агентів (якщо не вказано - всі активні)")
    ) -> Dict[str, Any]:
        """
        Масове генерування щоденних задач для всіх агентів (для cron job).
        """
        try:
            # Визначення дати
            if date:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
            else:
                target_date = datetime.utcnow().date()

            # Отримання списку агентів
            if agent_ids:
                agents = await self.db.agents.find({"_id": {"$in": [ObjectId(aid) for aid in agent_ids]}})
            else:
                # Всі активні агенти
                agents = await self.db.agents.find({"status": {"$ne": "inactive"}})

            results = {
                "date": target_date.isoformat(),
                "total_agents": len(agents),
                "successful": 0,
                "failed": 0,
                "results": []
            }

            # Генерація задач для кожного агента
            for agent in agents:
                agent_id = str(agent["_id"])
                try:
                    result = await self.generate_daily_tasks_for_agent(
                        agent_id, target_date, force_regenerate=False
                    )
                    
                    if result.get("success"):
                        results["successful"] += 1
                        results["results"].append({
                            "agent_id": agent_id,
                            "status": "success",
                            "tasks_count": len(result["data"]["tasks"])
                        })
                    else:
                        results["failed"] += 1
                        results["results"].append({
                            "agent_id": agent_id,
                            "status": "failed",
                            "error": result.get("message", "Unknown error")
                        })
                        
                except Exception as e:
                    results["failed"] += 1
                    results["results"].append({
                        "agent_id": agent_id,
                        "status": "failed",
                        "error": str(e)
                    })

            return Response.success(results)

        except Exception as e:
            return Response.error(
                message=f"Помилка при масовій генерації завдань: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def cleanup_expired_tasks(self) -> Dict[str, Any]:
        """
        Видалення задач старших за 3 місяці (для cron job).
        """
        try:
            three_months_ago = datetime.utcnow() - timedelta(days=90)
            
            # Видалення застарілих задач
            result = await self.db.agent_daily_tasks.delete_many({
                "expires_at": {"$lt": datetime.utcnow()}
            })
            
            # Також видалення задач старших за 3 місяці (якщо expires_at не встановлено)
            old_result = await self.db.agent_daily_tasks.delete_many({
                "created_at": {"$lt": three_months_ago},
                "expires_at": {"$exists": False}
            })
            
            total_deleted = result.deleted_count + old_result.deleted_count
            
            return Response.success({
                "deleted_count": total_deleted,
                "deleted_expired": result.deleted_count,
                "deleted_old": old_result.deleted_count,
                "cleanup_date": datetime.utcnow().isoformat()
            })

        except Exception as e:
            return Response.error(
                message=f"Помилка при очищенні застарілих завдань: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _prepare_property_analysis_text(self, property_data: Dict) -> str:
        """Підготовка тексту нерухомості для AI аналізу."""
        parts = []
        
        # Основна інформація
        parts.append(f"Тип: {property_data.get('property_type', 'не вказано')}")
        parts.append(f"Операція: {property_data.get('transaction_type', 'не вказано')}")
        
        # Локація
        location = property_data.get("location", {})
        if location.get("city"):
            parts.append(f"Місто: {location['city']}")
        if location.get("district"):
            parts.append(f"Район: {location['district']}")
        
        # Ціна
        price = property_data.get("price", {})
        if price.get("amount"):
            parts.append(f"Ціна: {price['amount']} {price.get('currency', 'грн')}")
        
        # Характеристики
        if property_data.get("area"):
            parts.append(f"Площа: {property_data['area']} кв.м")
        if property_data.get("rooms"):
            parts.append(f"Кімнат: {property_data['rooms']}")
        
        features = property_data.get("features", {})
        if features.get("bedrooms"):
            parts.append(f"Спалень: {features['bedrooms']}")
        if features.get("bathrooms"):
            parts.append(f"Санвузлів: {features['bathrooms']}")
        
        return " | ".join(parts)

    def _prepare_client_analysis_text(self, client_data: Dict) -> str:
        """Підготовка тексту клієнта для AI аналізу."""
        parts = []
        
        # Основна інформація
        parts.append(f"Клієнт: {client_data.get('name', 'не вказано')}")
        
        # Вподобання
        preferences = client_data.get("preferences", {})
        if preferences.get("property_type"):
            parts.append(f"Шукає: {preferences['property_type']}")
        if preferences.get("transaction_type"):
            parts.append(f"Операція: {preferences['transaction_type']}")
        
        # Бюджет
        budget = preferences.get("budget", {})
        if budget.get("min_price") or budget.get("max_price"):
            min_price = budget.get("min_price", 0)
            max_price = budget.get("max_price", "∞")
            parts.append(f"Бюджет: {min_price} - {max_price}")
        
        # Локація
        location_prefs = preferences.get("location", {})
        if location_prefs.get("cities"):
            parts.append(f"Міста: {', '.join(location_prefs['cities'])}")
        if location_prefs.get("districts"):
            parts.append(f"Райони: {', '.join(location_prefs['districts'])}")
        
        # Характеристики
        if preferences.get("min_area") or preferences.get("max_area"):
            min_area = preferences.get("min_area", 0)
            max_area = preferences.get("max_area", "∞")
            parts.append(f"Площа: {min_area} - {max_area} кв.м")
        
        if preferences.get("rooms"):
            parts.append(f"Кімнат: {preferences['rooms']}")
        
        return " | ".join(parts)

    async def _analyze_property_client_match(
        self, 
        property_text: str, 
        client_text: str, 
        property_data: Dict, 
        client_data: Dict
    ) -> Dict[str, Any]:
        """AI аналіз відповідності нерухомості клієнту."""
        
        system_prompt = """Ти - експертний AI помічник для агентів нерухомості. 
        Твоя задача - проаналізувати відповідність конкретної нерухомості вподобанням клієнта.
        
        Оцини відповідність за шкалою від 0 до 1, де:
        - 0.9-1.0: Ідеальна відповідність
        - 0.7-0.9: Дуже хороша відповідність  
        - 0.5-0.7: Хороша відповідність
        - 0.3-0.5: Помірна відповідність
        - 0.0-0.3: Слабка відповідність
        
        Поверни результат у форматі JSON:
        {
            "score": 0.85,
            "reasons": ["причина 1", "причина 2"],
            "actions": ["рекомендована дія 1", "рекомендована дія 2"]
        }"""
        
        user_prompt = f"""
        НЕРУХОМІСТЬ: {property_text}
        
        КЛІЄНТ: {client_text}
        
        Проаналізуй відповідність та дай рекомендації агенту."""
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.llm.invoke(messages)
            )
            
            # Парсинг JSON відповіді
            import json
            import re
            
            # Очищення відповіді від зайвого тексту
            content = response.content.strip()
            
            # Спроба знайти JSON блок
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_content = json_match.group()
                result = json.loads(json_content)
                return result
            else:
                # Якщо JSON не знайдено, повертаємо стандартну відповідь
                return {
                    "score": 0.5,
                    "reasons": ["AI не зміг проаналізувати відповідність"],
                    "actions": ["Проведіть ручний аналіз клієнта"]
                }
            
        except Exception as e:
            return {
                "score": 0.0,
                "reasons": [f"Помилка аналізу: {str(e)}"],
                "actions": ["Зв'яжіться з технічною підтримкою"]
            }

    async def _collect_agent_analysis_data(self, agent_id: str, target_date) -> Dict[str, Any]:
        """Збір даних для аналізу щоденних завдань агента."""
        
        # Нові нерухомості за останні 24 години
        yesterday = datetime.combine(target_date, datetime.min.time()) - timedelta(days=1)
        new_properties = await self.db.properties.find({
            "created_at": {"$gte": yesterday},
            "agent_id": agent_id
        })
        
        # Активні клієнти агента
        active_clients = await self.db.users.find({
            "user_type": "client",
            "assigned_agent_id": agent_id,
            "client_status": "active"
        })
        
        # Заплановані події на сьогодні
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        today_events = await self.db.calendar_events.find({
            "agent_id": agent_id,
            "start_date": {"$gte": start_of_day, "$lte": end_of_day}
        })
        
        # Активні угоди
        active_deals = await self.db.deals.find({
            "agent_id": agent_id,
            "status": {"$in": ["active", "pending", "negotiation"]}
        })
        
        # Клієнти без активності > 7 днів
        week_ago = datetime.utcnow() - timedelta(days=7)
        inactive_clients = await self.db.users.find({
            "user_type": "client",
            "assigned_agent_id": agent_id,
            "last_contact": {"$lt": week_ago},
            "client_status": "active"
        })
        
        return {
            "new_properties": new_properties,
            "active_clients": active_clients,
            "today_events": today_events,
            "active_deals": active_deals,
            "inactive_clients": inactive_clients,
            "summary": {
                "new_properties_count": len(new_properties),
                "active_clients_count": len(active_clients),
                "today_events_count": len(today_events),
                "active_deals_count": len(active_deals),
                "inactive_clients_count": len(inactive_clients)
            }
        }

    async def _generate_daily_tasks(self, analysis_data: Dict, target_date) -> List[Dict[str, Any]]:
        """AI генерація щоденних завдань на основі аналізу даних."""
        
        system_prompt = """Ти - AI помічник для агента нерухомості. 
        На основі аналізу даних згенеруй список пріоритетних завдань на день.
        
        Типи завдань:
        - call_client: Зателефонувати клієнту
        - send_property: Надіслати нерухомість клієнту  
        - schedule_meeting: Запланувати зустріч
        - follow_up: Слідкувати за угодою
        - marketing: Маркетингові активності
        - admin: Адміністративні завдання
        
        Поверни JSON масив завдань:
        [
            {
                "type": "call_client",
                "priority": "high|medium|low", 
                "title": "Заголовок завдання",
                "description": "Детальний опис",
                "estimated_time": 15,
                "client_id": "id_клієнта_якщо_є",
                "property_id": "id_нерухомості_якщо_є"
            }
        ]"""
        
        user_prompt = f"""
        ДАТА: {target_date}
        
        АНАЛІЗ ДАНИХ:
        - Нових нерухомостей: {analysis_data['summary']['new_properties_count']}
        - Активних клієнтів: {analysis_data['summary']['active_clients_count']}
        - Подій на сьогодні: {analysis_data['summary']['today_events_count']}
        - Активних угод: {analysis_data['summary']['active_deals_count']}
        - Клієнтів без контакту > 7 днів: {analysis_data['summary']['inactive_clients_count']}
        
        Згенеруй 5-10 найважливіших завдань на день."""
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.llm.invoke(messages)
            )
            
            # Парсинг JSON відповіді
            import json
            import re
            
            # Очищення відповіді від зайвого тексту
            content = response.content.strip()
            
            # Спроба знайти JSON масив
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                json_content = json_match.group()
                tasks = json.loads(json_content)
            else:
                # Якщо JSON не знайдено, створюємо базові завдання
                tasks = [
                    {
                        "type": "call_client",
                        "priority": "medium",
                        "title": "Зв'язатися з активними клієнтами",
                        "description": f"Зателефонувати {analysis_data['summary']['active_clients_count']} активним клієнтам",
                        "estimated_time": 30
                    },
                    {
                        "type": "admin",
                        "priority": "low",
                        "title": "Оновити базу даних",
                        "description": "Перевірити та оновити інформацію про клієнтів",
                        "estimated_time": 15
                    }
                ]
            
            # Додавання ID та timestamp
            for i, task in enumerate(tasks):
                task["task_id"] = f"task_{target_date}_{i+1}"
                task["created_at"] = datetime.utcnow().isoformat()
                task["status"] = "pending"
            
            return tasks
            
        except Exception as e:
            return [{
                "task_id": "error_task",
                "type": "admin",
                "priority": "high",
                "title": "Помилка генерації завдань",
                "description": f"Сталася помилка: {str(e)}",
                "estimated_time": 5,
                "created_at": datetime.utcnow().isoformat(),
                "status": "pending"
            }]

    def _get_property_summary(self, property_data: Dict) -> str:
        """Короткий опис нерухомості."""
        parts = []
        
        if property_data.get("property_type"):
            parts.append(property_data["property_type"])
        
        if property_data.get("area"):
            parts.append(f"{property_data['area']} кв.м")
            
        if property_data.get("rooms"):
            parts.append(f"{property_data['rooms']} кімн.")
            
        location = property_data.get("location", {})
        if location.get("city"):
            parts.append(location["city"])
            
        price = property_data.get("price", {})
        if price.get("amount"):
            parts.append(f"{price['amount']} {price.get('currency', 'грн')}")
        
        return " • ".join(parts) 