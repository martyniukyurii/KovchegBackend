from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime, timedelta
from api.jwt_handler import JWTHandler
from bson import ObjectId


def convert_objectid(data):
    """Конвертує ObjectId та datetime в рядки для JSON серіалізації."""
    if isinstance(data, list):
        return [convert_objectid(item) for item in data]
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, ObjectId):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, (dict, list)):
                data[key] = convert_objectid(value)
        return data
    return data


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
        limit: int = Query(10, ge=1, le=50),
        assigned_to: Optional[str] = Query(None, description="ID адміна для фільтрації подій")
    ) -> Dict[str, Any]:
        """
        Отримати події календаря (тільки для адмінів).
        """
        try:
            # Перевірка що користувач є адміном
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            admin_info = await self.jwt_handler.require_admin_role(token)
            
            # Формування фільтрів
            filters = {}
            
            # Фільтр за датами
            if start_date and end_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    filters["start_time"] = {"$gte": start_dt, "$lte": end_dt}
                except ValueError:
                    return Response.error("Невірний формат дати", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Фільтр за призначеним адміном
            if assigned_to:
                # Показуємо події призначені конкретному адміну або створені ним
                filters["$or"] = [
                    {"created_by": assigned_to},
                    {"assigned_admins": assigned_to}
                ]
            else:
                # Показуємо всі події де поточний адмін є учасником
                admin_id = admin_info["user_id"]
                filters["$or"] = [
                    {"created_by": admin_id},
                    {"assigned_admins": admin_id}
                ]
            
            skip = (page - 1) * limit
            events = await self.db.calendar_events.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("start_time", 1)]
            )
            events = convert_objectid(events)
            
            # Підрахунок загальної кількості
            total = await self.db.calendar_events.count_documents(filters)
            
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
        Створити подію календаря (тільки для адмінів).
        
        Можна призначити подію іншим адмінам через поле assigned_admins.
        """
        try:
            # Перевірка що користувач є адміном
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            admin_info = await self.jwt_handler.require_admin_role(token)
            
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
            
            # Обробка призначених адмінів
            assigned_admins = data.get("assigned_admins", [])
            if assigned_admins:
                # Перевіряємо що всі ID є валідними адмінами
                for admin_id in assigned_admins:
                    try:
                        admin = await self.db.admins.find_one({"_id": ObjectId(admin_id)})
                    except:
                        admin = await self.db.admins.find_one({"_id": admin_id})
                    
                    if not admin:
                        return Response.error(f"Адмін з ID {admin_id} не знайдений", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Автоматично додаємо створювача до списку призначених адмінів
            admin_id = admin_info["user_id"]
            if admin_id not in assigned_admins:
                assigned_admins.append(admin_id)
            
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
                "assigned_admins": assigned_admins,  # Нове поле
                "created_by": admin_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            event_id = await self.db.calendar_events.create(event_data)
            
            # Логування події
            event_logger = EventLogger({"_id": admin_id})
            await event_logger.log_custom_event(
                event_type="calendar_event_created",
                description=f"Створено подію календаря: {data['title']}",
                metadata={"event_id": event_id, "assigned_admins": assigned_admins}
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
        Отримати подію за ID (тільки для адмінів).
        """
        try:
            # Перевірка що користувач є адміном
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            admin_info = await self.jwt_handler.require_admin_role(token)
            
            try:
                event = await self.db.calendar_events.find_one({"_id": ObjectId(event_id)})
            except Exception:
                event = await self.db.calendar_events.find_one({"_id": event_id})
            
            if not event:
                raise AuthException(AuthErrorCode.EVENT_NOT_FOUND)
            
            # Перевіряємо чи адмін має доступ до цієї події
            admin_id = admin_info["user_id"] 
            if (event.get("created_by") != admin_id and 
                admin_id not in event.get("assigned_admins", [])):
                return Response.error("Недостатньо прав для перегляду цієї події", status_code=status.HTTP_403_FORBIDDEN)
            
            event = convert_objectid(event)
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
        Оновити подію (тільки для адмінів).
        """
        try:
            # Перевірка що користувач є адміном
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            admin_info = await self.jwt_handler.require_admin_role(token)
            
            # Перевірка існування події
            try:
                event = await self.db.calendar_events.find_one({"_id": ObjectId(event_id)})
            except Exception:
                event = await self.db.calendar_events.find_one({"_id": event_id})
            
            if not event:
                raise AuthException(AuthErrorCode.EVENT_NOT_FOUND)
            
            # Перевіряємо чи адмін має доступ до цієї події
            admin_id = admin_info["user_id"]
            if (event.get("created_by") != admin_id and 
                admin_id not in event.get("assigned_admins", [])):
                return Response.error("Недостатньо прав для редагування цієї події", status_code=status.HTTP_403_FORBIDDEN)
            
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
            
            # Оновлення assigned_admins з валідацією
            if "assigned_admins" in data:
                assigned_admins = data["assigned_admins"]
                # Перевіряємо що всі ID є валідними адмінами
                for admin_id_to_check in assigned_admins:
                    try:
                        admin = await self.db.admins.find_one({"_id": ObjectId(admin_id_to_check)})
                    except:
                        admin = await self.db.admins.find_one({"_id": admin_id_to_check})
                    
                    if not admin:
                        return Response.error(f"Адмін з ID {admin_id_to_check} не знайдений", status_code=status.HTTP_400_BAD_REQUEST)
                
                update_data["assigned_admins"] = assigned_admins
            
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
            
            try:
                await self.db.calendar_events.update({"_id": ObjectId(event_id)}, update_data)
            except Exception:
                await self.db.calendar_events.update({"_id": event_id}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": admin_id})
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
        Видалити подію (тільки для адмінів).
        """
        try:
            # Перевірка що користувач є адміном
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            admin_info = await self.jwt_handler.require_admin_role(token)
            
            # Перевірка існування події
            try:
                event = await self.db.calendar_events.find_one({"_id": ObjectId(event_id)})
            except Exception:
                event = await self.db.calendar_events.find_one({"_id": event_id})
            
            if not event:
                raise AuthException(AuthErrorCode.EVENT_NOT_FOUND)
            
            # Перевіряємо чи адмін має доступ до цієї події (тільки створювач може видаляти)
            admin_id = admin_info["user_id"]
            if event.get("created_by") != admin_id:
                return Response.error("Тільки створювач події може її видалити", status_code=status.HTTP_403_FORBIDDEN)
            
            try:
                await self.db.calendar_events.delete({"_id": ObjectId(event_id)})
            except Exception:
                await self.db.calendar_events.delete({"_id": event_id})
            
            # Логування події
            event_logger = EventLogger({"_id": admin_id})
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