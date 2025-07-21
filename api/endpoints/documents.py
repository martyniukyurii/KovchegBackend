from fastapi import Depends, HTTPException, status, Request, Query, UploadFile, File, Form
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from tools.google_drive_service import GoogleDriveService
from tools.docx_template_service import docx_template_service
from tools.logger import Logger
from datetime import datetime
from api.jwt_handler import JWTHandler
from bson import ObjectId
import mimetypes


class DocumentsEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()
        self.google_drive = GoogleDriveService()
        self.logger = Logger()

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
            
            # Конвертуємо ObjectId і datetime в рядки
            for doc in documents:
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])
                if "related_object_id" in doc and doc["related_object_id"]:
                    doc["related_object_id"] = str(doc["related_object_id"])
                # Конвертуємо datetime поля
                for field in ["created_at", "updated_at"]:
                    if field in doc and doc[field]:
                        doc[field] = doc[field].isoformat() if hasattr(doc[field], 'isoformat') else str(doc[field])
            
            # Підрахунок загальної кількості
            total = await self.db.documents.count_documents(filters)
            
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

    async def upload_document(
        self,
        file: UploadFile = File(...),
        title: str = Form(...),
        description: str = Form(""),
        category: str = Form(...),
        tags: str = Form(""),
        related_object_id: str = Form(None),
        related_object_type: str = Form(None),
        access_level: str = Form("private"),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Завантажити документ на Google Drive (потребує авторизації).
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
            
            # Валідація файлу
            if not file.filename:
                return Response.error("Файл не обрано", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Читаємо файл
            file_content = await file.read()
            file_size = len(file_content)
            
            # Валідація розміру файлу (максимум 100MB)
            if file_size > 100 * 1024 * 1024:
                return Response.error("Файл занадто великий (максимум 100MB)", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Визначаємо MIME тип
            mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
            
            # Завантажуємо файл на Google Drive
            drive_result = await self.google_drive.upload_file(
                file_content=file_content,
                filename=file.filename,
                mime_type=mime_type,
                category=category
            )
            
            if not drive_result:
                return Response.error("Google Drive сервіс недоступний. Перевірте OAuth авторизацію через /auth/google-drive/setup", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
            
            # Обробка тегів
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []
            
            # Створення документа в базі даних
            document_data = {
                "title": title,
                "description": description,
                "category": category,  # contract, certificate, photo, other
                "google_drive_file_id": drive_result["file_id"],
                "file_name": drive_result["filename"],
                "file_size": drive_result["size"],
                "file_type": drive_result["mime_type"],
                "web_view_link": drive_result["web_view_link"],
                "download_link": drive_result["download_link"],
                "tags": tags_list,
                "related_object_id": related_object_id,
                "related_object_type": related_object_type,
                "access_level": access_level,  # private, public, restricted
                "uploaded_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            document_id = await self.db.documents.create(document_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="document_uploaded",
                description=f"Завантажено документ: {title}",
                metadata={"document_id": document_id, "file_name": file.filename}
            )
            
            return Response.success({
                "message": "Документ успішно завантажено",
                "document_id": document_id,
                "google_drive_file_id": drive_result["file_id"],
                "web_view_link": drive_result["web_view_link"],
                "download_link": drive_result["download_link"]
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
            
            document = await self.db.documents.find_one({"_id": ObjectId(document_id)})
            
            if not document:
                raise AuthException(AuthErrorCode.DOCUMENT_NOT_FOUND)
            
            # Конвертуємо ObjectId і datetime в рядки
            if "_id" in document:
                document["_id"] = str(document["_id"])
            if "related_object_id" in document and document["related_object_id"]:
                document["related_object_id"] = str(document["related_object_id"])
            # Конвертуємо datetime поля
            for field in ["created_at", "updated_at"]:
                if field in document and document[field]:
                    document[field] = document[field].isoformat() if hasattr(document[field], 'isoformat') else str(document[field])
            
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
            document = await self.db.documents.find_one({"_id": ObjectId(document_id)})
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
            
            await self.db.documents.update({"_id": ObjectId(document_id)}, update_data)
            
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
            document = await self.db.documents.find_one({"_id": ObjectId(document_id)})
            if not document:
                raise AuthException(AuthErrorCode.DOCUMENT_NOT_FOUND)
            
            # Видаляємо файл з Google Drive якщо є file_id
            if document.get("google_drive_file_id"):
                delete_result = await self.google_drive.delete_file(document["google_drive_file_id"])
                if not delete_result:
                    self.logger.warning(f"Не вдалося видалити файл з Google Drive: {document['google_drive_file_id']}")
                    # Продовжуємо видалення з бази навіть якщо Google Drive файл не видалився
            
            await self.db.documents.delete({"_id": ObjectId(document_id)})
            
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
            filters = {}
            if category:
                filters["category"] = category
            
            templates = await self.db.document_templates.find(filters)
            
            # Конвертуємо ObjectId і datetime в рядки для кожного шаблона
            for template in templates:
                if "_id" in template:
                    template["_id"] = str(template["_id"])
                if "related_object_id" in template and template["related_object_id"]:
                    template["related_object_id"] = str(template["related_object_id"])
                # Конвертуємо datetime поля
                for field in ["created_at", "updated_at"]:
                    if field in template and template[field]:
                        template[field] = template[field].isoformat() if hasattr(template[field], 'isoformat') else str(template[field])
            
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
            template = await self.db.document_templates.find_one({"_id": ObjectId(template_id)})
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

    async def get_template(self, template_id: str, request: Request) -> Dict[str, Any]:
        """Отримати шаблон за ID"""
        try:
            # Авторизація
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            template = await self.db.document_templates.find_one({"_id": ObjectId(template_id)})
            if not template:
                return Response.error("Шаблон не знайдено", status_code=status.HTTP_404_NOT_FOUND)
            
            # Серіалізація
            if "_id" in template:
                template["_id"] = str(template["_id"])
            for field in ["created_at", "updated_at"]:
                if field in template and template[field]:
                    template[field] = template[field].isoformat() if hasattr(template[field], 'isoformat') else str(template[field])
            
            return Response.success({"template": template})
            
        except Exception as e:
            return Response.error(f"Помилка отримання шаблона: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    async def update_document_template(self, template_id: str, request: Request) -> Dict[str, Any]:
        """Оновити шаблон документа"""
        try:
            # Авторизація
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка існування
            template = await self.db.document_templates.find_one({"_id": ObjectId(template_id)})
            if not template:
                return Response.error("Шаблон не знайдено", status_code=status.HTTP_404_NOT_FOUND)
            
            data = await request.json()
            
            # Оновлення даних
            update_data = {
                "updated_at": datetime.utcnow()
            }
            
            if "title" in data:
                update_data["title"] = data["title"]
            if "description" in data:
                update_data["description"] = data["description"]
            if "category" in data:
                update_data["category"] = data["category"]
            if "template_content" in data:
                update_data["template_content"] = data["template_content"]
            if "variables" in data:
                update_data["variables"] = data["variables"]
            
            await self.db.document_templates.update({"_id": ObjectId(template_id)}, {"$set": update_data})
            
            return Response.success({"message": "Шаблон успішно оновлено"})
            
        except Exception as e:
            return Response.error(f"Помилка оновлення шаблона: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    async def delete_document_template(self, template_id: str, request: Request) -> Dict[str, Any]:
        """Видалити шаблон документа"""
        try:
            # Авторизація
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка існування
            template = await self.db.document_templates.find_one({"_id": ObjectId(template_id)})
            if not template:
                return Response.error("Шаблон не знайдено", status_code=status.HTTP_404_NOT_FOUND)
            
            await self.db.document_templates.delete({"_id": ObjectId(template_id)})
            
            return Response.success({"message": "Шаблон успішно видалено"})
            
        except Exception as e:
            return Response.error(f"Помилка видалення шаблона: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) 

    async def upload_document_template_from_file(self, request: Request, file: UploadFile = File(...), title: str = Form(...), description: str = Form(""), category: str = Form("contract")) -> Dict[str, Any]:
        """Завантажити .docx файл як шаблон з автоматичним парсингом змінних"""
        try:
            # Авторизація
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка типу файлу
            if not file.filename.endswith(('.docx',)):
                return Response.error("Підтримуються тільки .docx файли", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Читаємо файл
            file_content = await file.read()
            
            # Витягуємо змінні з .docx файлу через docxtpl
            extracted_variables = docx_template_service.extract_variables_from_docx(file_content)
            
            # Отримуємо превью шаблона
            template_preview = docx_template_service.get_template_preview(file_content)
            
            # Завантажуємо оригінальний файл на Google Drive
            if not self.google_drive.is_available():
                return Response.error("Google Drive сервіс недоступний. Перевірте OAuth авторизацію через /auth/google-drive/setup", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
            
            drive_result = await self.google_drive.upload_file(
                file_content=file_content,
                filename=file.filename,
                mime_type=file.content_type or "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                category="template"
            )
            
            if not drive_result:
                return Response.error("Помилка завантаження на Google Drive", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Створення шаблона в базі
            template_data = {
                "title": title,
                "description": description,
                "category": category,
                "template_content": f"DOCX шаблон: {file.filename}",
                "variables": extracted_variables,
                "template_type": "docx",  # Новий тип
                "template_stats": {
                    "variables_count": len(extracted_variables),
                    "paragraphs_count": template_preview.get("paragraphs_count", 0),
                    "tables_count": template_preview.get("tables_count", 0)
                },
                "original_file": {
                    "filename": file.filename,
                    "file_size": len(file_content),
                    "google_drive_file_id": drive_result["file_id"],
                    "web_view_link": drive_result["web_view_link"],
                    "download_link": drive_result["download_link"]
                },
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            template_id = await self.db.document_templates.create(template_data)
            
            return Response.success({
                "message": "DOCX шаблон успішно завантажено та проаналізовано",
                "template_id": template_id,
                "google_drive_file_id": drive_result["file_id"],
                "web_view_link": drive_result["web_view_link"],
                "extracted_variables": extracted_variables,
                "variables_count": len(extracted_variables),
                "template_stats": template_data["template_stats"],
                "preview_text": template_preview.get("preview_text", "")
            })
            
        except Exception as e:
            return Response.error(f"Помилка завантаження DOCX шаблона: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) 

    async def generate_docx_from_template(self, template_id: str, request: Request) -> Dict[str, Any]:
        """Згенерувати .docx документ з шаблона"""
        try:
            # Авторизація
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Перевірка існування шаблона
            template = await self.db.document_templates.find_one({"_id": ObjectId(template_id)})
            if not template:
                return Response.error("Шаблон не знайдено", status_code=status.HTTP_404_NOT_FOUND)
            
            # Перевіряємо чи це .docx шаблон
            if template.get("template_type") != "docx":
                return Response.error("Цей ендпоінт тільки для .docx шаблонів", status_code=status.HTTP_400_BAD_REQUEST)
            
            data = await request.json()
            variables = data.get("variables", {})
            
            # Завантажуємо оригінальний .docx файл з Google Drive
            original_file_id = template["original_file"]["google_drive_file_id"]
            template_content = await self.google_drive.download_file(original_file_id)
            
            if not template_content:
                return Response.error("Не вдалося завантажити оригінальний шаблон з Google Drive", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Валідуємо змінні
            validation_result = docx_template_service.validate_variables(template_content, variables)
            
            if not validation_result["is_valid"]:
                return Response.error(
                    f"Відсутні обов'язкові змінні: {validation_result['missing_variables']}", 
                    status_code=status.HTTP_400_BAD_REQUEST,
                    details=validation_result
                )
            
            # Генеруємо документ
            generated_content = docx_template_service.generate_document_from_template(template_content, variables)
            
            if not generated_content:
                return Response.error("Помилка генерації документа", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Завантажуємо згенерований документ на Google Drive
            generated_filename = f"{data.get('title', template['title'])}_generated.docx"
            
            drive_result = await self.google_drive.upload_file(
                file_content=generated_content,
                filename=generated_filename,
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                category="generated"
            )
            
            if not drive_result:
                return Response.error("Помилка завантаження згенерованого документа на Google Drive", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Зберігаємо інформацію про згенерований документ в базі
            document_data = {
                "title": data.get("title", f"Документ з шаблона: {template['title']}"),
                "description": data.get("description", ""),
                "category": template["category"],
                "document_type": "docx_generated",
                "template_id": template_id,
                "generated_from_template": True,
                "generation_variables": variables,
                "google_drive_file_id": drive_result["file_id"],
                "file_name": generated_filename,
                "file_size": drive_result["size"],
                "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "web_view_link": drive_result["web_view_link"],
                "download_link": drive_result["download_link"],
                "related_object_id": data.get("related_object_id"),
                "related_object_type": data.get("related_object_type"),
                "access_level": data.get("access_level", "private"),
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            document_id = await self.db.documents.create(document_data)
            
            return Response.success({
                "message": "DOCX документ успішно згенеровано з шаблона",
                "document_id": document_id,
                "google_drive_file_id": drive_result["file_id"],
                "web_view_link": drive_result["web_view_link"],
                "download_link": drive_result["download_link"],
                "filename": generated_filename,
                "used_variables": variables,
                "validation_result": validation_result
            })
            
        except Exception as e:
            return Response.error(f"Помилка генерації DOCX документа: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) 