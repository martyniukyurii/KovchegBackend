from fastapi import Depends, HTTPException, status, Request
from typing import Dict, Any, Optional
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from tools.email_service import EmailService
from tools.oauth2_service import OAuth2Service
from datetime import datetime, timedelta
import bcrypt
import secrets
import uuid
from bson import ObjectId
from api.jwt_handler import JWTHandler


class AuthEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()
        self.email_service = EmailService()
        self.oauth2_service = OAuth2Service()

    async def register(self, request: Request) -> Dict[str, Any]:
        """
        Реєстрація нового користувача.
        
        Параметри:
        - email: обов'язковий
        - password: обов'язковий
        - first_name: обов'язковий
        - last_name: обов'язковий
        - phone: опціональний
        - language: опціональний (uk, ru, en), за замовчуванням uk
        """
        try:
            data = await request.json()
            email = data.get("email", "").lower().strip()
            password = data.get("password", "")
            first_name = data.get("first_name", "")
            last_name = data.get("last_name", "")
            phone = data.get("phone", "")
            language = data.get("language", "uk")  # Мова для неавторизованого користувача
            
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
            verification_code = str(secrets.randbelow(900000) + 100000)
            
            # Створення нового користувача
            user_data = {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
                "login": email,  # За замовчуванням логін = email
                "password": hashed_password,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "language_code": language,
                "is_verified": False,
                "user_type": "client",  # client, agent, admin
                "favorites": [],
                "search_history": [],
                "notifications_settings": {
                    "telegram": True,
                    "email": True
                },
                # Клієнтські поля
                "client_status": "active",  # active, inactive, lead
                "assigned_agent_id": None,
                "client_interests": [],
                "client_budget": {},
                "client_preferred_locations": [],
                "client_notes": "",
                "client_source": "self_registered",
                "client_preferences": {
                    "property_type": [],
                    "price_range": {},
                    "location": [],
                    "features": []
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
            
            # Відправка email з кодом верифікації
            await self.email_service.send_verification_email(
                email=email,
                verification_code=verification_code,
                user_name=f"{first_name} {last_name}",
                language=language
            )
            
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
            await self.db.users.update({"_id": ObjectId(verification["user_id"])}, {"$set": {"is_verified": True}})
            
            # Видалення коду верифікації
            await self.db.verification_codes.delete({"code": code})
            
            # Відправка привітального email
            user = await self.db.users.find_one({"_id": ObjectId(verification["user_id"])})
            if user:
                await self.email_service.send_welcome_email(
                    email=user["email"],
                    user_name=f"{user['first_name']} {user['last_name']}",
                    language=user.get("language_code", "uk")
                )
            
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
            
            # Перевірка чи користувач має пароль (не OAuth2)
            if user.get("password") is None:
                return Response.error(
                    "Цей акаунт створено через соціальну мережу. Використовуйте вхід через Google або Apple.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
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
                "id": str(user["_id"]),
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
        Вхід користувача через OAuth2 (Google, Apple).
        
        Параметри:
        - provider: обов'язковий (google, apple)
        - token: обов'язковий (для прямого токена) або code + redirect_uri (для коду авторизації)
        - code: код авторизації (альтернатива токену)
        - redirect_uri: URI перенаправлення (потрібен для коду)
        - language: опціональний (uk, ru, en), за замовчуванням uk
        """
        try:
            data = await request.json()
            provider = data.get("provider", "")
            token = data.get("token", "")
            code = data.get("code", "")
            redirect_uri = data.get("redirect_uri", "")
            language = data.get("language", "uk")  # Мова для неавторизованого користувача
            
            if not provider:
                return Response.error("Провайдер обов'язковий", status_code=status.HTTP_400_BAD_REQUEST)
            
            if not token and not code:
                return Response.error("Токен або код авторизації обов'язкові", status_code=status.HTTP_400_BAD_REQUEST)
            
            if code and not redirect_uri:
                return Response.error("Для коду авторизації потрібен redirect_uri", status_code=status.HTTP_400_BAD_REQUEST)
            
            if provider not in ["google", "apple"]:
                return Response.error("Непідтримуваний провайдер", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Якщо передано код, спочатку обміняємо його на токен
            if code and provider == "google":
                token = await self.oauth2_service.exchange_google_code_for_token(code, redirect_uri)
                if not token:
                    return Response.error("Невірний код авторизації", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Верифікація токена через відповідний сервіс
            oauth_user_info = None
            if provider == "google":
                oauth_user_info = await self.oauth2_service.verify_google_token(token)
            elif provider == "apple":
                oauth_user_info = await self.oauth2_service.verify_apple_token(token)
            
            if not oauth_user_info:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Пошук користувача за email
            user = await self.db.users.find_one({"email": oauth_user_info["email"]})
            
            if not user:
                # Створення нового користувача тільки якщо його немає
                user_data = {
                    "first_name": oauth_user_info["first_name"],
                    "last_name": oauth_user_info["last_name"],
                    "email": oauth_user_info["email"],
                    "phone": "",
                    "login": oauth_user_info["email"],
                    "password": None,  # OAuth2 користувачі не мають пароля
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "language_code": language,
                    "is_verified": True,  # OAuth2 користувачі автоматично верифіковані
                    "user_type": "client",
                    "oauth2_info": {
                        "provider": provider,
                        "provider_id": oauth_user_info["provider_id"],
                        "access_token": token,
                        "picture": oauth_user_info.get("picture", "")
                    },
                    "favorites": [],
                    "search_history": [],
                    "notifications_settings": {
                        "telegram": True,
                        "email": True
                    },
                    # Клієнтські поля
                    "client_status": "active",
                    "assigned_agent_id": None,
                    "client_interests": [],
                    "client_budget": {},
                    "client_preferred_locations": [],
                    "client_notes": "",
                    "client_source": f"oauth2_{provider}",
                    "client_preferences": {
                        "property_type": [],
                        "price_range": {},
                        "location": [],
                        "features": []
                    }
                }
                
                user_id = await self.db.users.create(user_data)
                user = await self.db.users.find_one({"_id": user_id})
            else:
                # Користувач вже існує - оновлюємо OAuth2 інформацію та верифікуємо
                update_data = {
                    "oauth2_info": {
                        "provider": provider,
                        "provider_id": oauth_user_info["provider_id"],
                        "access_token": token,
                        "picture": oauth_user_info.get("picture", "")
                    },
                    "is_verified": True,  # OAuth2 користувачі автоматично верифіковані
                    "updated_at": datetime.utcnow()
                }
                
                # Якщо це перший OAuth2 логін для цього користувача, оновлюємо фото
                if oauth_user_info.get("picture"):
                    update_data["oauth2_info"]["picture"] = oauth_user_info["picture"]
                
                await self.db.users.update(
                    {"_id": ObjectId(user["_id"])},
                    {"$set": update_data}
                )
                
                # Оновлюємо дані користувача для відповіді
                user.update(update_data)
            
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
                "id": str(user["_id"]),
                "email": user["email"],
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "phone": user.get("phone", ""),
                "is_verified": user.get("is_verified", False),
                "picture": user.get("oauth2_info", {}).get("picture", "")
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
        
        Параметри:
        - email: обов'язковий
        - language: опціональний (uk, ru, en), за замовчуванням uk
        """
        try:
            data = await request.json()
            email = data.get("email", "").lower().strip()
            language = data.get("language", "uk")  # Мова для неавторизованого користувача
            
            if not email:
                return Response.error("Email обов'язковий", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Перевірка існування користувача
            user = await self.db.users.find_one({"email": email})
            
            if not user:
                raise AuthException(AuthErrorCode.EMAIL_NOT_FOUND)
            
            # Перевірка верифікації email
            if not user.get("is_verified", False):
                return Response.error(
                    "Email не верифіковано. Спочатку підтвердіть свою електронну адресу.",
                    status_code=status.HTTP_403_FORBIDDEN
                )
            
            # Перевірка чи користувач має пароль (не OAuth2)
            if user.get("password") is None:
                return Response.error(
                    "Цей акаунт створено через соціальну мережу. Використовуйте вхід через Google або Apple.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Генерація коду відновлення
            reset_code = str(secrets.randbelow(900000) + 100000)
            
            # Збереження коду відновлення
            reset_data = {
                "user_id": user["_id"],
                "code": reset_code,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=1),
                "email": email
            }
            await self.db.verification_codes.create(reset_data)
            
            # Відправка email з кодом відновлення
            await self.email_service.send_password_reset_email(
                email=email,
                reset_code=reset_code,
                user_name=f"{user['first_name']} {user['last_name']}",
                language=user.get("language_code", language)  # Якщо користувач знайдений, використовуємо його мову
            )
            
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
            await self.db.users.update({"_id": ObjectId(verification["user_id"])}, {"password": hashed_password})
            
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
    
    async def get_oauth2_urls(self, request: Request) -> Dict[str, Any]:
        """
        Отримання URL для OAuth2 авторизації.
        """
        try:
            data = await request.json()
            redirect_uri = data.get("redirect_uri", "")
            state = data.get("state", "")
            
            if not redirect_uri:
                return Response.error("redirect_uri обов'язковий", status_code=status.HTTP_400_BAD_REQUEST)
            
            urls = {}
            
            # Google OAuth2 URL
            if self.oauth2_service.google_client_id:
                urls["google"] = self.oauth2_service.get_google_auth_url(redirect_uri, state)
            
            # Apple OAuth2 URL
            if self.oauth2_service.apple_client_id:
                urls["apple"] = self.oauth2_service.get_apple_auth_url(redirect_uri, state)
            
            return Response.success({
                "oauth2_urls": urls,
                "redirect_uri": redirect_uri,
                "state": state
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні OAuth2 URLs: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 