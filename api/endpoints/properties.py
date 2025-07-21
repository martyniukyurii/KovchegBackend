from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from tools.embedding_service import EmbeddingService
from datetime import datetime
from api.jwt_handler import JWTHandler
import uuid
from api.endpoints.users import convert_objectid
from bson import ObjectId


class PropertiesEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_top_offers(self, limit: int = Query(10, ge=1, le=50)) -> Dict[str, Any]:
        """
        🌍 ПУБЛІЧНИЙ ENDPOINT: Отримати топові пропозиції нерухомості за кількістю вподобань.
        
        Доступний для всіх без авторизації. Показує найпопулярніші об'єкти.
        
        Параметри запиту:
        - limit: кількість результатів (1-50, за замовчуванням 10)
        
        Приклад запиту:
        GET /properties/top?limit=5
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "properties": [
                    {
                        "_id": "507f1f77bcf86cd799439011",
                        "title": "Елітна квартира в центрі",
                        "property_type": "apartment",
                        "transaction_type": "sale",
                        "price": 250000,
                        "area": 120,
                        "rooms": 3,
                        "location": {
                            "city": "Київ",
                            "address": "вул. Хрещатик, 1"
                        },
                        "likes_count": 15
                    }
                ]
            }
        }
        """
        try:
            # Агрегація для підрахунку лайків та сортування
            pipeline = [
                # Тільки активні об'єкти
                {"$match": {"status": "active"}},
                
                # Lookup для підрахунку лайків
                {"$lookup": {
                    "from": "property_likes",
                    "let": {"property_id": {"$toString": "$_id"}},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$property_id", "$$property_id"]}}}
                    ],
                    "as": "likes"
                }},
                
                # Додати поле з кількістю лайків
                {"$addFields": {
                    "likes_count": {"$size": "$likes"}
                }},
                
                # Сортування за кількістю лайків (спадаюче), потім за датою
                {"$sort": {
                    "likes_count": -1,
                    "created_at": -1
                }},
                
                # Обмеження результатів
                {"$limit": limit},
                
                # Видалити поле likes (залишити тільки likes_count)
                {"$project": {
                    "likes": 0
                }}
            ]
            
            properties = await self.db.properties.aggregate(pipeline)
            properties = convert_objectid(properties)
            
            return Response.success({"properties": properties})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні топових пропозицій: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def search_buy(
        self,
        city: Optional[str] = Query(None, description="Місто для пошуку (наприклад: Київ, Львів)"),
        property_type: Optional[str] = Query(None, description="Тип нерухомості: apartment, house, commercial, land"),
        min_price: Optional[float] = Query(None, description="Мінімальна ціна в доларах США"),
        max_price: Optional[float] = Query(None, description="Максимальна ціна в доларах США"),
        min_area: Optional[float] = Query(None, description="Мінімальна площа в кв.м"),
        max_area: Optional[float] = Query(None, description="Максимальна площа в кв.м"),
        rooms: Optional[int] = Query(None, description="Кількість кімнат"),
        page: int = Query(1, ge=1, description="Номер сторінки"),
        limit: int = Query(10, ge=1, le=50, description="Кількість результатів на сторінці")
    ) -> Dict[str, Any]:
        """
        🌍 ПУБЛІЧНИЙ ENDPOINT: Пошук нерухомості для купівлі.
        
        Доступний для всіх без авторизації. Показує об'єкти на продаж з фільтрами.
        
        Параметри запиту (всі опціональні):
        - city: місто пошуку
        - property_type: тип нерухомості (apartment, house, commercial, land)
        - min_price, max_price: діапазон цін в USD
        - min_area, max_area: діапазон площі в кв.м
        - rooms: кількість кімнат
        - page: номер сторінки (за замовчуванням 1)
        - limit: кількість на сторінці (1-50, за замовчуванням 10)
        
        Приклад запиту:
        GET /properties/buy?city=Київ&property_type=apartment&min_price=50000&max_price=200000&rooms=2
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "properties": [...],
                "pagination": {
                    "page": 1,
                    "limit": 10,
                    "total": 45,
                    "pages": 5
                }
            }
        }
        """
        try:
            # Формування фільтрів для продажу
            filters = {"transaction_type": "sale", "status": "active"}
            
            if city:
                filters["location.city"] = {"$regex": city, "$options": "i"}
            if property_type:
                filters["property_type"] = property_type
            if min_price is not None:
                filters.setdefault("price", {})["$gte"] = min_price
            if max_price is not None:
                filters.setdefault("price", {})["$lte"] = max_price
            if min_area is not None:
                filters.setdefault("area", {})["$gte"] = min_area
            if max_area is not None:
                filters.setdefault("area", {})["$lte"] = max_area
            if rooms is not None:
                filters["rooms"] = rooms
            
            # Пошук з пагінацією, сортування від новіших до старших
            skip = (page - 1) * limit
            
            # Використовуємо агрегацію для додавання кількості лайків
            pipeline = [
                {"$match": filters},
                
                # Lookup для підрахунку лайків
                {"$lookup": {
                    "from": "property_likes",
                    "let": {"property_id": {"$toString": "$_id"}},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$property_id", "$$property_id"]}}}
                    ],
                    "as": "likes"
                }},
                
                # Додати поле з кількістю лайків
                {"$addFields": {
                    "likes_count": {"$size": "$likes"}
                }},
                
                # Сортування за датою створення (новіші спочатку)
                {"$sort": {"created_at": -1}},
                
                # Пагінація
                {"$skip": skip},
                {"$limit": limit},
                
                # Видалити поле likes
                {"$project": {"likes": 0}}
            ]
            
            properties = await self.db.properties.aggregate(pipeline)
            properties = convert_objectid(properties)
            
            # Підрахунок загальної кількості
            total = await self.db.properties.count_documents(filters)
            
            return Response.success({
                "properties": properties,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при пошуку нерухомості для купівлі: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def search_rent(
        self,
        city: Optional[str] = Query(None, description="Місто для пошуку"),
        property_type: Optional[str] = Query(None, description="Тип нерухомості: apartment, house, commercial"),
        min_price: Optional[float] = Query(None, description="Мінімальна ціна оренди в USD/місяць"),
        max_price: Optional[float] = Query(None, description="Максимальна ціна оренди в USD/місяць"),
        min_area: Optional[float] = Query(None, description="Мінімальна площа в кв.м"),
        max_area: Optional[float] = Query(None, description="Максимальна площа в кв.м"),
        rooms: Optional[int] = Query(None, description="Кількість кімнат"),
        page: int = Query(1, ge=1, description="Номер сторінки"),
        limit: int = Query(10, ge=1, le=50, description="Кількість результатів на сторінці")
    ) -> Dict[str, Any]:
        """
        🌍 ПУБЛІЧНИЙ ENDPOINT: Пошук нерухомості для оренди.
        
        Доступний для всіх без авторизації. Показує об'єкти в оренду з фільтрами.
        
        Параметри аналогічні до пошуку для купівлі, але ціни вказуються за місяць.
        
        Приклад запиту:
        GET /properties/rent?city=Львів&property_type=apartment&min_price=300&max_price=800&rooms=1
        
        Приклад відповіді: аналогічний до search_buy
        """
        try:
            # Формування фільтрів для оренди
            filters = {"transaction_type": "rent", "status": "active"}
            
            if city:
                filters["location.city"] = {"$regex": city, "$options": "i"}
            if property_type:
                filters["property_type"] = property_type
            if min_price is not None:
                filters.setdefault("price", {})["$gte"] = min_price
            if max_price is not None:
                filters.setdefault("price", {})["$lte"] = max_price
            if min_area is not None:
                filters.setdefault("area", {})["$gte"] = min_area
            if max_area is not None:
                filters.setdefault("area", {})["$lte"] = max_area
            if rooms is not None:
                filters["rooms"] = rooms
            
            # Пошук з пагінацією, сортування від новіших до старших
            skip = (page - 1) * limit
            
            # Використовуємо агрегацію для додавання кількості лайків
            pipeline = [
                {"$match": filters},
                
                # Lookup для підрахунку лайків
                {"$lookup": {
                    "from": "property_likes",
                    "let": {"property_id": {"$toString": "$_id"}},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$property_id", "$$property_id"]}}}
                    ],
                    "as": "likes"
                }},
                
                # Додати поле з кількістю лайків
                {"$addFields": {
                    "likes_count": {"$size": "$likes"}
                }},
                
                # Сортування за датою створення (новіші спочатку)
                {"$sort": {"created_at": -1}},
                
                # Пагінація
                {"$skip": skip},
                {"$limit": limit},
                
                # Видалити поле likes
                {"$project": {"likes": 0}}
            ]
            
            properties = await self.db.properties.aggregate(pipeline)
            properties = convert_objectid(properties)
            
            # Підрахунок загальної кількості
            total = await self.db.properties.count_documents(filters)
            
            return Response.success({
                "properties": properties,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при пошуку нерухомості для оренди: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def submit_sell_request(self, request: Request) -> Dict[str, Any]:
        """
        🌍 ПУБЛІЧНИЙ ENDPOINT: Подати заявку на продаж нерухомості.
        
        Доступний для всіх без авторизації. Користувачі подають заявки, які розглядають агенти.
        
        Тіло запиту (JSON):
        {
            "contact_name": "Іван Петренко",         // обов'язково
            "contact_phone": "+380501234567",        // обов'язково
            "contact_email": "ivan@example.com",     // опціонально
            "property_type": "apartment",            // обов'язково (apartment, house, commercial, land)
            "city": "Київ",                         // обов'язково
            "address": "вул. Хрещатик, 1",          // обов'язково
            "description": "Опис нерухомості",      // опціонально
            "price": 150000,                        // опціонально
            "area": 85,                             // опціонально
            "rooms": 3                              // опціонально
        }
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "message": "Заявка на продаж успішно подана",
                "request_id": "507f1f77bcf86cd799439011"
            }
        }
        """
        try:
            data = await request.json()
            
            # Обов'язкові поля
            required_fields = ["contact_name", "contact_phone", "property_type", "city", "address"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення заявки
            sell_request = {
                "contact_name": data["contact_name"],
                "contact_phone": data["contact_phone"],
                "contact_email": data.get("contact_email", ""),
                "property_type": data["property_type"],
                "city": data["city"],
                "address": data["address"],
                "description": data.get("description", ""),
                "price": data.get("price"),
                "area": data.get("area"),
                "rooms": data.get("rooms"),
                "status": "pending",
                "created_at": datetime.utcnow()
            }
            
            request_id = await self.db.docs_sell_requests.create(sell_request)
            
            # Логування події
            event_logger = EventLogger()
            await event_logger.log_custom_event(
                event_type="sell_request_submitted",
                description=f"Нова заявка на продаж від {data['contact_name']}",
                metadata={"request_id": request_id}
            )
            
            return Response.success({
                "message": "Заявка на продаж успішно подана",
                "request_id": request_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при поданні заявки на продаж: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_my_properties(self, request: Request) -> Dict[str, Any]:
        """
        🔒 АДМІНСЬКИЙ ENDPOINT: Отримати мої об'єкти нерухомості (потребує авторизації).
        
        Показує об'єкти, створені поточним агентом/адміном.
        
        Заголовки:
        Authorization: Bearer <jwt_token>
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "properties": [
                    {
                        "_id": "507f1f77bcf86cd799439011",
                        "title": "Моя квартира",
                        "property_type": "apartment",
                        "transaction_type": "rent",
                        "price": 12000,
                        "area": 65,
                        "rooms": 2,
                        "location": {
                            "city": "Київ",
                            "address": "вул. Саксаганського, 25"
                        },
                        "status": "active",
                        "owner_id": "687619cebc3697db0a23b3b3"
                    }
                ]
            }
        }
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
            
            # Отримання об'єктів користувача
            properties = await self.db.properties.find({"owner_id": user_id})
            properties = convert_objectid(properties)
            
            return Response.success({"properties": properties})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні моїх об'єктів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_property(self, request: Request) -> Dict[str, Any]:
        """
        🔒 АДМІНСЬКИЙ ENDPOINT: Створити об'єкт нерухомості (потребує авторизації).
        
        Призначений для агентів/адмінів. Звичайні користувачі подають заявки через /properties/sell
        
        Заголовки:
        Authorization: Bearer <jwt_token>
        Content-Type: application/json
        
        Тіло запиту (JSON):
        {
            "title": "Назва об'єкта",                    // обов'язково
            "description": "Детальний опис",             // опціонально
            "property_type": "apartment",                // обов'язково (apartment, house, commercial, land)
            "transaction_type": "rent",                  // обов'язково (rent, sale)
            "price": 12000,                             // обов'язково (USD або USD/місяць)
            "area": 65,                                 // обов'язково (кв.м)
            "rooms": 2,                                 // опціонально
            "city": "Київ",                             // обов'язково
            "address": "вул. Саксаганського, 25",       // обов'язково
            "coordinates": {                            // опціонально
                "lat": 50.4378,
                "lon": 30.5201
            },
            "features": ["балкон", "ремонт", "меблі"],   // опціонально
            "images": ["url1.jpg", "url2.jpg"]          // опціонально
        }
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "message": "Об'єкт нерухомості успішно створено",
                "property_id": "507f1f77bcf86cd799439011"
            }
        }
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
            required_fields = ["title", "property_type", "transaction_type", "price", "area", "city", "address"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення об'єкта нерухомості
            property_data = {
                "title": data["title"],
                "description": data.get("description", ""),
                "property_type": data["property_type"],
                "transaction_type": data["transaction_type"],
                "price": data["price"],
                "area": data["area"],
                "rooms": data.get("rooms"),
                "location": {
                    "city": data["city"],
                    "address": data["address"],
                    "coordinates": data.get("coordinates", {})
                },
                "features": data.get("features", []),
                "images": data.get("images", []),
                "owner_id": user_id,
                "status": "active",
                "is_featured": False,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            property_id = await self.db.properties.create(property_data)
            
            # Створюємо векторний ембединг для об'єкта нерухомості
            if property_id:
                try:
                    embedding_service = EmbeddingService()
                    embedding = await embedding_service.create_property_embedding(property_data)
                    if embedding:
                        # Конвертуємо property_id в ObjectId для пошуку
                        search_id = ObjectId(property_id) if isinstance(property_id, str) else property_id
                        
                        # Оновлюємо документ з ембедингом
                        await self.db.properties.update(
                            {"_id": search_id},
                            {"vector_embedding": embedding}
                        )
                except Exception as embedding_error:
                    # Не зупиняємо процес створення через помилку ембедингу
                    pass
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="property_created",
                description=f"Створено об'єкт нерухомості: {data['title']}",
                metadata={"property_id": property_id}
            )
            
            return Response.success({
                "message": "Об'єкт нерухомості успішно створено",
                "property_id": property_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні об'єкта нерухомості: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_property(self, property_id: str) -> Dict[str, Any]:
        """
        🔒 АДМІНСЬКИЙ ENDPOINT: Отримати об'єкт нерухомості за ID.
        
        Для перегляду детальної інформації агентами/адмінами.
        """
        try:
            try:
                property_obj = await self.db.properties.find_one({"_id": ObjectId(property_id)})
            except Exception:
                property_obj = await self.db.properties.find_one({"_id": property_id})
            
            if not property_obj:
                return Response.error("Об'єкт нерухомості не знайдено", status_code=status.HTTP_404_NOT_FOUND)
            
            property_obj = convert_objectid(property_obj)
            return Response.success({"property": property_obj})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні об'єкта нерухомості: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_property(self, property_id: str, request: Request) -> Dict[str, Any]:
        """
        🔒 АДМІНСЬКИЙ ENDPOINT: Оновити об'єкт нерухомості (потребує авторизації).
        
        Тільки власник об'єкта може його редагувати.
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
            
            try:
                property_obj = await self.db.properties.find_one({"_id": ObjectId(property_id)})
            except Exception:
                property_obj = await self.db.properties.find_one({"_id": property_id})
            
            if not property_obj:
                raise AuthException(AuthErrorCode.PROPERTY_NOT_FOUND)
            
            # Перевірка прав власності
            if str(property_obj["owner_id"]) != str(user_id):
                return Response.error("Недостатньо прав для виконання операції", status_code=status.HTTP_403_FORBIDDEN)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = ["title", "description", "price", "area", "rooms", "features", "images", "status", "is_featured"]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            if "location" in data:
                update_data["location"] = data["location"]
            
            await self.db.properties.update({"_id": property_obj["_id"]}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="property_updated",
                description=f"Оновлено об'єкт нерухомості: {property_id}",
                metadata={"property_id": property_id}
            )
            
            return Response.success({"message": "Об'єкт нерухомості успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні об'єкта нерухомості: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_property(self, property_id: str, request: Request) -> Dict[str, Any]:
        """
        🔒 АДМІНСЬКИЙ ENDPOINT: Видалити об'єкт нерухомості (потребує авторизації).
        
        Тільки власник об'єкта може його видалити.
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
            
            try:
                property_obj = await self.db.properties.find_one({"_id": ObjectId(property_id)})
            except Exception:
                property_obj = await self.db.properties.find_one({"_id": property_id})
            
            if not property_obj:
                raise AuthException(AuthErrorCode.PROPERTY_NOT_FOUND)
            
            # Перевірка прав власності
            if str(property_obj["owner_id"]) != str(user_id):
                return Response.error("Недостатньо прав для виконання операції", status_code=status.HTTP_403_FORBIDDEN)
            
            await self.db.properties.delete({"_id": property_obj["_id"]})
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="property_deleted",
                description=f"Видалено об'єкт нерухомості: {property_id}",
                metadata={"property_id": property_id}
            )
            
            return Response.success({"message": "Об'єкт нерухомості успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні об'єкта нерухомості: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def add_to_favorites(self, property_id: str, request: Request) -> Dict[str, Any]:
        """
        👤 КОРИСТУВАЦЬКИЙ ENDPOINT: Додати об'єкт до обраних (потребує авторизації).
        
        Дозволяє користувачам додавати об'єкти до списку обраних.
        Створює запис у колекції property_likes з user_id та property_id.
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "message": "Об'єкт додано до обраних"
            }
        }
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
            
            # Перевірка існування об'єкта
            try:
                property_obj = await self.db.properties.find_one({"_id": ObjectId(property_id)})
            except Exception:
                property_obj = await self.db.properties.find_one({"_id": property_id})
            
            if not property_obj:
                return Response.error("Об'єкт нерухомості не знайдено", status_code=status.HTTP_404_NOT_FOUND)
            
            # Перевірка чи вже є лайк від цього користувача
            existing_like = await self.db.property_likes.find_one({
                "user_id": user_id,
                "property_id": str(property_obj["_id"])
            })
            
            if existing_like:
                return Response.error("Об'єкт вже додано до обраних", status_code=status.HTTP_409_CONFLICT)
            
            # Створення запису лайка
            like_data = {
                "user_id": user_id,
                "property_id": str(property_obj["_id"]),
                "created_at": datetime.utcnow()
            }
            
            await self.db.property_likes.create(like_data)
            
            return Response.success({"message": "Об'єкт додано до обраних"})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при додаванні до обраних: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def remove_from_favorites(self, property_id: str, request: Request) -> Dict[str, Any]:
        """
        👤 КОРИСТУВАЦЬКИЙ ENDPOINT: Видалити об'єкт з обраних (потребує авторизації).
        
        Дозволяє користувачам видаляти об'єкти зі списку обраних.
        Видаляє запис з колекції property_likes.
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
            
            # Видалення лайка з колекції
            result = await self.db.property_likes.delete({
                "user_id": user_id,
                "property_id": property_id
            })
            
            if result == 0:  # Нічого не видалено
                return Response.error("Об'єкт не був у обраних", status_code=status.HTTP_404_NOT_FOUND)
            
            return Response.success({"message": "Об'єкт видалено з обраних"})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні з обраних: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_favorites(self, request: Request) -> Dict[str, Any]:
        """
        👤 КОРИСТУВАЦЬКИЙ ENDPOINT: Отримати обрані об'єкти (потребує авторизації).
        
        Показує список улюблених об'єктів нерухомості користувача.
        Отримує дані з колекції property_likes з повною інформацією про об'єкти.
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "favorites": [
                    {
                        "_id": "507f1f77bcf86cd799439011",
                        "title": "Квартира в центрі",
                        "property_type": "apartment",
                        "price": 150000,
                        "area": 80,
                        "location": {
                            "city": "Київ",
                            "address": "вул. Хрещатик, 1"
                        },
                        "liked_at": "2025-07-15T10:30:00Z"
                    }
                ]
            }
        }
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
            
            # Використовуємо агрегацію для отримання обраних об'єктів
            pipeline = [
                # Знаходимо всі лайки користувача
                {"$match": {"user_id": user_id}},
                
                # Lookup для отримання інформації про нерухомість
                {"$lookup": {
                    "from": "properties",
                    "let": {"property_id": {"$toObjectId": "$property_id"}},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$_id", "$$property_id"]}}}
                    ],
                    "as": "property"
                }},
                
                # Розгортаємо масив property
                {"$unwind": "$property"},
                
                # Перевіряємо, що об'єкт активний
                {"$match": {"property.status": "active"}},
                
                # Додаємо дату лайка
                {"$addFields": {
                    "property.liked_at": "$created_at"
                }},
                
                # Сортування за датою лайка (новіші спочатку)
                {"$sort": {"created_at": -1}},
                
                # Повертаємо тільки об'єкт нерухомості
                {"$replaceRoot": {"newRoot": "$property"}}
            ]
            
            favorites = await self.db.property_likes.aggregate(pipeline)
            favorites = convert_objectid(favorites)
            
            # Якщо немає обраних, повертаємо пустий список
            if not favorites:
                favorites = []
            
            return Response.success({"favorites": favorites})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні обраних об'єктів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

 