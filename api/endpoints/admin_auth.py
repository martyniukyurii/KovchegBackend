from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database, CollectionHandler
from tools.event_logger import EventLogger
from tools.email_service import EmailService
from datetime import datetime, timedelta
import bcrypt
import secrets
from bson import ObjectId
import json
from api.jwt_handler import JWTHandler


# Клас для серіалізації ObjectId в JSON
class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)


class AdminAuthEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()
        self.email_service = EmailService()
        self.event_logger = EventLogger()
        # Додаємо колекцію admin_applications
        self.db.admin_applications = CollectionHandler(self.db, "admin_applications")
        # Додаємо колекцію training_programs
        self.db.training_programs = CollectionHandler(self.db, "training_programs")

    async def login(self, request: Request) -> Dict[str, Any]:
        """
        Вхід адміністратора в систему.
        
        Тіло запиту (JSON):
        {
            "email": "admin@example.com",       // обов'язково
            "password": "adminpassword"         // обов'язково
        }
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "admin": {
                    "id": "687619dcbc3697db0a23b3b7",
                    "email": "admin@example.com",
                    "first_name": "Адмін",
                    "last_name": "Петренко",
                    "role": "admin",
                    "is_verified": true
                },
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }
        """
        try:
            data = await request.json()
            email = data.get("email", "").lower().strip()
            password = data.get("password", "")
            
            if not email or not password:
                return Response.error("Email та пароль обов'язкові", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Пошук адміністратора
            admin = await self.db.admins.find_one({"email": email})
            
            if not admin:
                raise AuthException(AuthErrorCode.INVALID_CREDENTIALS)
            
            # Перевірка чи адмін має пароль (не тільки Telegram)
            if admin.get("password") is None:
                return Response.error(
                    "Цей акаунт створено через Telegram. Використовуйте вхід через Telegram.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Перевірка пароля
            if not bcrypt.checkpw(password.encode("utf-8"), admin["password"].encode("utf-8")):
                raise AuthException(AuthErrorCode.INVALID_CREDENTIALS)
            
            # Перевірка верифікації email (якщо email встановлено)
            if admin.get("email") and not admin.get("is_verified", False):
                return Response.error(
                    "Email не верифіковано. Перевірте вашу пошту для завершення верифікації.",
                    status_code=status.HTTP_403_FORBIDDEN
                )
            
            # Генерація токенів
            access_token = self.jwt_handler.create_access_token(str(admin["_id"]))
            refresh_token = self.jwt_handler.create_refresh_token(str(admin["_id"]))
            
            # Логування події
            event_logger = EventLogger(admin)
            await event_logger.log_custom_event(
                event_type="admin_login",
                description=f"Адміністратор увійшов в систему: {email}"
            )
            
            # Підготовка даних адміністратора для відповіді
            admin_data = {
                "id": str(admin["_id"]),
                "email": admin["email"],
                "first_name": admin["first_name"],
                "last_name": admin["last_name"],
                "role": admin.get("role", "admin"),
                "is_verified": admin.get("is_verified", False)
            }
            
            return Response.success({
                "admin": admin_data,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer"
            })
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при вході в систему: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def verify_email(self, request: Request) -> Dict[str, Any]:
        """
        Верифікація email адміністратора.
        """
        try:
            data = await request.json()
            code = data.get("code", "")
            
            if not code:
                return Response.error("Код верифікації не надано", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Пошук коду верифікації
            verification = await self.db.verification_codes.find_one({"code": code})
            
            if not verification:
                raise AuthException(AuthErrorCode.INVALID_VERIFICATION_CODE)
            
            # Перевірка терміну дії коду
            if verification["expires_at"] < datetime.utcnow():
                await self.db.verification_codes.delete({"code": code})
                raise AuthException(AuthErrorCode.INVALID_VERIFICATION_CODE)
            
            # Перевірка, що це адміністратор
            admin_id = verification.get("admin_id") or verification.get("user_id")
            admin = await self.db.admins.find_one({"_id": ObjectId(admin_id)})
            if not admin:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            # Оновлення статусу адміністратора
            await self.db.admins.update(
                {"_id": ObjectId(admin_id)}, 
                {"$set": {"is_verified": True, "updated_at": datetime.utcnow()}}
            )
            
            # Видалення коду верифікації
            await self.db.verification_codes.delete({"code": code})
            
            # Відправка привітального email
            if admin.get("email"):
                await self.email_service.send_welcome_email(
                    email=admin["email"],
                    user_name=f"{admin['first_name']} {admin['last_name']}",
                    language=admin.get("language_code", "uk")
                )
            
            # Логування події
            event_logger = EventLogger({"_id": admin_id})
            await event_logger.log_custom_event(
                event_type="admin_email_verified",
                description="Email адміністратора верифіковано"
            )
            
            return Response.success({"message": "Email успішно верифіковано"})
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при верифікації email: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def request_password_reset(self, request: Request) -> Dict[str, Any]:
        """
        Запит на відновлення пароля адміністратора.
        """
        try:
            data = await request.json()
            email = data.get("email", "").lower().strip()
            language = data.get("language", "uk")
            
            if not email:
                return Response.error("Email обов'язковий", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Перевірка існування адміністратора
            admin = await self.db.admins.find_one({"email": email})
            
            if not admin:
                raise AuthException(AuthErrorCode.EMAIL_NOT_FOUND)
            
            # Перевірка верифікації email
            if not admin.get("is_verified", False):
                return Response.error(
                    "Email не верифіковано. Спочатку підтвердіть свою електронну адресу.",
                    status_code=status.HTTP_403_FORBIDDEN
                )
            
            # Перевірка чи адмін має пароль (не тільки Telegram)
            if admin.get("password") is None:
                return Response.error(
                    "Цей акаунт створено через Telegram. Використовуйте вхід через Telegram.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Генерація 6-значного коду відновлення
            reset_code = str(secrets.randbelow(900000) + 100000)
            
            # Збереження коду відновлення
            reset_data = {
                "admin_id": admin["_id"],
                "code": reset_code,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=1),
                "email": email,
                "type": "admin_password_reset"
            }
            await self.db.verification_codes.create(reset_data)
            
            # Відправка email з кодом відновлення
            await self.email_service.send_password_reset_email(
                email=email,
                reset_code=reset_code,
                user_name=f"{admin['first_name']} {admin['last_name']}",
                language=admin.get("language_code", language)
            )
            
            # Логування події
            event_logger = EventLogger({"_id": admin["_id"]})
            await event_logger.log_custom_event(
                event_type="admin_password_reset_request",
                description="Адміністратор запросив відновлення пароля"
            )
            
            return Response.success({
                "message": "Інструкції з відновлення пароля надіслано на вашу електронну пошту"
            })
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при запиті відновлення пароля: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def confirm_password_reset(self, request: Request) -> Dict[str, Any]:
        """
        Підтвердження відновлення пароля адміністратора.
        """
        try:
            data = await request.json()
            code = data.get("code", "")
            new_password = data.get("new_password", "")
            
            if not code or not new_password:
                return Response.error("Код та новий пароль обов'язкові", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Пошук коду відновлення
            verification = await self.db.verification_codes.find_one({"code": code})
            
            if not verification:
                raise AuthException(AuthErrorCode.INVALID_VERIFICATION_CODE)
            
            # Перевірка терміну дії коду
            if verification["expires_at"] < datetime.utcnow():
                await self.db.verification_codes.delete({"code": code})
                raise AuthException(AuthErrorCode.INVALID_VERIFICATION_CODE)
            
            # Перевірка, що це адміністратор
            admin_id = verification.get("admin_id") or verification.get("user_id")
            admin = await self.db.admins.find_one({"_id": ObjectId(admin_id)})
            if not admin:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            # Хешування нового пароля
            hashed_password = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            
            # Оновлення пароля адміністратора
            await self.db.admins.update(
                {"_id": ObjectId(admin_id)}, 
                {"$set": {"password": hashed_password, "updated_at": datetime.utcnow()}}
            )
            
            # Видалення коду відновлення
            await self.db.verification_codes.delete({"code": code})
            
            # Логування події
            event_logger = EventLogger({"_id": admin_id})
            await event_logger.log_custom_event(
                event_type="admin_password_reset",
                description="Пароль адміністратора відновлено"
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
                message=f"Помилка при відновленні пароля: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def logout(self, request: Request) -> Dict[str, Any]:
        """
        Вихід адміністратора з системи.
        """
        try:
            # Отримання токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Невірний формат токена", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            
            # Додавання токена до чорного списку
            # TODO: Реалізувати чорний список токенів
            
            # Логування події
            # Отримання адміністратора з токена
            try:
                payload = self.jwt_handler.decode_token(token)
                admin_id = payload.get("sub")
                if admin_id:
                    event_logger = EventLogger({"_id": admin_id})
                    await event_logger.log_custom_event(
                        event_type="admin_logout",
                        description="Адміністратор вийшов із системи"
                    )
            except Exception:
                pass
            
            return Response.success({"message": "Успішний вихід з системи"})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при виході з системи: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 

    async def get_admins(
        self,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати список адмінів (доступно для всіх).
        """
        try:
            skip = (page - 1) * limit
            admins_cursor = await self.db.admins.find(
                {"role": "admin"}, # Повертаємо тільки адмінів
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Конвертуємо ObjectId в строку для JSON серіалізації
            admins = []
            for admin in admins_cursor:
                admin["_id"] = str(admin["_id"])
                for key, value in admin.items():
                    if isinstance(value, ObjectId):
                        admin[key] = str(value)
                    elif isinstance(value, datetime):
                        admin[key] = value.isoformat()
                admins.append(admin)
            
            # Підрахунок загальної кількості
            total = await self.db.admins.count_documents({"role": "admin"})
            
            return Response.success({
                "admins": admins,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні списку адмінів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_admin(self, admin_id: str) -> Dict[str, Any]:
        """
        Отримати інформацію про адміна (доступно для всіх).
        """
        try:
            try:
                admin = await self.db.admins.find_one({"_id": ObjectId(admin_id), "role": "admin"})
            except:
                admin = await self.db.admins.find_one({"_id": admin_id, "role": "admin"})
            if not admin:
                raise AuthException(AuthErrorCode.ADMIN_NOT_FOUND)
            admin["_id"] = str(admin["_id"])
            for key, value in admin.items():
                if isinstance(value, ObjectId):
                    admin[key] = str(value)
                elif isinstance(value, datetime):
                    admin[key] = value.isoformat()
            return Response.success({"admin": admin})
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні інформації про адміна: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def apply_for_admin(self, request: Request) -> Dict[str, Any]:
        """
        Подати заявку на роботу адміном (доступно для всіх).
        """
        try:
            data = await request.json()
            required_fields = ["first_name", "last_name", "email", "phone"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
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
            application_id = await self.db.admin_applications.create(application)
            await self.event_logger.log_custom_event(
                event_type="admin_application_submitted",
                description=f"Нова заявка на роботу адміном від {data['first_name']} {data['last_name']}",
                metadata={"application_id": application_id}
            )
            return Response.success({
                "message": "Заявка на роботу адміном успішно подана",
                "application_id": application_id
            })
        except Exception as e:
            return Response.error(
                message=f"Помилка при поданні заявки на роботу адміном: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_admin(self, request: Request) -> Dict[str, Any]:
        """
        Створити адміна (потребує авторизації адміністратора).
        """
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            data = await request.json()
            required_fields = ["first_name", "last_name", "email", "phone"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            admin_data = {
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "email": data["email"],
                "phone": data["phone"],
                "login": data["email"],
                "password": None,
                "role": "admin",
                "is_verified": True,
                "language_code": "uk",
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
            admin_id = await self.db.admins.create(admin_data)
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="admin_created",
                description=f"Створено адміна: {data['first_name']} {data['last_name']}",
                metadata={"admin_id": admin_id}
            )
            return Response.success({
                "message": "Адміна успішно створено",
                "admin_id": admin_id
            })
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні адміна: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_admin(self, admin_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити інформацію про адміна (потребує авторизації).
        """
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            try:
                admin = await self.db.admins.find_one({"_id": ObjectId(admin_id), "role": "admin"})
                filter_id = ObjectId(admin_id)
            except:
                admin = await self.db.admins.find_one({"_id": admin_id, "role": "admin"})
                filter_id = admin_id
            if not admin:
                raise AuthException(AuthErrorCode.ADMIN_NOT_FOUND)
            data = await request.json()
            update_data = {
                "updated_at": datetime.utcnow()
            }
            updatable_fields = ["bio", "experience", "specializations", "languages", "photo_url", "status"]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            await self.db.admins.update_one({"_id": filter_id, "role": "admin"}, update_data)
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="admin_updated",
                description=f"Оновлено інформацію про адміна: {admin_id}",
                metadata={"admin_id": admin_id}
            )
            return Response.success({"message": "Інформацію про адміна успішно оновлено"})
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні інформації про адміна: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_admin(self, admin_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити адміна (потребує авторизації адміністратора).
        """
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            try:
                admin = await self.db.admins.find_one({"_id": ObjectId(admin_id), "role": "admin"})
                filter_id = ObjectId(admin_id)
            except:
                admin = await self.db.admins.find_one({"_id": admin_id, "role": "admin"})
                filter_id = admin_id
            if not admin:
                raise AuthException(AuthErrorCode.ADMIN_NOT_FOUND)
            await self.db.admins.delete({"_id": filter_id, "role": "admin"})
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="admin_deleted",
                description=f"Видалено адміна: {admin_id}",
                metadata={"admin_id": admin_id}
            )
            return Response.success({"message": "Адміна успішно видалено"})
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні адміна: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_training_programs(
        self,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50)
    ) -> Dict[str, Any]:
        """
        Отримати програми підготовки адмінів.
        """
        try:
            skip = (page - 1) * limit
            
            # Перевірка наявності колекції
            if not hasattr(self.db, "training_programs"):
                # Якщо колекції немає, повертаємо пустий список
                return Response.success({
                    "programs": [],
                    "pagination": {
                        "page": page,
                        "limit": limit,
                        "total": 0,
                        "pages": 0
                    }
                })
            
            programs = await self.db.training_programs.find(
                {"status": "active"},
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            )
            
            # Конвертуємо ObjectId в строку для JSON серіалізації
            for program in programs:
                program["_id"] = str(program["_id"])
                for key, value in program.items():
                    if isinstance(value, ObjectId):
                        program[key] = str(value)
                    elif isinstance(value, datetime):
                        program[key] = value.isoformat()
            
            # Підрахунок загальної кількості
            total = await self.db.training_programs.count_documents({"status": "active"})
            
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
            # Перевірка наявності колекції
            if not hasattr(self.db, "training_programs"):
                return Response.error(
                    message="Програму підготовки не знайдено",
                    status_code=status.HTTP_404_NOT_FOUND,
                    details={"code": "TRAINING_PROGRAM_NOT_FOUND"}
                )
            
            # Конвертуємо строковий ID в ObjectId
            try:
                program = await self.db.training_programs.find_one({"_id": ObjectId(program_id)})
            except:
                program = await self.db.training_programs.find_one({"_id": program_id})
            
            if not program:
                raise AuthException(AuthErrorCode.TRAINING_PROGRAM_NOT_FOUND)
            
            # Конвертуємо ObjectId в строку для JSON серіалізації
            program["_id"] = str(program["_id"])
            for key, value in program.items():
                if isinstance(value, ObjectId):
                    program[key] = str(value)
                elif isinstance(value, datetime):
                    program[key] = value.isoformat()
            
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

    async def create_training_program(self, request: Request) -> Dict[str, Any]:
        """
        Створити програму підготовки адмінів (потребує авторизації адміністратора).
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
            required_fields = ["title", "description", "duration"]
            for field in required_fields:
                if not data.get(field):
                    return Response.error(f"Поле '{field}' є обов'язковим", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Створення програми підготовки
            program_data = {
                "title": data["title"],
                "description": data["description"],
                "duration": data["duration"],
                "modules": data.get("modules", []),
                "status": "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "created_by": user_id
            }
            
            program_id = await self.db.training_programs.create(program_data)
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="training_program_created",
                description=f"Створено програму підготовки: {data['title']}",
                metadata={"program_id": program_id}
            )
            
            return Response.success({
                "message": "Програму підготовки успішно створено",
                "program_id": program_id
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні програми підготовки: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def update_training_program(self, program_id: str, request: Request) -> Dict[str, Any]:
        """
        Оновити програму підготовки (потребує авторизації адміністратора).
        """
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            # Перевірка існування програми
            try:
                program = await self.db.training_programs.find_one({"_id": ObjectId(program_id)})
                filter_id = ObjectId(program_id)
            except:
                program = await self.db.training_programs.find_one({"_id": program_id})
                filter_id = program_id
            if not program:
                raise AuthException(AuthErrorCode.TRAINING_PROGRAM_NOT_FOUND)
            data = await request.json()
            update_data = {
                "updated_at": datetime.utcnow()
            }
            updatable_fields = ["title", "description", "duration", "modules", "status"]
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            await self.db.training_programs.update_one({"_id": filter_id}, update_data)
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="training_program_updated",
                description=f"Оновлено програму підготовки: {program_id}",
                metadata={"program_id": program_id}
            )
            return Response.success({"message": "Програму підготовки успішно оновлено"})
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при оновленні програми підготовки: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def delete_training_program(self, program_id: str, request: Request) -> Dict[str, Any]:
        """
        Видалити програму підготовки (потребує авторизації адміністратора).
        """
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            # Перевірка існування програми
            try:
                program = await self.db.training_programs.find_one({"_id": ObjectId(program_id)})
                filter_id = ObjectId(program_id)
            except:
                program = await self.db.training_programs.find_one({"_id": program_id})
                filter_id = program_id
            if not program:
                raise AuthException(AuthErrorCode.TRAINING_PROGRAM_NOT_FOUND)
            await self.db.training_programs.delete({"_id": filter_id})
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="training_program_deleted",
                description=f"Видалено програму підготовки: {program_id}",
                metadata={"program_id": program_id}
            )
            return Response.success({"message": "Програму підготовки успішно видалено"})
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при видаленні програми підготовки: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 