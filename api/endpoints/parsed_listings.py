from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime
from api.jwt_handler import JWTHandler


class ParsedListingsEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_parsed_listings(
        self,
        request: Request,
        source: Optional[str] = Query(None),
        status_filter: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати спарсені оголошення (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Формування фільтрів
            filters = {}
            if source:
                filters["source"] = source
            if status_filter:
                filters["status"] = status_filter
            
            skip = (page - 1) * limit
            listings = await self.db.parsed_listings.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("parsed_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.parsed_listings.count(filters)
            
            return Response.success({
                "listings": listings,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні спарсених оголошень: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_parsed_listing(self, listing_id: str, request: Request) -> Dict[str, Any]:
        """
        Отримати спарсене оголошення за ID (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            listing = await self.db.parsed_listings.find_one({"_id": listing_id})
            
            if not listing:
                raise AuthException(AuthErrorCode.PARSED_LISTING_NOT_FOUND)
            
            return Response.success({"listing": listing})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні спарсеного оголошення: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_parsed_listing(self, request: Request) -> Dict[str, Any]:
        """
        Створити спарсене оголошення (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            data = await request.json()
            
            # Обов'язкові поля
            required_fields = ["source", "external_id", "title", "price"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Перевірка на дублікати
            existing_listing = await self.db.parsed_listings.find_one({
                "source": data["source"],
                "external_id": data["external_id"]
            })
            
            if existing_listing:
                return Response.error("Оголошення з таким external_id вже існує", status_code=status.HTTP_409_CONFLICT)
            
            # Створення спарсеного оголошення
            listing_data = {
                "source": data["source"],  # olx, ria, dom_ria, etc.
                "external_id": data["external_id"],
                "title": data["title"],
                "description": data.get("description", ""),
                "price": data["price"],
                "currency": data.get("currency", "UAH"),
                "property_type": data.get("property_type", ""),
                "area": data.get("area", 0),
                "rooms": data.get("rooms", 0),
                "location": {
                    "city": data.get("city", ""),
                    "address": data.get("address", ""),
                    "coordinates": data.get("coordinates", {})
                },
                "images": data.get("images", []),
                "contact_info": data.get("contact_info", {}),
                "features": data.get("features", []),
                "url": data.get("url", ""),
                "status": "new",
                "confidence_score": data.get("confidence_score", 0.0),
                "parsed_at": datetime.utcnow(),
                "created_at": datetime.utcnow()
            }
            
            listing_id = await self.db.parsed_listings.create(listing_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="parsed_listing_created",
                description=f"Створено спарсене оголошення з {data['source']}",
                metadata={"listing_id": listing_id, "source": data["source"]}
            )
            
            return Response.success({
                "message": "Спарсене оголошення успішно створено",
                "listing_id": listing_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні спарсеного оголошення: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_parsed_listing_status(self, listing_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити статус спарсеного оголошення (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка існування оголошення
            listing = await self.db.parsed_listings.find_one({"_id": listing_id})
            if not listing:
                raise AuthException(AuthErrorCode.PARSED_LISTING_NOT_FOUND)
            
            data = await request.json()
            
            # Обов'язкове поле
            if not data.get("status"):
                return Response.error("Поле 'status' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Допустимі статуси
            valid_statuses = ["new", "processed", "approved", "rejected", "duplicate"]
            if data["status"] not in valid_statuses:
                return Response.error(f"Невірний статус. Допустимі: {', '.join(valid_statuses)}", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Оновлення статусу
            update_data = {
                "status": data["status"],
                "updated_at": datetime.utcnow()
            }
            
            if data.get("notes"):
                update_data["notes"] = data["notes"]
            
            await self.db.parsed_listings.update({"_id": listing_id}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="parsed_listing_status_updated",
                description=f"Оновлено статус спарсеного оголошення на '{data['status']}'",
                metadata={"listing_id": listing_id, "new_status": data["status"]}
            )
            
            return Response.success({"message": "Статус спарсеного оголошення успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні статусу: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def convert_to_property(self, listing_id: str, request: Request) -> Dict[str, Any]:
        """
        Конвертувати спарсене оголошення в об'єкт нерухомості (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка існування оголошення
            listing = await self.db.parsed_listings.find_one({"_id": listing_id})
            if not listing:
                raise AuthException(AuthErrorCode.PARSED_LISTING_NOT_FOUND)
            
            # Перевірка статусу
            if listing["status"] != "approved":
                return Response.error("Тільки схвалені оголошення можна конвертувати", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення об'єкта нерухомості на основі спарсених даних
            property_data = {
                "title": listing["title"],
                "description": listing.get("description", ""),
                "property_type": listing.get("property_type", "apartment"),
                "transaction_type": "sale",  # За замовчуванням
                "price": listing["price"],
                "currency": listing.get("currency", "UAH"),
                "area": listing.get("area", 0),
                "rooms": listing.get("rooms", 0),
                "location": listing.get("location", {}),
                "images": listing.get("images", []),
                "features": listing.get("features", []),
                "source": "parsed",
                "parsed_listing_id": listing_id,
                "contact_info": listing.get("contact_info", {}),
                "external_url": listing.get("url", ""),
                "status": "pending_review",
                "is_featured": False,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            property_id = await self.db.properties.create(property_data)
            
            # Оновлення статусу спарсеного оголошення
            await self.db.parsed_listings.update(
                {"_id": listing_id},
                {
                    "status": "converted",
                    "property_id": property_id,
                    "converted_at": datetime.utcnow()
                }
            )
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="parsed_listing_converted",
                description=f"Спарсене оголошення конвертовано в об'єкт нерухомості",
                metadata={"listing_id": listing_id, "property_id": property_id}
            )
            
            return Response.success({
                "message": "Спарсене оголошення успішно конвертовано в об'єкт нерухомості",
                "property_id": property_id
            })
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при конвертації: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_parsed_listing(self, listing_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити спарсене оголошення (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка існування оголошення
            listing = await self.db.parsed_listings.find_one({"_id": listing_id})
            if not listing:
                raise AuthException(AuthErrorCode.PARSED_LISTING_NOT_FOUND)
            
            await self.db.parsed_listings.delete({"_id": listing_id})
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="parsed_listing_deleted",
                description=f"Видалено спарсене оголошення: {listing_id}",
                metadata={"listing_id": listing_id}
            )
            
            return Response.success({"message": "Спарсене оголошення успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні спарсеного оголошення: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_parsing_sources(self, request: Request) -> Dict[str, Any]:
        """
        Отримати список джерел парсингу (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Отримання статистики по джерелах
            sources_stats = await self.db.parsed_listings.aggregate([
                {"$group": {
                    "_id": "$source",
                    "total_listings": {"$sum": 1},
                    "new_listings": {"$sum": {"$cond": [{"$eq": ["$status", "new"]}, 1, 0]}},
                    "processed_listings": {"$sum": {"$cond": [{"$eq": ["$status", "processed"]}, 1, 0]}},
                    "approved_listings": {"$sum": {"$cond": [{"$eq": ["$status", "approved"]}, 1, 0]}},
                    "converted_listings": {"$sum": {"$cond": [{"$eq": ["$status", "converted"]}, 1, 0]}},
                    "last_parsed": {"$max": "$parsed_at"}
                }},
                {"$sort": {"total_listings": -1}}
            ])
            
            # Конфігурація джерел
            sources_config = [
                {
                    "name": "OLX",
                    "code": "olx",
                    "url": "https://www.olx.ua",
                    "enabled": True,
                    "description": "Популярний сайт оголошень"
                },
                {
                    "name": "RIA.com",
                    "code": "ria",
                    "url": "https://ria.com",
                    "enabled": True,
                    "description": "Сайт нерухомості RIA"
                },
                {
                    "name": "DOM.RIA",
                    "code": "dom_ria",
                    "url": "https://dom.ria.com",
                    "enabled": True,
                    "description": "Спеціалізований сайт нерухомості"
                },
                {
                    "name": "Lun.ua",
                    "code": "lun",
                    "url": "https://lun.ua",
                    "enabled": False,
                    "description": "Сайт нерухомості Lun"
                }
            ]
            
            return Response.success({
                "sources_config": sources_config,
                "sources_stats": sources_stats
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні джерел парсингу: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def start_parsing_task(self, request: Request) -> Dict[str, Any]:
        """
        Запустити задачу парсингу (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            data = await request.json()
            
            # Обов'язкові поля
            required_fields = ["sources", "search_criteria"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення задачі парсингу
            task_data = {
                "sources": data["sources"],  # Список джерел для парсингу
                "search_criteria": data["search_criteria"],  # Критерії пошуку
                "status": "pending",
                "progress": 0,
                "total_found": 0,
                "processed": 0,
                "errors": [],
                "started_by": user_id,
                "created_at": datetime.utcnow()
            }
            
            task_id = await self.db.parsing_tasks.create(task_data)
            
            # TODO: Запустити фонову задачу парсингу
            # Тут має бути інтеграція з Celery або іншим менеджером задач
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="parsing_task_started",
                description=f"Запущено задачу парсингу: {task_id}",
                metadata={"task_id": task_id, "sources": data["sources"]}
            )
            
            return Response.success({
                "message": "Задача парсингу успішно запущена",
                "task_id": task_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при запуску задачі парсингу: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_parsing_task_status(self, task_id: str, request: Request) -> Dict[str, Any]:
        """
        Отримати статус задачі парсингу (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Отримання задачі
            task = await self.db.parsing_tasks.find_one({"_id": task_id})
            if not task:
                raise AuthException(AuthErrorCode.PARSING_TASK_NOT_FOUND)
            
            return Response.success({"task": task})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні статусу задачі: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 