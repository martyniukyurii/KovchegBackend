from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime, timedelta
from api.jwt_handler import JWTHandler


class CalendarEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_events(
        self,
        request: Request,
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати події календаря (потребує авторизації).
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
            
            if start_date and end_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    filters["start_time"] = {"$gte": start_dt, "$lte": end_dt}
                except ValueError:
                    return Response.error("Невірний формат дати", status_code=status.HTTP_400_BAD_REQUEST)
            
            skip = (page - 1) * limit
            events = await self.db.calendar_events.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("start_time", 1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.calendar_events.count(filters)
            
            return Response.success({
                "events": events,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні подій календаря: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_event(self, request: Request) -> Dict[str, Any]:
        """
        Створити подію календаря (потребує авторизації).
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
            required_fields = ["title", "start_time", "end_time"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Перетворення дат
            try:
                start_time = datetime.fromisoformat(data["start_time"].replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(data["end_time"].replace('Z', '+00:00'))
            except ValueError:
                return Response.error("Невірний формат дати", status_code=status.HTTP_400_BAD_REQUEST)
            
            if start_time >= end_time:
                return Response.error("Час початку повинен бути раніше часу закінчення", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення події
            event_data = {
                "title": data["title"],
                "description": data.get("description", ""),
                "start_time": start_time,
                "end_time": end_time,
                "type": data.get("type", "meeting"),  # meeting, viewing, call, etc.
                "status": "scheduled",
                "location": data.get("location", ""),
                "attendees": data.get("attendees", []),
                "reminders": data.get("reminders", []),
                "related_object_id": data.get("related_object_id"),
                "related_object_type": data.get("related_object_type"),
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            event_id = await self.db.calendar_events.create(event_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="calendar_event_created",
                description=f"Створено подію календаря: {data['title']}",
                metadata={"event_id": event_id}
            )
            
            return Response.success({
                "message": "Подію календаря успішно створено",
                "event_id": event_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні події календаря: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_event(self, event_id: str, request: Request) -> Dict[str, Any]:
        """
        Отримати подію за ID (потребує авторизації).
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
            
            event = await self.db.calendar_events.find_one({"_id": event_id})
            
            if not event:
                raise AuthException(AuthErrorCode.EVENT_NOT_FOUND)
            
            return Response.success({"event": event})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні події: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_event(self, event_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити подію (потребує авторизації).
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
            
            # Перевірка існування події
            event = await self.db.calendar_events.find_one({"_id": event_id})
            if not event:
                raise AuthException(AuthErrorCode.EVENT_NOT_FOUND)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = [
                "title", "description", "type", "status", "location", 
                "attendees", "reminders", "related_object_id", "related_object_type"
            ]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            # Оновлення дат з валідацією
            if "start_time" in data or "end_time" in data:
                try:
                    start_time = datetime.fromisoformat(data.get("start_time", event["start_time"]).replace('Z', '+00:00')) if isinstance(data.get("start_time", event["start_time"]), str) else data.get("start_time", event["start_time"])
                    end_time = datetime.fromisoformat(data.get("end_time", event["end_time"]).replace('Z', '+00:00')) if isinstance(data.get("end_time", event["end_time"]), str) else data.get("end_time", event["end_time"])
                    
                    if start_time >= end_time:
                        return Response.error("Час початку повинен бути раніше часу закінчення", status_code=status.HTTP_400_BAD_REQUEST)
                    
                    update_data["start_time"] = start_time
                    update_data["end_time"] = end_time
                except ValueError:
                    return Response.error("Невірний формат дати", status_code=status.HTTP_400_BAD_REQUEST)
            
            await self.db.calendar_events.update({"_id": event_id}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="calendar_event_updated",
                description=f"Оновлено подію календаря: {event_id}",
                metadata={"event_id": event_id}
            )
            
            return Response.success({"message": "Подію календаря успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні події: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_event(self, event_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити подію (потребує авторизації).
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
            
            # Перевірка існування події
            event = await self.db.calendar_events.find_one({"_id": event_id})
            if not event:
                raise AuthException(AuthErrorCode.EVENT_NOT_FOUND)
            
            await self.db.calendar_events.delete({"_id": event_id})
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="calendar_event_deleted",
                description=f"Видалено подію календаря: {event_id}",
                metadata={"event_id": event_id}
            )
            
            return Response.success({"message": "Подію календаря успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні події: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 