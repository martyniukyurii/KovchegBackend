from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime
from api.jwt_handler import JWTHandler
import bcrypt


class UserProfileEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_profile(self, request: Request) -> Dict[str, Any]:
        """
        Отримати профіль користувача (потребує авторизації).
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
            
            # Отримання користувача
            user = await self.db.users.find_one({"_id": user_id})
            if not user:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            # Видалення конфіденційних даних
            user.pop("password", None)
            user.pop("verification_code", None)
            
            return Response.success({"profile": user})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні профілю: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_profile(self, request: Request) -> Dict[str, Any]:
        """
        Оновити профіль користувача (потребує авторизації).
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
            
            # Перевірка існування користувача
            user = await self.db.users.find_one({"_id": user_id})
            if not user:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = [
                "first_name", "last_name", "phone", "avatar_url", 
                "bio", "preferences", "notification_settings"
            ]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            await self.db.users.update({"_id": user_id}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="profile_updated",
                description="Користувач оновив свій профіль"
            )
            
            return Response.success({"message": "Профіль успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні профілю: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def change_password(self, request: Request) -> Dict[str, Any]:
        """
        Змінити пароль користувача (потребує авторизації).
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
            required_fields = ["current_password", "new_password"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Отримання користувача
            user = await self.db.users.find_one({"_id": user_id})
            if not user:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            # Перевірка поточного пароля
            if not bcrypt.checkpw(data["current_password"].encode('utf-8'), user["password"].encode('utf-8')):
                raise AuthException(AuthErrorCode.INVALID_CREDENTIALS)
            
            # Хешування нового пароля
            salt = bcrypt.gensalt()
            hashed_password = bcrypt.hashpw(data["new_password"].encode('utf-8'), salt).decode('utf-8')
            
            # Оновлення пароля
            await self.db.users.update(
                {"_id": user_id}, 
                {
                    "password": hashed_password,
                    "updated_at": datetime.utcnow()
                }
            )
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="password_changed",
                description="Користувач змінив пароль"
            )
            
            return Response.success({"message": "Пароль успішно змінено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при зміні пароля: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_account(self, request: Request) -> Dict[str, Any]:
        """
        Видалити акаунт користувача (потребує авторизації).
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
            
            # Обов'язкове поле
            if not data.get("password"):
                return Response.error("Пароль є обов'язковим для видалення акаунта", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Отримання користувача
            user = await self.db.users.find_one({"_id": user_id})
            if not user:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            # Перевірка пароля
            if not bcrypt.checkpw(data["password"].encode('utf-8'), user["password"].encode('utf-8')):
                raise AuthException(AuthErrorCode.INVALID_CREDENTIALS)
            
            # Логування події перед видаленням
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="account_deleted",
                description="Користувач видалив свій акаунт"
            )
            
            # Видалення користувача
            await self.db.users.delete({"_id": user_id})
            
            return Response.success({"message": "Акаунт успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні акаунта: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # Комунікації
    async def get_communications(
        self,
        request: Request,
        type_filter: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати комунікації (потребує авторизації).
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
            filters = {
                "$or": [
                    {"sender_id": user_id},
                    {"recipient_id": user_id}
                ]
            }
            if type_filter:
                filters["type"] = type_filter
            
            skip = (page - 1) * limit
            communications = await self.db.communications.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.communications.count(filters)
            
            return Response.success({
                "communications": communications,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні комунікацій: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def send_communication(self, request: Request) -> Dict[str, Any]:
        """
        Надіслати комунікацію (потребує авторизації).
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
            required_fields = ["recipient_id", "type", "content"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення комунікації
            communication_data = {
                "sender_id": user_id,
                "recipient_id": data["recipient_id"],
                "type": data["type"],  # email, sms, call, note
                "subject": data.get("subject", ""),
                "content": data["content"],
                "status": "sent",
                "read": False,
                "related_object_id": data.get("related_object_id"),
                "related_object_type": data.get("related_object_type"),
                "created_at": datetime.utcnow()
            }
            
            communication_id = await self.db.communications.create(communication_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="communication_sent",
                description=f"Надіслано комунікацію типу {data['type']}",
                metadata={"communication_id": communication_id}
            )
            
            return Response.success({
                "message": "Комунікацію успішно надіслано",
                "communication_id": communication_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при надсиланні комунікації: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def mark_communication_as_read(self, communication_id: str, request: Request) -> Dict[str, Any]:
        """
        Позначити комунікацію як прочитану (потребує авторизації).
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
            
            # Перевірка існування комунікації
            communication = await self.db.communications.find_one({"_id": communication_id})
            if not communication:
                raise AuthException(AuthErrorCode.COMMUNICATION_NOT_FOUND)
            
            # Перевірка прав (тільки отримувач може позначити як прочитане)
            if communication["recipient_id"] != user_id:
                raise AuthException(AuthErrorCode.INSUFFICIENT_PERMISSIONS)
            
            # Оновлення статусу
            await self.db.communications.update(
                {"_id": communication_id},
                {"read": True}
            )
            
            return Response.success({"message": "Комунікацію позначено як прочитану"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при позначенні комунікації як прочитаної: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_notifications(
        self,
        request: Request,
        unread_only: bool = Query(False),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати сповіщення (потребує авторизації).
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
            filters = {"user_id": user_id}
            if unread_only:
                filters["read"] = False
            
            skip = (page - 1) * limit
            notifications = await self.db.notifications.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.notifications.count(filters)
            unread_count = await self.db.notifications.count({"user_id": user_id, "read": False})
            
            return Response.success({
                "notifications": notifications,
                "unread_count": unread_count,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні сповіщень: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def mark_notification_as_read(self, notification_id: str, request: Request) -> Dict[str, Any]:
        """
        Позначити сповіщення як прочитане (потребує авторизації).
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
            
            # Перевірка існування сповіщення
            notification = await self.db.notifications.find_one({"_id": notification_id})
            if not notification:
                raise AuthException(AuthErrorCode.NOTIFICATION_NOT_FOUND)
            
            # Перевірка прав
            if notification["user_id"] != user_id:
                raise AuthException(AuthErrorCode.INSUFFICIENT_PERMISSIONS)
            
            # Оновлення статусу
            await self.db.notifications.update(
                {"_id": notification_id},
                {"read": True}
            )
            
            return Response.success({"message": "Сповіщення позначено як прочитане"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при позначенні сповіщення як прочитаного: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def mark_all_notifications_as_read(self, request: Request) -> Dict[str, Any]:
        """
        Позначити всі сповіщення як прочитані (потребує авторизації).
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
            
            # Оновлення всіх сповіщень користувача
            await self.db.notifications.update_many(
                {"user_id": user_id, "read": False},
                {"read": True}
            )
            
            return Response.success({"message": "Всі сповіщення позначено як прочитані"})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при позначенні всіх сповіщень як прочитаних: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 