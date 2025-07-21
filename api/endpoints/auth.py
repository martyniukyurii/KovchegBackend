from fastapi import Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from typing import Dict, Any, Optional
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from tools.email_service import EmailService
# OAuth2Service видалено - не використовується для Google Drive
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

    async def register(self, request: Request) -> Dict[str, Any]:
        """
        Реєстрація нового користувача.
        
        Тіло запиту (JSON):
        {
            "email": "user@example.com",        // обов'язково, унікальний
            "password": "securepass123",        // обов'язково, мін. 6 символів
            "first_name": "Іван",               // обов'язково
            "last_name": "Петренко",            // обов'язково
            "phone": "+380501234567",           // опціонально
            "language": "uk"                    // опціонально (uk, ru, en), за замовчуванням uk
        }
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "message": "Користувач успішно зареєстрований. Перевірте email для верифікації."
            },
            "status_code": 201
        }
        
        Після реєстрації на email приходить код верифікації.
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
                "user_type": "client",  # client, admin, admin
                "favorites": [],
                "search_history": [],
                "notifications_settings": {
                    "telegram": True,
                    "email": True
                },
                # Клієнтські поля
                "client_status": "active",  # active, inactive, lead
                "assigned_admin_id": None,
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
        
        Тіло запиту (JSON):
        {
            "code": "123456"        // 6-значний код з email
        }
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "message": "Email успішно верифіковано"
            }
        }
        
        Після верифікації користувач може авторизуватись.
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
        
        Тіло запиту (JSON):
        {
            "email": "user@example.com",        // обов'язково
            "password": "userpassword"          // обов'язково
        }
        
        Приклад відповіді:
        {
            "status": "success",
            "data": {
                "user": {
                    "id": "687619cebc3697db0a23b3b3",
                    "email": "user@example.com",
                    "first_name": "Іван",
                    "last_name": "Петренко",
                    "phone": "+380501234567",
                    "is_verified": true
                },
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }
        
        Використовуйте access_token в заголовку Authorization: Bearer <token>
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
                return Response.error("Google OAuth не налаштований", status_code=status.HTTP_501_NOT_IMPLEMENTED)
            
            # Верифікація токена через відповідний сервіс
            oauth_user_info = None
            if provider == "google":
                return Response.error("Google OAuth не налаштований", status_code=status.HTTP_501_NOT_IMPLEMENTED)
            elif provider == "apple":
                return Response.error("Apple OAuth не налаштований", status_code=status.HTTP_501_NOT_IMPLEMENTED)
            
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
                    "assigned_admin_id": None,
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

    async def refresh_token(self, request: Request) -> Dict[str, Any]:
        """Оновлення JWT токена"""
        try:
            refresh_token = request.headers.get("Refresh-Token")
            if not refresh_token:
                return Response.error("Refresh token обов'язковий", status_code=status.HTTP_400_BAD_REQUEST)

            payload = self.jwt_handler.decode_token(refresh_token)
            if payload.get("token_type") != "refresh":
                return Response.error("Неправильний тип токена", status_code=status.HTTP_401_UNAUTHORIZED)

            user_id = payload.get("sub")
            user = await self.db.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return Response.error("Користувач не знайдений", status_code=status.HTTP_404_NOT_FOUND)

            # Генеруємо новий access token
            access_token = self.jwt_handler.create_access_token(user_id)

            return Response.success({
                "access_token": access_token,
                "token_type": "bearer"
            })

        except Exception as e:
            return Response.error(f"Помилка оновлення токена: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            
            # Google та Apple OAuth не налаштований
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

    async def get_google_drive_auth_url(self) -> Dict[str, Any]:
        """Отримати URL для OAuth авторизації Google Drive"""
        try:
            from google_auth_oauthlib.flow import Flow
            import os
            
            # Шлях до credentials файлу
            credentials_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'google api kovcheg test.json')
            
            if not os.path.exists(credentials_path):
                return Response.error("OAuth credentials файл не знайдено", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Створюємо OAuth flow
            flow = Flow.from_client_secrets_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/drive'],
                redirect_uri='http://localhost:8002/auth/google-drive/callback-web'
            )
            
            # Отримуємо authorization URL
            auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')
            
            # Зберігаємо state для перевірки
            # В production використовуйте Redis або базу даних
            self._oauth_state = state
            
            return Response.success({
                "auth_url": auth_url,
                "state": state
            })
            
        except Exception as e:
            return Response.error(f"Помилка створення OAuth URL: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    async def handle_google_drive_callback(self, request: Request) -> Dict[str, Any]:
        """Обробка callback від Google OAuth"""
        try:
            from google_auth_oauthlib.flow import Flow
            import os
            
            data = await request.json()
            auth_code = data.get('code')
            
            if not auth_code:
                return Response.error("Код авторизації не надано", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Шлях до credentials файлу
            credentials_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'google api kovcheg test.json')
            token_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'token.json')
            
            # Створюємо OAuth flow
            flow = Flow.from_client_secrets_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/drive'],
                redirect_uri='http://localhost:8002/auth/google-drive/callback-web'
            )
            
            # Обмінюємо код на токени
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            
            # Зберігаємо токени
            with open(token_path, 'w') as token_file:
                token_file.write(creds.to_json())
            
            return Response.success({
                "message": "Google Drive успішно підключено!",
                "token_saved": True
            })
            
        except Exception as e:
            return Response.error(f"Помилка OAuth callback: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    async def handle_google_drive_callback_web(self, request: Request) -> Dict[str, Any]:
        """Обробка GET callback від Google OAuth (для веб-авторизації)"""
        try:
            from google_auth_oauthlib.flow import Flow
            from fastapi.responses import HTMLResponse
            import os
            
            # Отримуємо параметри з URL
            code = request.query_params.get('code')
            state = request.query_params.get('state')
            error = request.query_params.get('error')
            
            if error:
                return HTMLResponse(f"""
                <html><body>
                <h1>❌ Помилка авторизації</h1>
                <p>Помилка: {error}</p>
                <p><a href="/static/oauth_setup.html">Спробувати знову</a></p>
                </body></html>
                """)
            
            if not code:
                return HTMLResponse("""
                <html><body>
                <h1>❌ Не отримано код авторизації</h1>
                <p><a href="/static/oauth_setup.html">Спробувати знову</a></p>
                </body></html>
                """)
            
            # Шлях до credentials файлу
            credentials_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'google api kovcheg test.json')
            token_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'token.json')
            
            # Створюємо OAuth flow
            flow = Flow.from_client_secrets_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/drive'],
                redirect_uri='http://localhost:8002/auth/google-drive/callback-web'
            )
            
            # Обмінюємо код на токени
            flow.fetch_token(code=code)
            creds = flow.credentials
            
            # Зберігаємо токени
            with open(token_path, 'w') as token_file:
                token_file.write(creds.to_json())
            
            return HTMLResponse("""
            <html><body style='font-family: Arial; margin: 50px; text-align: center;'>
            <h1>🎉 Google Drive успішно підключено!</h1>
            <p>Тепер ви можете завантажувати документи на ваш особистий Google Drive.</p>
            <p><a href="/static/oauth_setup.html" style='color: #007bff;'>Повернутися до налаштувань</a></p>
            <script>
                // Автоматично закриваємо вікно через 3 секунди
                setTimeout(() => {
                    window.close();
                }, 3000);
            </script>
            </body></html>
            """)
            
        except Exception as e:
            return HTMLResponse(f"""
            <html><body style='font-family: Arial; margin: 50px; text-align: center;'>
            <h1>❌ Помилка OAuth callback</h1>
            <p>Деталі: {str(e)}</p>
            <p><a href="/static/oauth_setup.html">Спробувати знову</a></p>
            </body></html>
            """) 