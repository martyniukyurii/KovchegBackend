from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime
from api.jwt_handler import JWTHandler
import uuid


class AgentsEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_agents(
        self,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати список агентів (доступно для всіх).
        """
        try:
            skip = (page - 1) * limit
            agents = await self.db.agents.find(
                {"status": "active"},
                skip=skip,
                limit=limit,
                sort=[("rating", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.agents.count({"status": "active"})
            
            return Response.success({
                "agents": agents,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні списку агентів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """
        Отримати інформацію про агента (доступно для всіх).
        """
        try:
            agent = await self.db.agents.find_one({"_id": agent_id})
            
            if not agent:
                raise AuthException(AuthErrorCode.AGENT_NOT_FOUND)
            
            return Response.success({"agent": agent})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні інформації про агента: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def apply_for_agent(self, request: Request) -> Dict[str, Any]:
        """
        Подати заявку на роботу агентом (доступно для всіх).
        """
        try:
            data = await request.json()
            
            # Обов'язкові поля
            required_fields = ["first_name", "last_name", "email", "phone"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення заявки
            application = {
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "email": data["email"],
                "phone": data["phone"],
                "experience": data.get("experience", ""),
                "education": data.get("education", ""),
                "languages": data.get("languages", []),
                "motivation": data.get("motivation", ""),
                "cv_url": data.get("cv_url", ""),
                "status": "pending",
                "created_at": datetime.utcnow()
            }
            
            application_id = await self.db.agent_applications.create(application)
            
            # Логування події
            event_logger = EventLogger()
            await event_logger.log_custom_event(
                event_type="agent_application_submitted",
                description=f"Нова заявка на роботу агентом від {data['first_name']} {data['last_name']}",
                metadata={"application_id": application_id}
            )
            
            return Response.success({
                "message": "Заявка на роботу агентом успішно подана",
                "application_id": application_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при поданні заявки на роботу агентом: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_agent(self, request: Request) -> Dict[str, Any]:
        """
        Створити агента (потребує авторизації адміністратора).
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
            
            # TODO: Перевірка ролі адміністратора
            
            data = await request.json()
            
            # Обов'язкові поля
            required_fields = ["first_name", "last_name", "email", "phone"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення агента
            agent_data = {
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "email": data["email"],
                "phone": data["phone"],
                "bio": data.get("bio", ""),
                "experience": data.get("experience", ""),
                "specializations": data.get("specializations", []),
                "languages": data.get("languages", []),
                "photo_url": data.get("photo_url", ""),
                "rating": 0.0,
                "reviews_count": 0,
                "deals_count": 0,
                "status": "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            agent_id = await self.db.agents.create(agent_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="agent_created",
                description=f"Створено агента: {data['first_name']} {data['last_name']}",
                metadata={"agent_id": agent_id}
            )
            
            return Response.success({
                "message": "Агента успішно створено",
                "agent_id": agent_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні агента: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_agent(self, agent_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити інформацію про агента (потребує авторизації).
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
            
            # Перевірка існування агента
            agent = await self.db.agents.find_one({"_id": agent_id})
            if not agent:
                raise AuthException(AuthErrorCode.AGENT_NOT_FOUND)
            
            # TODO: Перевірка прав (агент може редагувати тільки свої дані або адміністратор)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = ["bio", "experience", "specializations", "languages", "photo_url", "status"]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            await self.db.agents.update({"_id": agent_id}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="agent_updated",
                description=f"Оновлено інформацію про агента: {agent_id}",
                metadata={"agent_id": agent_id}
            )
            
            return Response.success({"message": "Інформацію про агента успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні інформації про агента: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_agent(self, agent_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити агента (потребує авторизації адміністратора).
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
            
            # TODO: Перевірка ролі адміністратора
            
            # Перевірка існування агента
            agent = await self.db.agents.find_one({"_id": agent_id})
            if not agent:
                raise AuthException(AuthErrorCode.AGENT_NOT_FOUND)
            
            await self.db.agents.delete({"_id": agent_id})
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="agent_deleted",
                description=f"Видалено агента: {agent_id}",
                metadata={"agent_id": agent_id}
            )
            
            return Response.success({"message": "Агента успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні агента: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_training_programs(
        self,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати програми підготовки агентів.
        """
        try:
            skip = (page - 1) * limit
            programs = await self.db.training_programs.find(
                {"status": "active"},
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.training_programs.count({"status": "active"})
            
            return Response.success({
                "programs": programs,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні програм підготовки: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_training_program(self, program_id: str) -> Dict[str, Any]:
        """
        Отримати програму підготовки за ID.
        """
        try:
            program = await self.db.training_programs.find_one({"_id": program_id})
            
            if not program:
                raise AuthException(AuthErrorCode.TRAINING_PROGRAM_NOT_FOUND)
            
            return Response.success({"program": program})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні програми підготовки: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 