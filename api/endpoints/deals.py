from fastapi import Depends, HTTPException, Request, Query
from fastapi import status
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime
from api.jwt_handler import JWTHandler
from bson import ObjectId
from api.models.activity_metadata import ActivityMetadataFactory, EventType


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


class DealsEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_deals(
        self,
        request: Request,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50),
        deal_status: Optional[str] = Query(None)
    ) -> Dict[str, Any]:
        """
        Отримати список угод (тільки для адмінів).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            # Формування фільтрів
            filters = {}
            if deal_status:
                filters["status"] = deal_status
            
            skip = (page - 1) * limit
            deals = await self.db.deals.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            deals = convert_objectid(deals)
            
            # Підрахунок загальної кількості
            total = await self.db.deals.count_documents(filters)
            
            return Response.success({
                "deals": deals,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
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
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            data = await request.json()
            
            # Обов'язкові поля
            required_fields = ["property_id", "client_id", "type", "price"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Перевірка існування об'єкта та клієнта
            try:
                property_obj = await self.db.properties.find_one({"_id": ObjectId(data["property_id"])})
            except Exception:
                property_obj = await self.db.properties.find_one({"_id": data["property_id"]})
            
            if not property_obj:
                raise AuthException(AuthErrorCode.PROPERTY_NOT_FOUND)
            
            try:
                client = await self.db.users.find_one({"_id": ObjectId(data["client_id"])})
            except Exception:
                client = await self.db.users.find_one({"_id": data["client_id"]})
            
            if not client:
                raise AuthException(AuthErrorCode.CLIENT_NOT_FOUND)
            
            # Створення угоди
            deal_data = {
                "property_id": data["property_id"],
                "client_id": data["client_id"],
                "admin_id": data.get("admin_id"),
                "owner_id": data.get("owner_id", user_id),  # ID власника угоди (за замовчуванням створювач)
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
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            try:
                deal = await self.db.deals.find_one({"_id": ObjectId(deal_id)})
            except Exception:
                deal = await self.db.deals.find_one({"_id": deal_id})
            
            if not deal:
                raise AuthException(AuthErrorCode.DEAL_NOT_FOUND)
            
            deal = convert_objectid(deal)
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
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            # Перевірка існування угоди
            try:
                deal = await self.db.deals.find_one({"_id": ObjectId(deal_id)})
            except Exception:
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
                "expected_close_date", "admin_id"
            ]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            try:
                await self.db.deals.update({"_id": ObjectId(deal_id)}, update_data)
            except Exception:
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
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            # Перевірка існування угоди
            try:
                deal = await self.db.deals.find_one({"_id": ObjectId(deal_id)})
            except Exception:
                deal = await self.db.deals.find_one({"_id": deal_id})
            
            if not deal:
                raise AuthException(AuthErrorCode.DEAL_NOT_FOUND)
            
            try:
                await self.db.deals.delete({"_id": ObjectId(deal_id)})
            except Exception:
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
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            skip = (page - 1) * limit
            entries = await self.db.activity_journal.find(
                {},
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            entries = convert_objectid(entries)
            
            # Підрахунок загальної кількості
            total = await self.db.activity_journal.count_documents({})
            
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
        
        Використовує систематизовані коди подій та metadata.
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            data = await request.json()
            
            # Обов'язкові поля
            required_fields = ["event_type", "description"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Валідація типу події
            event_type = data["event_type"]
            try:
                event_enum = EventType(event_type)
            except ValueError:
                return Response.error(
                    f"Невірний тип події: {event_type}. Використовуйте GET /deals/activity-codes для отримання доступних кодів",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Створення валідних metadata
            raw_metadata = data.get("metadata", {})
            validated_metadata = ActivityMetadataFactory.create_metadata(event_enum, raw_metadata)
            
            # Створення запису
            entry_data = {
                "event_type": event_type,
                "description": data["description"],
                "user_id": user_id,
                "related_object_id": data.get("related_object_id"),
                "related_object_type": data.get("related_object_type"),
                "metadata": validated_metadata,
                "created_at": datetime.utcnow()
            }
            
            entry_id = await self.db.activity_journal.create(entry_data)
            
            return Response.success({
                "message": "Запис додано до журналу активності",
                "entry_id": entry_id,
                "validated_metadata": validated_metadata
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при додаванні запису до журналу: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_activity_codes(self, request: Request) -> Dict[str, Any]:
        """
        Отримати всі доступні коди для журналу активності (потребує авторизації).
        
        Повертає структуровані коди подій, способи контакту, типи документів та інші енуми
        для використання на фронтенді при створенні записів.
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            # Отримання всіх доступних кодів
            codes = ActivityMetadataFactory.get_available_codes()
            
            return Response.success({
                "activity_codes": codes,
                "usage_info": {
                    "description": "Використовуйте ці коди при створенні записів журналу активності",
                    "example_request": {
                        "event_type": "client_call",
                        "description": "Телефонна розмова з клієнтом щодо оренди квартири",
                        "metadata": {
                            "contact_method": "phone",
                            "duration_minutes": 15,
                            "client_mood": "positive",
                            "client_interest": "high"
                        },
                        "related_object_id": "deal_id_or_property_id",
                        "related_object_type": "deal"
                    }
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні кодів активності: {str(e)}",
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
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            try:
                entry = await self.db.activity_journal.find_one({"_id": ObjectId(entry_id)})
            except Exception:
                entry = await self.db.activity_journal.find_one({"_id": entry_id})
            
            if not entry:
                raise AuthException(AuthErrorCode.ACTIVITY_JOURNAL_ENTRY_NOT_FOUND)
            
            entry = convert_objectid(entry)
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
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            # Перевірка існування запису
            try:
                entry = await self.db.activity_journal.find_one({"_id": ObjectId(entry_id)})
            except Exception:
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
                try:
                    await self.db.activity_journal.update({"_id": ObjectId(entry_id)}, update_data)
                except Exception:
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
            
            # Перевірка токена та отримання користувача
            try:
                payload = await self.jwt_handler.validate_token(token)
                user_id = payload.sub
            except:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка що користувач є адміном  
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if not admin:
                return Response.error("Доступ тільки для адмінів", status_code=status.HTTP_403_FORBIDDEN)
            
            # Перевірка існування запису
            try:
                entry = await self.db.activity_journal.find_one({"_id": ObjectId(entry_id)})
            except Exception:
                entry = await self.db.activity_journal.find_one({"_id": entry_id})
            
            if not entry:
                raise AuthException(AuthErrorCode.ACTIVITY_JOURNAL_ENTRY_NOT_FOUND)
            
            try:
                await self.db.activity_journal.delete({"_id": ObjectId(entry_id)})
            except Exception:
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