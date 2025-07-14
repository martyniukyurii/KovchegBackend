from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime
from api.jwt_handler import JWTHandler


class DealsEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_deals(
        self,
        request: Request,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50),
        status: Optional[str] = Query(None)
    ) -> Dict[str, Any]:
        """
        Отримати список угод (потребує авторизації).
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
            if status:
                filters["status"] = status
            
            skip = (page - 1) * limit
            deals = await self.db.deals.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.deals.count(filters)
            
            return Response.success({
                "deals": deals,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні списку угод: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_deal(self, request: Request) -> Dict[str, Any]:
        """
        Створити угоду (потребує авторизації).
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
            required_fields = ["property_id", "client_id", "type", "price"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Перевірка існування об'єкта та клієнта
            property_obj = await self.db.properties.find_one({"_id": data["property_id"]})
            if not property_obj:
                raise AuthException(AuthErrorCode.PROPERTY_NOT_FOUND)
            
            client = await self.db.users.find_one({"_id": data["client_id"], "user_type": "client"})
            if not client:
                raise AuthException(AuthErrorCode.CLIENT_NOT_FOUND)
            
            # Створення угоди
            deal_data = {
                "property_id": data["property_id"],
                "client_id": data["client_id"],
                "agent_id": data.get("agent_id"),
                "type": data["type"],  # sale, rent, lease
                "price": data["price"],
                "commission": data.get("commission", 0),
                "status": "draft",
                "description": data.get("description", ""),
                "notes": data.get("notes", ""),
                "expected_close_date": data.get("expected_close_date"),
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            deal_id = await self.db.deals.create(deal_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="deal_created",
                description=f"Створено угоду: {deal_id}",
                metadata={"deal_id": deal_id}
            )
            
            return Response.success({
                "message": "Угоду успішно створено",
                "deal_id": deal_id
            })
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні угоди: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_deal(self, deal_id: str, request: Request) -> Dict[str, Any]:
        """
        Отримати угоду за ID (потребує авторизації).
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
            
            deal = await self.db.deals.find_one({"_id": deal_id})
            
            if not deal:
                raise AuthException(AuthErrorCode.DEAL_NOT_FOUND)
            
            return Response.success({"deal": deal})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні угоди: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_deal(self, deal_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити угоду (потребує авторизації).
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
            
            # Перевірка існування угоди
            deal = await self.db.deals.find_one({"_id": deal_id})
            if not deal:
                raise AuthException(AuthErrorCode.DEAL_NOT_FOUND)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = [
                "price", "commission", "status", "description", "notes", 
                "expected_close_date", "agent_id"
            ]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            await self.db.deals.update({"_id": deal_id}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="deal_updated",
                description=f"Оновлено угоду: {deal_id}",
                metadata={"deal_id": deal_id}
            )
            
            return Response.success({"message": "Угоду успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні угоди: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_deal(self, deal_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити угоду (потребує авторизації).
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
            
            # Перевірка існування угоди
            deal = await self.db.deals.find_one({"_id": deal_id})
            if not deal:
                raise AuthException(AuthErrorCode.DEAL_NOT_FOUND)
            
            await self.db.deals.delete({"_id": deal_id})
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="deal_deleted",
                description=f"Видалено угоду: {deal_id}",
                metadata={"deal_id": deal_id}
            )
            
            return Response.success({"message": "Угоду успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні угоди: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # Журнал активності
    async def get_activity_journal(
        self,
        request: Request,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати журнал активності (потребує авторизації).
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
            entries = await self.db.activity_journal.find(
                {},
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.activity_journal.count({})
            
            return Response.success({
                "entries": entries,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні журналу активності: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def add_activity_journal_entry(self, request: Request) -> Dict[str, Any]:
        """
        Додати запис до журналу активності (потребує авторизації).
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
            required_fields = ["event_type", "description"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення запису
            entry_data = {
                "event_type": data["event_type"],
                "description": data["description"],
                "user_id": user_id,
                "related_object_id": data.get("related_object_id"),
                "related_object_type": data.get("related_object_type"),
                "metadata": data.get("metadata", {}),
                "created_at": datetime.utcnow()
            }
            
            entry_id = await self.db.activity_journal.create(entry_data)
            
            return Response.success({
                "message": "Запис додано до журналу активності",
                "entry_id": entry_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при додаванні запису до журналу: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_activity_journal_entry(self, entry_id: str, request: Request) -> Dict[str, Any]:
        """
        Отримати запис журналу за ID (потребує авторизації).
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
            
            entry = await self.db.activity_journal.find_one({"_id": entry_id})
            
            if not entry:
                raise AuthException(AuthErrorCode.ACTIVITY_JOURNAL_ENTRY_NOT_FOUND)
            
            return Response.success({"entry": entry})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні запису журналу: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_activity_journal_entry(self, entry_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити запис журналу (потребує авторизації).
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
            
            # Перевірка існування запису
            entry = await self.db.activity_journal.find_one({"_id": entry_id})
            if not entry:
                raise AuthException(AuthErrorCode.ACTIVITY_JOURNAL_ENTRY_NOT_FOUND)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {}
            
            # Поля, які можна оновити
            updatable_fields = ["description", "metadata"]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            if update_data:
                await self.db.activity_journal.update({"_id": entry_id}, update_data)
            
            return Response.success({"message": "Запис журналу успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні запису журналу: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_activity_journal_entry(self, entry_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити запис журналу (потребує авторизації).
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
            
            # Перевірка існування запису
            entry = await self.db.activity_journal.find_one({"_id": entry_id})
            if not entry:
                raise AuthException(AuthErrorCode.ACTIVITY_JOURNAL_ENTRY_NOT_FOUND)
            
            await self.db.activity_journal.delete({"_id": entry_id})
            
            return Response.success({"message": "Запис журналу успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні запису журналу: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 