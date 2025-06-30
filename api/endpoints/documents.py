from fastapi import Depends, HTTPException, status, Request, Query, UploadFile, File
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime
from api.jwt_handler import JWTHandler
import uuid


class DocumentsEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_documents(
        self,
        request: Request,
        category: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати список документів (потребує авторизації).
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
            if category:
                filters["category"] = category
            
            skip = (page - 1) * limit
            documents = await self.db.documents.find(
                filters,
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Підрахунок загальної кількості
            total = await self.db.documents.count(filters)
            
            return Response.success({
                "documents": documents,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні списку документів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def upload_document(self, request: Request) -> Dict[str, Any]:
        """
        Завантажити документ (потребує авторизації).
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
            required_fields = ["title", "category", "file_url"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення документа
            document_data = {
                "title": data["title"],
                "description": data.get("description", ""),
                "category": data["category"],  # contract, certificate, photo, other
                "file_url": data["file_url"],
                "file_name": data.get("file_name", ""),
                "file_size": data.get("file_size", 0),
                "file_type": data.get("file_type", ""),
                "tags": data.get("tags", []),
                "related_object_id": data.get("related_object_id"),
                "related_object_type": data.get("related_object_type"),
                "access_level": data.get("access_level", "private"),  # private, public, restricted
                "uploaded_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            document_id = await self.db.documents.create(document_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="document_uploaded",
                description=f"Завантажено документ: {data['title']}",
                metadata={"document_id": document_id}
            )
            
            return Response.success({
                "message": "Документ успішно завантажено",
                "document_id": document_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при завантаженні документа: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_document(self, document_id: str, request: Request) -> Dict[str, Any]:
        """
        Отримати документ за ID (потребує авторизації).
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
            
            document = await self.db.documents.find_one({"_id": document_id})
            
            if not document:
                raise AuthException(AuthErrorCode.DOCUMENT_NOT_FOUND)
            
            return Response.success({"document": document})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні документа: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_document(self, document_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити документ (потребує авторизації).
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
            
            # Перевірка існування документа
            document = await self.db.documents.find_one({"_id": document_id})
            if not document:
                raise AuthException(AuthErrorCode.DOCUMENT_NOT_FOUND)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            # Поля, які можна оновити
            updatable_fields = [
                "title", "description", "category", "tags", 
                "access_level", "related_object_id", "related_object_type"
            ]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            await self.db.documents.update({"_id": document_id}, update_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="document_updated",
                description=f"Оновлено документ: {document_id}",
                metadata={"document_id": document_id}
            )
            
            return Response.success({"message": "Документ успішно оновлено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні документа: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_document(self, document_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити документ (потребує авторизації).
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
            
            # Перевірка існування документа
            document = await self.db.documents.find_one({"_id": document_id})
            if not document:
                raise AuthException(AuthErrorCode.DOCUMENT_NOT_FOUND)
            
            await self.db.documents.delete({"_id": document_id})
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="document_deleted",
                description=f"Видалено документ: {document_id}",
                metadata={"document_id": document_id}
            )
            
            return Response.success({"message": "Документ успішно видалено"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні документа: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_document_templates(
        self,
        request: Request,
        category: Optional[str] = Query(None)
    ) -> Dict[str, Any]:
        """
        Отримати шаблони документів (потребує авторизації).
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
            filters = {"is_template": True}
            if category:
                filters["category"] = category
            
            templates = await self.db.document_templates.find(filters)
            
            return Response.success({"templates": templates})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні шаблонів документів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_document_template(self, request: Request) -> Dict[str, Any]:
        """
        Створити шаблон документа (потребує авторизації).
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
            required_fields = ["title", "category", "template_content"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення шаблона
            template_data = {
                "title": data["title"],
                "description": data.get("description", ""),
                "category": data["category"],
                "template_content": data["template_content"],
                "variables": data.get("variables", []),
                "is_template": True,
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            template_id = await self.db.document_templates.create(template_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="document_template_created",
                description=f"Створено шаблон документа: {data['title']}",
                metadata={"template_id": template_id}
            )
            
            return Response.success({
                "message": "Шаблон документа успішно створено",
                "template_id": template_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні шаблона документа: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def generate_document_from_template(self, template_id: str, request: Request) -> Dict[str, Any]:
        """
        Згенерувати документ з шаблона (потребує авторизації).
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
            
            # Перевірка існування шаблона
            template = await self.db.document_templates.find_one({"_id": template_id})
            if not template:
                raise AuthException(AuthErrorCode.TEMPLATE_NOT_FOUND)
            
            data = await request.json()
            
            # Генерація документа з шаблона
            template_content = template["template_content"]
            variables = data.get("variables", {})
            
            # Заміна змінних у шаблоні
            for key, value in variables.items():
                template_content = template_content.replace(f"{{{key}}}", str(value))
            
            # Створення документа
            document_data = {
                "title": data.get("title", f"Документ з шаблона: {template['title']}"),
                "description": data.get("description", ""),
                "category": template["category"],
                "content": template_content,
                "template_id": template_id,
                "generated_from_template": True,
                "related_object_id": data.get("related_object_id"),
                "related_object_type": data.get("related_object_type"),
                "access_level": data.get("access_level", "private"),
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            document_id = await self.db.documents.create(document_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="document_generated_from_template",
                description=f"Згенеровано документ з шаблона: {template_id}",
                metadata={"document_id": document_id, "template_id": template_id}
            )
            
            return Response.success({
                "message": "Документ успішно згенеровано з шаблона",
                "document_id": document_id
            })
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при генерації документа з шаблона: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 