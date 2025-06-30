from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime
from api.jwt_handler import JWTHandler
import uuid


class PropertiesEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_top_offers(self, limit: int = Query(10, ge=1, le=50)) -> Dict[str, Any]:
        """
        Отримати топові пропозиції нерухомості (доступно для всіх).
        """
        try:
            # Отримуємо топові пропозиції з бази даних
            properties = await self.db.properties.find(
                {"status": "active", "is_featured": True},
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            return Response.success({"properties": properties})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні топових пропозицій: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def search_buy(
        self,
        city: Optional[str] = Query(None),
        property_type: Optional[str] = Query(None),
        min_price: Optional[float] = Query(None),
        max_price: Optional[float] = Query(None),
        min_area: Optional[float] = Query(None),
        max_area: Optional[float] = Query(None),
        rooms: Optional[int] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Пошук нерухомості для купівлі (доступно для всіх).
        """
        try:
            # Формування фільтрів
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
            
            # Пошук з пагінацією
            skip = (page - 1) * limit
            properties = await self.db.properties.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.properties.count(filters)
            
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
        city: Optional[str] = Query(None),
        property_type: Optional[str] = Query(None),
        min_price: Optional[float] = Query(None),
        max_price: Optional[float] = Query(None),
        min_area: Optional[float] = Query(None),
        max_area: Optional[float] = Query(None),
        rooms: Optional[int] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Пошук нерухомості для оренди (доступно для всіх).
        """
        try:
            # Формування фільтрів
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
            
            # Пошук з пагінацією
            skip = (page - 1) * limit
            properties = await self.db.properties.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.properties.count(filters)
            
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
        Подати заявку на продаж нерухомості (доступно для всіх).
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
            
            request_id = await self.db.sell_requests.create(sell_request)
            
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
        Отримати мої об'єкти нерухомості (потребує авторизації).
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
            
            return Response.success({"properties": properties})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні моїх об'єктів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_property(self, request: Request) -> Dict[str, Any]:
        """
        Створити об'єкт нерухомості (потребує авторизації).
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
        Отримати об'єкт нерухомості за ID.
        """
        try:
            property_obj = await self.db.properties.find_one({"_id": property_id})
            
            if not property_obj:
                raise AuthException(AuthErrorCode.PROPERTY_NOT_FOUND)
            
            return Response.success({"property": property_obj})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні об'єкта нерухомості: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_property(self, property_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити об'єкт нерухомості (потребує авторизації).
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
            property_obj = await self.db.properties.find_one({"_id": property_id})
            if not property_obj:
                raise AuthException(AuthErrorCode.PROPERTY_NOT_FOUND)
            
            # Перевірка прав власності
            if property_obj["owner_id"] != user_id:
                raise AuthException(AuthErrorCode.INSUFFICIENT_PERMISSIONS)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = ["title", "description", "price", "area", "rooms", "features", "images", "status"]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            if "location" in data:
                update_data["location"] = data["location"]
            
            await self.db.properties.update({"_id": property_id}, update_data)
            
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
        Видалити об'єкт нерухомості (потребує авторизації).
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
            property_obj = await self.db.properties.find_one({"_id": property_id})
            if not property_obj:
                raise AuthException(AuthErrorCode.PROPERTY_NOT_FOUND)
            
            # Перевірка прав власності
            if property_obj["owner_id"] != user_id:
                raise AuthException(AuthErrorCode.INSUFFICIENT_PERMISSIONS)
            
            await self.db.properties.delete({"_id": property_id})
            
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
        Додати об'єкт до обраних (потребує авторизації).
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
            property_obj = await self.db.properties.find_one({"_id": property_id})
            if not property_obj:
                raise AuthException(AuthErrorCode.PROPERTY_NOT_FOUND)
            
            # Додавання до обраних
            await self.db.users.update(
                {"_id": user_id},
                {"$addToSet": {"favorites": property_id}}
            )
            
            return Response.success({"message": "Об'єкт додано до обраних"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при додаванні до обраних: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def remove_from_favorites(self, property_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити об'єкт з обраних (потребує авторизації).
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
            
            # Видалення з обраних
            await self.db.users.update(
                {"_id": user_id},
                {"$pull": {"favorites": property_id}}
            )
            
            return Response.success({"message": "Об'єкт видалено з обраних"})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні з обраних: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_favorites(self, request: Request) -> Dict[str, Any]:
        """
        Отримати обрані об'єкти (потребує авторизації).
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
            
            # Отримання користувача з обраними
            user = await self.db.users.find_one({"_id": user_id})
            if not user:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            favorites = user.get("favorites", [])
            
            # Отримання об'єктів з обраних
            properties = []
            for property_id in favorites:
                property_obj = await self.db.properties.find_one({"_id": property_id})
                if property_obj:
                    properties.append(property_obj)
            
            return Response.success({"favorites": properties})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні обраних об'єктів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_search_history(self, request: Request) -> Dict[str, Any]:
        """
        Отримати історію пошуку (потребує авторизації).
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
            
            # Отримання користувача з історією пошуку
            user = await self.db.users.find_one({"_id": user_id})
            if not user:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            search_history = user.get("search_history", [])
            
            return Response.success({"search_history": search_history})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні історії пошуку: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 