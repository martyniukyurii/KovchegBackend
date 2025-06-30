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
        source: Optional[str] = Query(None, description="Джерело парсингу (OLX, M2BOMBER)"),
        status_filter: Optional[str] = Query(None, description="Статус оголошення (new, processed, converted)"),
        property_type: Optional[str] = Query(None, description="Тип нерухомості (commerce, orenda, prodazh, zemlya)"),
        min_price: Optional[float] = Query(None, ge=0, description="Мінімальна ціна"),
        max_price: Optional[float] = Query(None, ge=0, description="Максимальна ціна"),
        currency: Optional[str] = Query(None, description="Валюта (UAH, USD, EUR)"),
        min_area: Optional[float] = Query(None, ge=0, description="Мінімальна площа"),
        max_area: Optional[float] = Query(None, ge=0, description="Максимальна площа"),
        min_rooms: Optional[int] = Query(None, ge=0, description="Мінімальна кількість кімнат"),
        max_rooms: Optional[int] = Query(None, ge=0, description="Максимальна кількість кімнат"),
        city: Optional[str] = Query(None, description="Місто"),
        sort_by: Optional[str] = Query("parsed_at", description="Поле для сортування (parsed_at, price, area, rooms, created_at)"),
        sort_order: Optional[str] = Query("desc", description="Порядок сортування (asc, desc)"),
        search_text: Optional[str] = Query(None, description="Пошук по тексту в назві та описі"),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати спарсені оголошення з фільтрами та сортуванням (потребує авторизації).
        
        Доступні фільтри:
        - source: джерело парсингу (OLX, M2BOMBER)
        - status_filter: статус оголошення (new, processed, converted)
        - property_type: тип нерухомості (commerce, orenda, prodazh, zemlya)
        - min_price/max_price: ціновий діапазон
        - currency: валюта (UAH, USD, EUR)
        - min_area/max_area: діапазон площі
        - min_rooms/max_rooms: діапазон кількості кімнат
        - city: пошук по місту
        - search_text: пошук по тексту в назві та описі
        - sort_by: поле для сортування (parsed_at, price, area, rooms, created_at)
        - sort_order: порядок сортування (asc, desc)
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
            
            # Базові фільтри
            if source:
                filters["source"] = source
            if status_filter:
                filters["status"] = status_filter
            if property_type:
                filters["property_type"] = property_type
            if currency:
                filters["currency"] = currency
            if city:
                filters["location.city"] = {"$regex": city, "$options": "i"}
            
            # Ціновий діапазон
            if min_price is not None or max_price is not None:
                price_filter = {}
                if min_price is not None:
                    price_filter["$gte"] = min_price
                if max_price is not None:
                    price_filter["$lte"] = max_price
                filters["price"] = price_filter
            
            # Діапазон площі
            if min_area is not None or max_area is not None:
                area_filter = {}
                if min_area is not None:
                    area_filter["$gte"] = min_area
                if max_area is not None:
                    area_filter["$lte"] = max_area
                filters["area"] = area_filter
            
            # Діапазон кімнат
            if min_rooms is not None or max_rooms is not None:
                rooms_filter = {}
                if min_rooms is not None:
                    rooms_filter["$gte"] = min_rooms
                if max_rooms is not None:
                    rooms_filter["$lte"] = max_rooms
                filters["rooms"] = rooms_filter
            
            # Текстовий пошук
            if search_text:
                filters["$or"] = [
                    {"title": {"$regex": search_text, "$options": "i"}},
                    {"description": {"$regex": search_text, "$options": "i"}}
                ]
            
            # Формування сортування
            sort_field = sort_by if sort_by in ["parsed_at", "price", "area", "rooms", "created_at"] else "parsed_at"
            sort_direction = -1 if sort_order == "desc" else 1
            
            skip = (page - 1) * limit
            listings = await self.db.parsed_listings.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[(sort_field, sort_direction)]
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

    async def get_parsed_listings_stats(self, request: Request) -> Dict[str, Any]:
        """
        Отримати статистику по спарсеним оголошенням (потребує авторизації).
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
            
            # Загальна кількість оголошень
            total_listings = await self.db.parsed_listings.count({})
            
            # Статистика по джерелам
            sources_stats = await self.db.parsed_listings.aggregate([
                {"$group": {"_id": "$source", "count": {"$sum": 1}}}
            ])
            
            # Статистика по статусам
            status_stats = await self.db.parsed_listings.aggregate([
                {"$group": {"_id": "$status", "count": {"$sum": 1}}}
            ])
            
            # Статистика по типам нерухомості
            property_type_stats = await self.db.parsed_listings.aggregate([
                {"$group": {"_id": "$property_type", "count": {"$sum": 1}}}
            ])
            
            # Статистика по валютах
            currency_stats = await self.db.parsed_listings.aggregate([
                {"$group": {"_id": "$currency", "count": {"$sum": 1}}}
            ])
            
            # Статистика по містах
            city_stats = await self.db.parsed_listings.aggregate([
                {"$group": {"_id": "$location.city", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ])
            
            # Середня ціна по типах нерухомості
            avg_price_stats = await self.db.parsed_listings.aggregate([
                {"$match": {"price": {"$gt": 0}}},
                {"$group": {
                    "_id": "$property_type", 
                    "avg_price": {"$avg": "$price"},
                    "min_price": {"$min": "$price"},
                    "max_price": {"$max": "$price"},
                    "count": {"$sum": 1}
                }}
            ])
            
            # Статистика за останні 30 днів
            from datetime import datetime, timedelta
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            
            recent_stats = await self.db.parsed_listings.aggregate([
                {"$match": {"parsed_at": {"$gte": thirty_days_ago}}},
                {"$group": {
                    "_id": {
                        "year": {"$year": "$parsed_at"},
                        "month": {"$month": "$parsed_at"},
                        "day": {"$dayOfMonth": "$parsed_at"}
                    },
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ])
            
            return Response.success({
                "total_listings": total_listings,
                "sources": sources_stats,
                "statuses": status_stats,
                "property_types": property_type_stats,
                "currencies": currency_stats,
                "top_cities": city_stats,
                "price_statistics": avg_price_stats,
                "recent_activity": recent_stats
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні статистики: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 