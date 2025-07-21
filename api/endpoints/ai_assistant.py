
import warnings
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from fastapi import Request, Query, Path, Body
from fastapi import status
import asyncio

from bson import ObjectId
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage


from api.response import Response
from tools.database import Database
from tools.logger import Logger

# Приховуємо попередження від LangChain
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_openai")


class AIAssistantEndpoints:
    """Ендпойнти для AI помічника адмінів."""
    
    def __init__(self):
        self.db = Database()
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small"
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
        Rule-based AI аналіз: топ клієнтів для конкретної нерухомості (без OpenAI).
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

            # Основні характеристики нерухомості
            location_obj = property_data["location"] if isinstance(property_data.get("location"), dict) else {}
            prop_city = location_obj.get("city", "").lower() if isinstance(location_obj, dict) else None
            if isinstance(property_data.get("price"), dict):
                prop_price = property_data["price"].get("amount")
            elif isinstance(property_data.get("price"), (int, float)):
                prop_price = property_data["price"]
            else:
                prop_price = None
            prop_area = property_data["area"] if isinstance(property_data.get("area"), (int, float)) else None
            prop_rooms = property_data["rooms"] if isinstance(property_data.get("rooms"), (int, float)) else None
            features_obj = property_data["features"] if isinstance(property_data.get("features"), dict) else None

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

            # Rule-based matching
            client_matches = []
            for idx, client in enumerate(clients):
                try:
                    prefs = client.get("client_preferences") if isinstance(client.get("client_preferences"), dict) else client.get("preferences") if isinstance(client.get("preferences"), dict) else {}
                    # Пропускаємо клієнтів без ключових вподобань
                    if not prefs.get("location") or not prefs.get("property_type") or not prefs.get("price_range"):
                        continue
                    # Місто
                    match_city = True  # Якщо немає міст — не фільтруємо
                    location_val = prefs.get("location") if isinstance(prefs, dict) and isinstance(prefs.get("location"), (dict, list)) else {} if isinstance(prefs, dict) else {}
                    if isinstance(location_val, dict):
                        cities = location_val.get("cities", []) if isinstance(location_val.get("cities", []), list) else []
                        if cities:
                            match_city = any(prop_city and prop_city in str(c).lower() for c in cities)
                    elif isinstance(location_val, list) and location_val:
                        match_city = any(prop_city and prop_city in str(c).lower() for c in location_val)
                    # Бюджет
                    match_budget = True  # Якщо немає бюджету — не фільтруємо
                    budget = prefs.get("budget") if isinstance(prefs, dict) and isinstance(prefs.get("budget"), dict) else None
                    price_range = prefs.get("price_range") if isinstance(prefs, dict) and isinstance(prefs.get("price_range"), dict) else None
                    budget_dict = budget if isinstance(budget, dict) else price_range if isinstance(price_range, dict) else {}
                    max_price = budget_dict.get("max_price") if isinstance(budget_dict, dict) else None
                    if max_price is not None and prop_price is not None:
                        match_budget = prop_price <= max_price
                    # Площа
                    match_area = True  # Якщо немає площі — не фільтруємо
                    min_area = prefs.get("min_area") if isinstance(prefs, dict) else None
                    max_area = prefs.get("max_area") if isinstance(prefs, dict) else None
                    if prop_area is not None:
                        if min_area is not None and prop_area < min_area:
                            match_area = False
                        elif max_area is not None and prop_area > max_area:
                            match_area = False
                    # Кімнати
                    match_rooms = True  # Якщо немає — не фільтруємо
                    rooms_val = prefs.get("rooms") if isinstance(prefs, dict) else None
                    if rooms_val is not None and prop_rooms is not None:
                        try:
                            match_rooms = int(prop_rooms) == int(rooms_val)
                        except Exception:
                            match_rooms = False
                    # Новий rule-based: підрахунок збігів
                    match_count = 0
                    reasons = []
                    if match_city:
                        match_count += 1
                        reasons.append("Місто збігається")
                    if match_budget:
                        match_count += 1
                        reasons.append("Бюджет підходить")
                    if match_area:
                        match_count += 1
                        reasons.append("Площа підходить")
                    if match_rooms:
                        match_count += 1
                        reasons.append("Кількість кімнат підходить")
                    if match_count == 0:
                        continue  # Жодного збігу — не включати
                    match_score = match_count / 4
                    client_matches.append({
                        "client_id": str(client["_id"]),
                        "client_name": client.get("name", "") or client.get("first_name", ""),
                        "client_email": client.get("email", ""),
                        "client_phone": client.get("phone", ""),
                        "match_score": match_score,
                        "match_reasons": reasons,
                        "recommended_actions": ["Зв'язатися з клієнтом"]
                    })
                except Exception as e:
                    pass
            # Сортування: спочатку топові, потім часткові
            client_matches.sort(key=lambda x: x["match_score"], reverse=True)
            client_matches = client_matches[:10]
            return Response.success({
                "property_id": str(property_id),
                "property_title": property_data.get("title", ""),
                "property_summary": self._get_property_summary(property_data),
                "matched_clients": client_matches,
                "total_analyzed": len(clients),
                "analysis_timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            return Response.error(
                message=f"Помилка при аналізі клієнтів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_daily_admin_tasks(
        self,
        request: Request,
        admin_id: Optional[str] = Query(None, description="ID адміна (якщо не вказано, береться з токена)"),
        date: Optional[str] = Query(None, description="Дата в форматі YYYY-MM-DD (за замовчуванням сьогодні)")
    ) -> Dict[str, Any]:
        """
        Отримання щоденних задач адміна (з автоматичним генеруванням якщо потрібно).
        """
        try:
            # Визначення дати
            if date:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
            else:
                target_date = datetime.utcnow().date()

            # Отримання ID адміна з токена якщо не вказано
            if not admin_id:
                # TODO: Отримати з JWT токена
                admin_id = "current_admin"  # Заглушка

            # Пошук існуючих задач на цю дату
            existing_tasks = await self.db.admin_daily_tasks.find_one({
                "admin_id": admin_id,
                "date": target_date.isoformat()
            })

            if existing_tasks:
                return Response.success({
                    "admin_id": admin_id,
                    "date": target_date.isoformat(),
                    "tasks": existing_tasks["tasks"],
                    "generation_metadata": existing_tasks.get("generation_metadata", {}),
                    "last_updated": existing_tasks.get("last_updated"),
                    "source": "existing"
                })
            else:
                # Автоматичне генерування задач
                generated_tasks = await self.generate_daily_tasks_for_admin(admin_id, target_date)
                return generated_tasks

        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні завдань: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def generate_daily_tasks_for_admin(
        self, 
        admin_id: str, 
        target_date: datetime.date,
        force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """
        Генерування щоденних задач для адміна з збереженням у БД.
        """
        try:
            # Перевірка чи існують задачі на цю дату
            if not force_regenerate:
                existing = await self.db.admin_daily_tasks.find_one({
                    "admin_id": admin_id,
                    "date": target_date.isoformat()
                })
                if existing:
                    return Response.success({
                        "admin_id": admin_id,
                        "date": target_date.isoformat(),
                        "tasks": existing["tasks"],
                        "message": "Задачі вже існують для цієї дати",
                        "source": "existing"
                    })

            # Збір даних для аналізу
            analysis_data = await self._collect_admin_analysis_data(admin_id, target_date)
            
            # AI генерація завдань
            generated_tasks = await self._generate_daily_tasks(analysis_data, target_date)
            
            # Підготовка документа для збереження
            tasks_document = {
                "admin_id": admin_id,
                "date": target_date.isoformat(),
                "tasks": generated_tasks,
                "generation_metadata": {
                    "generated_at": datetime.utcnow().isoformat(),
                    "generation_method": "ai_auto",
                    "data_snapshot": analysis_data["summary"]
                },
                "last_updated": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(days=90)).isoformat()  # 3 місяці
            }

            # Збереження в БД (upsert)
            await self.db.admin_daily_tasks.update_one(
                {"admin_id": admin_id, "date": target_date.isoformat()},
                {"$set": tasks_document},
                upsert=True
            )
            
            return Response.success({
                "admin_id": admin_id,
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
        admin_id: str = Path(..., description="ID адміна"),
        date: str = Path(..., description="Дата в форматі YYYY-MM-DD"),
        tasks_update: Dict[str, Any] = Body(..., description="Оновлення задач")
    ) -> Dict[str, Any]:
        """
        Оновлення щоденних задач адміна.
        """
        try:
            # Валідація дати
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            
            # Пошук існуючих задач
            existing_tasks = await self.db.admin_daily_tasks.find_one({
                "admin_id": admin_id,
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
            await self.db.admin_daily_tasks.update_one(
                {"admin_id": admin_id, "date": date},
                {"$set": update_data}
            )
            
            # Отримання оновленого документа
            updated_document = await self.db.admin_daily_tasks.find_one({
                "admin_id": admin_id,
                "date": date
            })
            # --- ВИПРАВЛЕННЯ: серіалізація datetime ---
            def serialize_dt(val):
                if isinstance(val, datetime):
                    return val.isoformat()
                return val
            # tasks
            tasks = updated_document.get("tasks", [])
            for t in tasks:
                if "created_at" in t:
                    t["created_at"] = serialize_dt(t["created_at"])
                if "updated_at" in t:
                    t["updated_at"] = serialize_dt(t["updated_at"])
            # last_updated, expires_at, created_at
            last_updated = serialize_dt(updated_document.get("last_updated"))
            created_at = serialize_dt(updated_document.get("created_at"))
            expires_at = serialize_dt(updated_document.get("expires_at"))
            return Response.success({
                "admin_id": admin_id,
                "date": date,
                "tasks": tasks,
                "last_updated": last_updated,
                "created_at": created_at,
                "expires_at": expires_at,
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
        admin_ids: Optional[List[str]] = Query(None, description="Список ID адмінів (якщо не вказано - всі активні)")
    ) -> Dict[str, Any]:
        """
        Масове генерування щоденних задач для всіх адмінів (для cron job).
        """
        try:
            # Визначення дати
            if date:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
            else:
                target_date = datetime.utcnow().date()

            # Отримання списку адмінів
            if admin_ids:
                admins = await self.db.admins.find({"_id": {"$in": [ObjectId(aid) for aid in admin_ids]}, "role": "admin"})
            else:
                admins = await self.db.admins.find({"status": {"$ne": "inactive"}, "role": "admin"})

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
                    result = await self.generate_daily_tasks_for_admin(
                        admin_id, target_date, force_regenerate=False
                    )
                    # result може бути Response.success (dict) або JSONResponse
                    # Якщо це Response.success, то це dict з 'status' і 'data'
                    if isinstance(result, dict):
                        if result.get("status") == "success":
                            results["successful"] += 1
                            results["results"].append({
                                "admin_id": admin_id,
                                "status": "success",
                                "tasks_count": len(result["data"]["tasks"]) if "data" in result and "tasks" in result["data"] else 0
                            })
                        else:
                            results["failed"] += 1
                            results["results"].append({
                                "admin_id": admin_id,
                                "status": "failed",
                                "error": result.get("message", "Unknown error")
                            })
                    else:
                        # Якщо це не dict (наприклад, JSONResponse), пробуємо отримати .body
                        try:
                            import json
                            body = result.body if hasattr(result, "body") else result
                            if isinstance(body, bytes):
                                body = body.decode()
                            data = json.loads(body)
                            if data.get("status") == "success":
                                results["successful"] += 1
                                results["results"].append({
                                    "admin_id": admin_id,
                                    "status": "success",
                                    "tasks_count": len(data["data"]["tasks"]) if "data" in data and "tasks" in data["data"] else 0
                                })
                            else:
                                results["failed"] += 1
                                results["results"].append({
                                    "admin_id": admin_id,
                                    "status": "failed",
                                    "error": data.get("message", "Unknown error")
                                })
                        except Exception as e:
                            results["failed"] += 1
                            results["results"].append({
                                "admin_id": admin_id,
                                "status": "failed",
                                "error": str(e)
                            })
                except Exception as e:
                    results["failed"] += 1
                    results["results"].append({
                        "admin_id": admin_id,
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
            result = await self.db.admin_daily_tasks.delete_many({
                "expires_at": {"$lt": datetime.utcnow()}
            })
            # Також видалення задач старших за 3 місяці (якщо expires_at не встановлено)
            old_result = await self.db.admin_daily_tasks.delete_many({
                "created_at": {"$lt": three_months_ago},
                "expires_at": {"$exists": False}
            })
            # Якщо повертається int, а не об'єкт з .deleted_count
            def get_deleted_count(obj):
                if hasattr(obj, "deleted_count"):
                    return obj.deleted_count
                elif isinstance(obj, int):
                    return obj
                return 0
            total_deleted = get_deleted_count(result) + get_deleted_count(old_result)
            return Response.success({
                "deleted_count": total_deleted,
                "deleted_expired": get_deleted_count(result),
                "deleted_old": get_deleted_count(old_result),
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
        if isinstance(location, dict):
            if location.get("city"):
                parts.append(f"Місто: {location['city']}")
            if location.get("district"):
                parts.append(f"Район: {location['district']}")
        
        # Ціна
        price = property_data.get("price", {})
        if isinstance(price, dict) and price.get("amount"):
            parts.append(f"Ціна: {price['amount']} {price.get('currency', 'грн')}")
        elif isinstance(property_data.get("price"), (int, float)):
            parts.append(f"Ціна: {property_data['price']} грн")
        
        # Характеристики
        if isinstance(property_data.get("area"), (int, float, str)):
            parts.append(f"Площа: {property_data['area']} кв.м")
        if isinstance(property_data.get("rooms"), (int, float, str)):
            parts.append(f"Кімнат: {property_data['rooms']}")
        
        features = property_data.get("features", None)
        if isinstance(features, dict):
            if features.get("bedrooms"):
                parts.append(f"Спалень: {features['bedrooms']}")
            if features.get("bathrooms"):
                parts.append(f"Санвузлів: {features['bathrooms']}")
        elif isinstance(features, list):
            if features:
                parts.append(f"Особливості: {', '.join(map(str, features))}")
        elif isinstance(features, str):
            parts.append(f"Особливості: {features}")
        # Якщо features - число або None, ігноруємо
        
        return " | ".join(parts)

    def _prepare_client_analysis_text(self, client_data: Dict) -> str:
        """Підготовка тексту клієнта для AI аналізу."""
        parts = []
        
        # Основна інформація
        parts.append(f"Клієнт: {client_data.get('name', 'не вказано')}")
        
        # Вподобання
        preferences = client_data.get("client_preferences") or client_data.get("preferences", {})
        if not isinstance(preferences, dict):
            preferences = {}
        if isinstance(preferences.get("property_type"), str):
            parts.append(f"Шукає: {preferences['property_type']}")
        if isinstance(preferences.get("transaction_type"), str):
            parts.append(f"Операція: {preferences['transaction_type']}")
        
        # Бюджет
        budget = preferences.get("budget", {})
        if isinstance(budget, dict) and (isinstance(budget.get("min_price"), (int, float)) or isinstance(budget.get("max_price"), (int, float))):
            min_price = budget.get("min_price", 0)
            max_price = budget.get("max_price", "∞")
            parts.append(f"Бюджет: {min_price} - {max_price}")
        
        # Локація
        location_prefs = preferences.get("location", {})
        if isinstance(location_prefs, dict):
            if isinstance(location_prefs.get("cities"), list) and location_prefs.get("cities"):
                parts.append(f"Міста: {', '.join(map(str, location_prefs['cities']))}")
            if isinstance(location_prefs.get("districts"), list) and location_prefs.get("districts"):
                parts.append(f"Райони: {', '.join(map(str, location_prefs['districts']))}")
        
        # Характеристики
        if (isinstance(preferences.get("min_area"), (int, float)) or isinstance(preferences.get("max_area"), (int, float))):
            min_area = preferences.get("min_area", 0)
            max_area = preferences.get("max_area", "∞")
            parts.append(f"Площа: {min_area} - {max_area} кв.м")
        
        if isinstance(preferences.get("rooms"), (int, float, str)):
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
        
        system_prompt = """Ти - експертний AI помічник для адмінів нерухомості. 
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
        
        Проаналізуй відповідність та дай рекомендації адміну."""
        
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

    async def _collect_admin_analysis_data(self, admin_id: str, target_date) -> Dict[str, Any]:
        """Збір даних для аналізу щоденних завдань адміна."""
        
        # Нові нерухомості за останні 24 години
        yesterday = datetime.combine(target_date, datetime.min.time()) - timedelta(days=1)
        new_properties = await self.db.properties.find({
            "created_at": {"$gte": yesterday},
            "admin_id": admin_id
        })
        
        # Активні клієнти адміна
        active_clients = await self.db.users.find({
            "user_type": "client",
            "assigned_admin_id": admin_id,
            "client_status": "active"
        })
        
        # Заплановані події на сьогодні
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        today_events = await self.db.calendar_events.find({
            "admin_id": admin_id,
            "start_date": {"$gte": start_of_day, "$lte": end_of_day}
        })
        
        # Активні угоди
        active_deals = await self.db.deals.find({
            "admin_id": admin_id,
            "status": {"$in": ["active", "pending", "negotiation"]}
        })
        
        # Клієнти без активності > 7 днів
        week_ago = datetime.utcnow() - timedelta(days=7)
        inactive_clients = await self.db.users.find({
            "user_type": "client",
            "assigned_admin_id": admin_id,
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
        
        system_prompt = """Ти - AI помічник для адміна нерухомості. 
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
        if isinstance(location, dict) and location.get("city"):
            parts.append(location["city"])
            
        price = property_data.get("price")
        if isinstance(price, dict) and price.get("amount"):
            parts.append(f"{price['amount']} {price.get('currency', 'грн')}")
        elif isinstance(price, (int, float)):
            parts.append(f"{price} грн")
        
        return " • ".join(parts) 