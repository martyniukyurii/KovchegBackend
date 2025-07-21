from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime
from api.jwt_handler import JWTHandler


class MarketingEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_campaigns(
        self,
        request: Request,
        status_filter: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати маркетингові кампанії (потребує авторизації).
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
            if status_filter:
                filters["status"] = status_filter
            
            skip = (page - 1) * limit
            campaigns = await self.db.marketing_campaigns.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.marketing_campaigns.count(filters)
            
            return Response.success({
                "campaigns": campaigns,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні маркетингових кампаній: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_campaign(self, request: Request) -> Dict[str, Any]:
        """
        Створити маркетингову кампанію (потребує авторизації).
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
            required_fields = ["name", "type", "budget"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення кампанії
            campaign_data = {
                "name": data["name"],
                "description": data.get("description", ""),
                "type": data["type"],  # email, social, ads, seo
                "budget": data["budget"],
                "target_audience": data.get("target_audience", []),
                "channels": data.get("channels", []),
                "start_date": data.get("start_date"),
                "end_date": data.get("end_date"),
                "goals": data.get("goals", []),
                "metrics": data.get("metrics", {}),
                "status": "draft",
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            campaign_id = await self.db.marketing_campaigns.create(campaign_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="marketing_campaign_created",
                description=f"Створено маркетингову кампанію: {data['name']}",
                metadata={"campaign_id": campaign_id}
            )
            
            return Response.success({
                "message": "Маркетингову кампанію успішно створено",
                "campaign_id": campaign_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні маркетингової кампанії: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_campaign(self, campaign_id: str, request: Request) -> Dict[str, Any]:
        """
        Отримати маркетингову кампанію за ID (потребує авторизації).
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
            
            campaign = await self.db.marketing_campaigns.find_one({"_id": campaign_id})
            
            if not campaign:
                raise AuthException(AuthErrorCode.CAMPAIGN_NOT_FOUND)
            
            return Response.success({"campaign": campaign})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні маркетингової кампанії: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_campaign(self, campaign_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити маркетингову кампанію (потребує авторизації).
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
            
            # Перевірка існування кампанії
            campaign = await self.db.marketing_campaigns.find_one({"_id": campaign_id})
            if not campaign:
                raise AuthException(AuthErrorCode.CAMPAIGN_NOT_FOUND)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = [
                "name", "description", "budget", "target_audience", "channels",
                "start_date", "end_date", "goals", "metrics", "status"
            ]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            await self.db.marketing_campaigns.update({"_id": campaign_id}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="marketing_campaign_updated",
                description=f"Оновлено маркетингову кампанію: {campaign_id}",
                metadata={"campaign_id": campaign_id}
            )
            
            return Response.success({"message": "Маркетингову кампанію успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні маркетингової кампанії: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_campaign(self, campaign_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити маркетингову кампанію (потребує авторизації).
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
            
            # Перевірка існування кампанії
            campaign = await self.db.marketing_campaigns.find_one({"_id": campaign_id})
            if not campaign:
                raise AuthException(AuthErrorCode.CAMPAIGN_NOT_FOUND)
            
            await self.db.marketing_campaigns.delete({"_id": campaign_id})
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="marketing_campaign_deleted",
                description=f"Видалено маркетингову кампанію: {campaign_id}",
                metadata={"campaign_id": campaign_id}
            )
            
            return Response.success({"message": "Маркетингову кампанію успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні маркетингової кампанії: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_leads(
        self,
        request: Request,
        source: Optional[str] = Query(None),
        status_filter: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати ліди (потребує авторизації).
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
            if source:
                filters["source"] = source
            if status_filter:
                filters["status"] = status_filter
            
            skip = (page - 1) * limit
            leads = await self.db.leads.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.leads.count(filters)
            
            return Response.success({
                "leads": leads,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні лідів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_lead(self, request: Request) -> Dict[str, Any]:
        """
        Створити лід (потребує авторизації).
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
            required_fields = ["name", "contact", "source"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення ліда
            lead_data = {
                "name": data["name"],
                "contact": data["contact"],  # email or phone
                "source": data["source"],  # website, ad, referral, etc.
                "interest": data.get("interest", ""),
                "budget": data.get("budget", {}),
                "notes": data.get("notes", ""),
                "status": "new",
                "score": data.get("score", 0),
                "assigned_admin_id": data.get("assigned_admin_id"),
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            lead_id = await self.db.leads.create(lead_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="lead_created",
                description=f"Створено лід: {data['name']}",
                metadata={"lead_id": lead_id}
            )
            
            return Response.success({
                "message": "Лід успішно створено",
                "lead_id": lead_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні ліда: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_lead(self, lead_id: str, request: Request) -> Dict[str, Any]:
        """
        Отримати лід за ID (потребує авторизації).
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
            
            lead = await self.db.leads.find_one({"_id": lead_id})
            
            if not lead:
                raise AuthException(AuthErrorCode.LEAD_NOT_FOUND)
            
            return Response.success({"lead": lead})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні ліда: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_lead(self, lead_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити лід (потребує авторизації).
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
            
            # Перевірка існування ліда
            lead = await self.db.leads.find_one({"_id": lead_id})
            if not lead:
                raise AuthException(AuthErrorCode.LEAD_NOT_FOUND)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = [
                "name", "contact", "interest", "budget", "notes", 
                "status", "score", "assigned_admin_id"
            ]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            await self.db.leads.update({"_id": lead_id}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="lead_updated",
                description=f"Оновлено лід: {lead_id}",
                metadata={"lead_id": lead_id}
            )
            
            return Response.success({"message": "Лід успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні ліда: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_lead(self, lead_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити лід (потребує авторизації).
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
            
            # Перевірка існування ліда
            lead = await self.db.leads.find_one({"_id": lead_id})
            if not lead:
                raise AuthException(AuthErrorCode.LEAD_NOT_FOUND)
            
            await self.db.leads.delete({"_id": lead_id})
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="lead_deleted",
                description=f"Видалено лід: {lead_id}",
                metadata={"lead_id": lead_id}
            )
            
            return Response.success({"message": "Лід успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні ліда: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 