from fastapi import Depends, HTTPException, status, Request
from typing import Dict, Any, Optional
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime, timedelta
import bcrypt
import secrets
import uuid
from api.jwt_handler import JWTHandler


class AdminAuthEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def login(self, request: Request) -> Dict[str, Any]:
        """
        Вхід адміністратора в систему.
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
            
            # Перевірка пароля
            if not bcrypt.checkpw(password.encode("utf-8"), admin["password"].encode("utf-8")):
                raise AuthException(AuthErrorCode.INVALID_CREDENTIALS)
            
            # Перевірка верифікації email
            if not admin.get("is_verified", False):
                return Response.error(
                    "Email не верифіковано. Перевірте вашу пошту для завершення верифікації.",
                    status_code=status.HTTP_403_FORBIDDEN
                )
            
            # Генерація токенів
            access_token = self.jwt_handler.create_admin_access_token(admin["_id"])
            refresh_token = self.jwt_handler.create_admin_refresh_token(admin["_id"])
            
            # Логування події
            event_logger = EventLogger(admin)
            await event_logger.log_custom_event(
                event_type="admin_login",
                description=f"Адміністратор увійшов в систему: {email}"
            )
            
            # Підготовка даних адміністратора для відповіді
            admin_data = {
                "id": admin["_id"],
                "email": admin["email"],
                "first_name": admin["first_name"],
                "last_name": admin["last_name"],
                "role": admin.get("role", "admin")
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
            admin = await self.db.admins.find_one({"_id": verification["user_id"]})
            if not admin:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            # Оновлення статусу адміністратора
            await self.db.admins.update({"_id": verification["user_id"]}, {"is_verified": True})
            
            # Видалення коду верифікації
            await self.db.verification_codes.delete({"code": code})
            
            # Логування події
            event_logger = EventLogger({"_id": verification["user_id"]})
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
            
            if not email:
                return Response.error("Email обов'язковий", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Перевірка існування адміністратора
            admin = await self.db.admins.find_one({"email": email})
            
            if not admin:
                raise AuthException(AuthErrorCode.EMAIL_NOT_FOUND)
            
            # Генерація коду відновлення
            reset_code = str(uuid.uuid4())
            
            # Збереження коду відновлення
            reset_data = {
                "user_id": admin["_id"],
                "code": reset_code,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=1),
                "email": email
            }
            await self.db.verification_codes.create(reset_data)
            
            # TODO: Відправка email з кодом відновлення
            
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
            admin = await self.db.admins.find_one({"_id": verification["user_id"]})
            if not admin:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
            # Хешування нового пароля
            hashed_password = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            
            # Оновлення пароля адміністратора
            await self.db.admins.update({"_id": verification["user_id"]}, {"password": hashed_password})
            
            # Видалення коду відновлення
            await self.db.verification_codes.delete({"code": code})
            
            # Логування події
            event_logger = EventLogger({"_id": verification["user_id"]})
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