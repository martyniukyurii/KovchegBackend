from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from tools.embedding_service import EmbeddingService
from tools.logger import Logger
from datetime import datetime
from api.jwt_handler import JWTHandler
from bson import ObjectId
import urllib.parse

logger = Logger()


def convert_mongo_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Конвертує MongoDB документ в JSON-сумісний формат та видаляє векторні ембединги"""
    if not doc:
        return doc
    
    # Видаляємо векторні ембединги з відповіді (вони не потрібні фронтенду)
    if 'vector_embedding' in doc:
        del doc['vector_embedding']
    
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            doc[key] = str(value)
        elif isinstance(value, datetime):
            doc[key] = value.isoformat()
        elif isinstance(value, dict):
            doc[key] = convert_mongo_document(value)
        elif isinstance(value, list):
            doc[key] = [convert_mongo_document(item) if isinstance(item, dict) else 
                       str(item) if isinstance(item, ObjectId) else 
                       item.isoformat() if isinstance(item, datetime) else item 
                       for item in value]
    return doc


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
        Отримати список спарсених оголошень з фільтрацією та пагінацією (потребує авторизації).
        
        Параметри:
        - source: джерело парсингу (OLX, M2BOMBER)
        - status_filter: статус оголошення (new, processed, converted)
        - property_type: тип нерухомості (commerce, orenda, prodazh, zemlya)
        - min_price, max_price: ціновий діапазон
        - currency: валюта (UAH, USD, EUR)
        - min_area, max_area: діапазон площі
        - min_rooms, max_rooms: діапазон кімнат
        - city: місто
        - search_text: пошук по тексту в назві та описі
        - page: номер сторінки
        - limit: кількість результатів на сторінку
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
                # Правильно обробляємо українські символи
                decoded_city = urllib.parse.unquote(city) if '%' in city else city
                filters["location.city"] = {"$regex": decoded_city, "$options": "i"}
            
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
                # Правильно обробляємо українські символи
                decoded_search_text = urllib.parse.unquote(search_text) if '%' in search_text else search_text
                filters["$or"] = [
                    {"title": {"$regex": decoded_search_text, "$options": "i"}},
                    {"description": {"$regex": decoded_search_text, "$options": "i"}}
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
            
            # Конвертація MongoDB об'єктів для JSON серіалізації
            listings = [convert_mongo_document(listing) for listing in listings]
            
            # Підрахунок загальної кількості
            total = await self.db.parsed_listings.count_documents(filters)
            
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
            
            # --- ВИПРАВЛЕННЯ: підтримка ObjectId ---
            query = None
            try:
                query = {"_id": ObjectId(listing_id)}
            except Exception:
                query = {"_id": listing_id}
            listing = await self.db.parsed_listings.find_one(query)
            
            if not listing:
                raise AuthException(AuthErrorCode.PARSED_LISTING_NOT_FOUND)
            
            # --- ВИПРАВЛЕННЯ: серіалізація ObjectId ---
            listing = convert_mongo_document(listing)
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
                "status": data.get("status", "new"),  # Дозволяємо передавати статус через API
                "confidence_score": data.get("confidence_score", 0.0),
                "parsed_at": datetime.utcnow(),
                "created_at": datetime.utcnow()
            }
            
            listing_id = await self.db.parsed_listings.create(listing_data)
            
            # Створюємо векторний ембединг для оголошення
            if listing_id:
                try:
                    embedding_service = EmbeddingService()
                    embedding = await embedding_service.create_listing_embedding(listing_data)
                    if embedding:
                        # Конвертуємо listing_id в ObjectId для пошуку
                        from bson import ObjectId
                        search_id = ObjectId(listing_id) if isinstance(listing_id, str) else listing_id
                        
                        # Оновлюємо документ з ембедингом
                        await self.db.parsed_listings.update(
                            {"_id": search_id},
                            {"vector_embedding": embedding}
                        )
                except Exception as embedding_error:
                    logger.error(f"❌ Помилка створення ембедингу через API: {embedding_error}")
                    # Продовжуємо без ембедингу
                    pass
            
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
            
            # --- ВИПРАВЛЕННЯ: підтримка ObjectId ---
            query = None
            try:
                query = {"_id": ObjectId(listing_id)}
            except Exception:
                query = {"_id": listing_id}
            listing = await self.db.parsed_listings.find_one(query)
            
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
            
            # --- ВИПРАВЛЕННЯ: підтримка ObjectId ---
            query = None
            try:
                query = {"_id": ObjectId(listing_id)}
            except Exception:
                query = {"_id": listing_id}
            listing = await self.db.parsed_listings.find_one(query)
            if not listing:
                raise AuthException(AuthErrorCode.PARSED_LISTING_NOT_FOUND)
            await self.db.parsed_listings.delete(query)
            
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