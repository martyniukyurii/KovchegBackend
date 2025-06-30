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


class AuthEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def register(self, request: Request) -> Dict[str, Any]:
        """
        Реєстрація нового користувача.
        """
        try:
            data = await request.json()
            email = data.get("email", "").lower().strip()
            password = data.get("password", "")
            first_name = data.get("first_name", "")
            last_name = data.get("last_name", "")
            phone = data.get("phone", "")
            
            # Перевірка наявності обов'язкових полів
            if not email or not password or not first_name or not last_name:
                return Response.error("Не всі обов'язкові поля заповнені", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Перевірка, чи існує користувач з таким email
            existing_user = await self.db.users.find_one({"email": email})
            if existing_user:
                raise AuthException(AuthErrorCode.EMAIL_ALREADY_REGISTERED)
            
            # Хешування пароля
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # Створення коду верифікації
            verification_code = str(uuid.uuid4())
            
            # Створення нового користувача
            user_data = {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
                "login": email,  # За замовчуванням логін = email
                "password": hashed_password,
                "created_at": datetime.utcnow(),
                "language_code": "uk",
                "is_verified": False,
                "favorites": [],
                "search_history": [],
                "notifications_settings": {
                    "telegram": True,
                    "email": True
                }
            }
            
            user_id = await self.db.users.create(user_data)
            
            # Збереження коду верифікації
            verification_data = {
                "user_id": user_id,
                "code": verification_code,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=24),
                "email": email
            }
            await self.db.verification_codes.create(verification_data)
            
            # TODO: Відправка email з кодом верифікації
            
            # Логування події
            event_logger = EventLogger()
            await event_logger.log_custom_event(
                event_type="user_registered",
                description=f"Користувач зареєстрований: {email}",
                metadata={"user_id": user_id}
            )
            
            return Response.success(
                {"message": "Користувач успішно зареєстрований. Перевірте email для верифікації."},
                status_code=status.HTTP_201_CREATED
            )
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при реєстрації: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def verify_email(self, request: Request) -> Dict[str, Any]:
        """
        Верифікація email користувача.
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
            
            # Оновлення статусу користувача
            await self.db.users.update({"_id": verification["user_id"]}, {"is_verified": True})
            
            # Видалення коду верифікації
            await self.db.verification_codes.delete({"code": code})
            
            # Логування події
            event_logger = EventLogger({"_id": verification["user_id"]})
            await event_logger.log_custom_event(
                event_type="email_verified",
                description="Email користувача верифіковано"
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

    async def login(self, request: Request) -> Dict[str, Any]:
        """
        Вхід користувача в систему.
        """
        try:
            data = await request.json()
            email = data.get("email", "").lower().strip()
            password = data.get("password", "")
            
            if not email or not password:
                return Response.error("Email та пароль обов'язкові", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Пошук користувача
            user = await self.db.users.find_one({"email": email})
            
            if not user:
                raise AuthException(AuthErrorCode.INVALID_CREDENTIALS)
            
            # Перевірка пароля
            if not bcrypt.checkpw(password.encode('utf-8'), user["password"].encode('utf-8')):
                raise AuthException(AuthErrorCode.INVALID_CREDENTIALS)
            
            # Перевірка верифікації email
            if not user.get("is_verified", False):
                return Response.error(
                    "Email не верифіковано. Перевірте вашу пошту для завершення реєстрації.",
                    status_code=status.HTTP_403_FORBIDDEN
                )
            
            # Генерація токенів
            access_token = self.jwt_handler.create_access_token(user["_id"])
            refresh_token = self.jwt_handler.create_refresh_token(user["_id"])
            
            # Логування події
            event_logger = EventLogger(user)
            await event_logger.log_login_success()
            
            # Підготовка даних користувача для відповіді
            user_data = {
                "id": user["_id"],
                "email": user["email"],
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "phone": user.get("phone", ""),
                "is_verified": user.get("is_verified", False)
            }
            
            return Response.success({
                "user": user_data,
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

    async def login_oauth2(self, request: Request) -> Dict[str, Any]:
        """
        Вхід користувача через OAuth2 (Gmail, Apple).
        """
        try:
            data = await request.json()
            provider = data.get("provider", "")
            token = data.get("token", "")
            
            if not provider or not token:
                return Response.error("Провайдер та токен обов'язкові", status_code=status.HTTP_400_BAD_REQUEST)
            
            if provider not in ["gmail", "apple"]:
                return Response.error("Непідтримуваний провайдер", status_code=status.HTTP_400_BAD_REQUEST)
            
            # TODO: Реалізувати валідацію OAuth2 токенів
            # Тут буде код для перевірки токена через API провайдера
            # і отримання даних користувача
            
            # Заглушка для демонстрації
            oauth_user_info = {
                "email": "user@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "provider_id": "123456789"
            }
            
            # Пошук користувача за email або створення нового
            user = await self.db.users.find_one({"email": oauth_user_info["email"]})
            
            if not user:
                # Створення нового користувача
                user_data = {
                    "first_name": oauth_user_info["first_name"],
                    "last_name": oauth_user_info["last_name"],
                    "email": oauth_user_info["email"],
                    "login": oauth_user_info["email"],
                    "created_at": datetime.utcnow(),
                    "language_code": "uk",
                    "is_verified": True,  # OAuth2 користувачі автоматично верифіковані
                    "oauth2_info": {
                        "provider": provider,
                        "provider_id": oauth_user_info["provider_id"],
                        "access_token": token
                    },
                    "favorites": [],
                    "search_history": [],
                    "notifications_settings": {
                        "telegram": True,
                        "email": True
                    }
                }
                
                user_id = await self.db.users.create(user_data)
                user = await self.db.users.find_one({"_id": user_id})
            else:
                # Оновлення OAuth2 інформації
                await self.db.users.update(
                    {"_id": user["_id"]},
                    {
                        "oauth2_info": {
                            "provider": provider,
                            "provider_id": oauth_user_info["provider_id"],
                            "access_token": token
                        }
                    }
                )
            
            # Генерація токенів
            access_token = self.jwt_handler.create_access_token(user["_id"])
            refresh_token = self.jwt_handler.create_refresh_token(user["_id"])
            
            # Логування події
            event_logger = EventLogger(user)
            await event_logger.log_custom_event(
                event_type="oauth2_login",
                description=f"Користувач увійшов через {provider}"
            )
            
            # Підготовка даних користувача для відповіді
            user_data = {
                "id": user["_id"],
                "email": user["email"],
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "is_verified": user.get("is_verified", False)
            }
            
            return Response.success({
                "user": user_data,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer"
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при вході через OAuth2: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def request_password_reset(self, request: Request) -> Dict[str, Any]:
        """
        Запит на відновлення пароля.
        """
        try:
            data = await request.json()
            email = data.get("email", "").lower().strip()
            
            if not email:
                return Response.error("Email обов'язковий", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Перевірка існування користувача
            user = await self.db.users.find_one({"email": email})
            
            if not user:
                raise AuthException(AuthErrorCode.EMAIL_NOT_FOUND)
            
            # Генерація коду відновлення
            reset_code = str(uuid.uuid4())
            
            # Збереження коду відновлення
            reset_data = {
                "user_id": user["_id"],
                "code": reset_code,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=1),
                "email": email
            }
            await self.db.verification_codes.create(reset_data)
            
            # TODO: Відправка email з кодом відновлення
            
            # Логування події
            event_logger = EventLogger({"_id": user["_id"]})
            await event_logger.log_password_change_request()
            
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
        Підтвердження відновлення пароля.
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
            
            # Хешування нового пароля
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # Оновлення пароля користувача
            await self.db.users.update({"_id": verification["user_id"]}, {"password": hashed_password})
            
            # Видалення коду відновлення
            await self.db.verification_codes.delete({"code": code})
            
            # Логування події
            event_logger = EventLogger({"_id": verification["user_id"]})
            await event_logger.log_custom_event(
                event_type="password_reset",
                description="Пароль користувача відновлено"
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
        Вихід користувача з системи.
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
            # Отримання користувача з токена
            try:
                payload = self.jwt_handler.decode_token(token)
                user_id = payload.get("sub")
                if user_id:
                    event_logger = EventLogger({"_id": user_id})
                    await event_logger.log_logout()
            except Exception:
                pass
            
            return Response.success({"message": "Успішний вихід з системи"})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при виході з системи: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 