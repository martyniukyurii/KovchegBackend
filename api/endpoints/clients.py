from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime
from api.jwt_handler import JWTHandler


class ClientsEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_clients(
        self,
        request: Request,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати список клієнтів (потребує авторизації).
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
            clients = await self.db.clients.find(
                {},
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.clients.count({})
            
            return Response.success({
                "clients": clients,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні списку клієнтів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_client(self, request: Request) -> Dict[str, Any]:
        """
        Створити клієнта (потребує авторизації).
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
            
            # Створення клієнта
            client_data = {
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "email": data.get("email", ""),
                "phone": data["phone"],
                "type": data.get("type", "individual"),  # individual, corporate
                "interests": data.get("interests", []),
                "budget": data.get("budget", {}),
                "preferred_locations": data.get("preferred_locations", []),
                "notes": data.get("notes", ""),
                "status": "active",
                "source": data.get("source", "manual"),
                "assigned_agent_id": data.get("assigned_agent_id"),
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            client_id = await self.db.clients.create(client_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="client_created",
                description=f"Створено клієнта: {data['first_name']} {data['last_name']}",
                metadata={"client_id": client_id}
            )
            
            return Response.success({
                "message": "Клієнта успішно створено",
                "client_id": client_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні клієнта: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_client(self, client_id: str, request: Request) -> Dict[str, Any]:
        """
        Отримати клієнта за ID (потребує авторизації).
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
            
            client = await self.db.clients.find_one({"_id": client_id})
            
            if not client:
                raise AuthException(AuthErrorCode.CLIENT_NOT_FOUND)
            
            return Response.success({"client": client})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні клієнта: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_client(self, client_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити клієнта (потребує авторизації).
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
            
            # Перевірка існування клієнта
            client = await self.db.clients.find_one({"_id": client_id})
            if not client:
                raise AuthException(AuthErrorCode.CLIENT_NOT_FOUND)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = [
                "first_name", "last_name", "email", "phone", "type", 
                "interests", "budget", "preferred_locations", "notes", 
                "status", "assigned_agent_id"
            ]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            await self.db.clients.update({"_id": client_id}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="client_updated",
                description=f"Оновлено клієнта: {client_id}",
                metadata={"client_id": client_id}
            )
            
            return Response.success({"message": "Клієнта успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні клієнта: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_client(self, client_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити клієнта (потребує авторизації).
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
            
            # Перевірка існування клієнта
            client = await self.db.clients.find_one({"_id": client_id})
            if not client:
                raise AuthException(AuthErrorCode.CLIENT_NOT_FOUND)
            
            await self.db.clients.delete({"_id": client_id})
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="client_deleted",
                description=f"Видалено клієнта: {client_id}",
                metadata={"client_id": client_id}
            )
            
            return Response.success({"message": "Клієнта успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні клієнта: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 