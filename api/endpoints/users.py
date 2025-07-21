from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime
from api.jwt_handler import JWTHandler
from bson import ObjectId


def convert_objectid(data):
    """Конвертує ObjectId та datetime в рядки для серіалізації в JSON та видаляє векторні ембединги"""
    if isinstance(data, dict):
        # Видаляємо векторні ембединги з відповіді (вони не потрібні фронтенду)
        if 'vector_embedding' in data:
            del data['vector_embedding']
            
        for key, value in data.items():
            if isinstance(value, ObjectId):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, dict) or isinstance(value, list):
                data[key] = convert_objectid(value)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, ObjectId):
                data[i] = str(item)
            elif isinstance(item, datetime):
                data[i] = item.isoformat()
            elif isinstance(item, dict) or isinstance(item, list):
                data[i] = convert_objectid(item)
    return data


class UsersEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_users(
        self,
        request: Request,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати список користувачів (потребує авторизації).
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
            
            skip = (page - 1) * limit
            users = await self.db.users.find(
                {"user_type": "client"},
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Конвертуємо ObjectId в рядки для серіалізації
            users = convert_objectid(users)
            
            # Підрахунок загальної кількості
            total = await self.db.users.count_documents({"user_type": "client"})
            
            return Response.success({
                "users": users,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні списку користувачів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_user(self, request: Request) -> Dict[str, Any]:
        """
        Створити користувача (потребує авторизації).
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
            required_fields = ["first_name", "last_name", "phone"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення користувача
            user_data = {
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "email": data.get("email", ""),
                "phone": data["phone"],
                "login": data.get("email", ""),
                "password": None,  # Користувач створений адміном/адміном, пароль не потрібен
                "user_type": "client",
                "client_status": "active",
                "client_interests": data.get("interests", []),
                "client_budget": data.get("budget", {}),
                "client_preferred_locations": data.get("preferred_locations", []),
                "client_notes": data.get("notes", ""),
                "client_source": data.get("source", "manual"),
                "assigned_admin_id": data.get("assigned_admin_id"),
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_verified": False,
                "language_code": "uk",
                "favorites": [],
                "search_history": [],
                "notifications_settings": {
                    "telegram": True,
                    "email": True
                },
                "client_preferences": {
                    "property_type": data.get("property_type", []),
                    "price_range": data.get("price_range", {}),
                    "location": data.get("location", []),
                    "features": data.get("features", [])
                }
            }
            
            user_id = await self.db.users.create(user_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="user_created",
                description=f"Створено користувача: {data['first_name']} {data['last_name']}",
                metadata={"user_id": user_id}
            )
            
            return Response.success({
                "message": "Користувача успішно створено",
                "user_id": user_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні користувача: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_user(self, user_id: str, request: Request) -> Dict[str, Any]:
        """
        Отримати користувача за ID (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            admin_id = payload.get("sub")
            
            if not admin_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Конвертуємо рядок в ObjectId
            try:
                user_id_obj = ObjectId(user_id)
            except:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            user = await self.db.users.find_one({"_id": user_id_obj, "user_type": "client"})
            
            if not user:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            # Конвертуємо ObjectId в рядки для серіалізації
            user = convert_objectid(user)
            
            return Response.success({"user": user})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні користувача: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_user(self, user_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити користувача (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            admin_id = payload.get("sub")
            
            if not admin_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Конвертуємо рядок в ObjectId
            try:
                user_id_obj = ObjectId(user_id)
            except:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            # Перевірка існування користувача
            user = await self.db.users.find_one({"_id": user_id_obj, "user_type": "client"})
            if not user:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = [
                "first_name", "last_name", "email", "phone", 
                "client_interests", "client_budget", "client_preferred_locations", 
                "client_notes", "client_status", "assigned_admin_id"
            ]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            await self.db.users.update({"_id": user_id_obj}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": admin_id})
            await event_logger.log_custom_event(
                event_type="user_updated",
                description=f"Оновлено користувача: {user_id}",
                metadata={"user_id": user_id}
            )
            
            return Response.success({"message": "Користувача успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні користувача: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_user(self, user_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити користувача (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            admin_id = payload.get("sub")
            
            if not admin_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Конвертуємо рядок в ObjectId
            try:
                user_id_obj = ObjectId(user_id)
            except:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            # Перевірка існування користувача
            user = await self.db.users.find_one({"_id": user_id_obj, "user_type": "client"})
            if not user:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            await self.db.users.delete({"_id": user_id_obj})
            
            # Логування події
            event_logger = EventLogger({"_id": admin_id})
            await event_logger.log_custom_event(
                event_type="user_deleted",
                description=f"Видалено користувача: {user_id}",
                metadata={"user_id": user_id}
            )
            
            return Response.success({"message": "Користувача успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні користувача: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 