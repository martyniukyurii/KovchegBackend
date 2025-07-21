from datetime import datetime, timedelta
from typing import Optional
import hmac
import hashlib
import jwt as PyJWT
import uuid
from bson import ObjectId  # Додаємо для роботи з MongoDB ID

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from tools.config import Config  # Імпортуємо конфіг для отримання секретного ключа
from tools.logger import Logger  # Імпортуємо логер для обробки помилок
from tools.database import Database  # Імпорт бази даних для перевірки користувача
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode


class TokenPayload(BaseModel):
    sub: str  # Стандартне поле для user_id
    jti: str  # Унікальний ідентифікатор токена (для запобігання replay-атак)
    exp: datetime
    token_type: Optional[str] = "access"  # access або refresh


class JWTHandler:
    def __init__(self):
        self.config = Config()  # Отримуємо конфігурацію
        self.logger = Logger()  # Ініціалізуємо логер
        self.db = Database()
        self.algorithm = 'HS256'
        # Базовий секретний ключ з конфігурації
        self.base_secret_key = self.config.JWT_SECRET_KEY
        # Час життя access токена (30 днів)
        self.access_token_expire_minutes = 30 * 24 * 60  # 30 днів у хвилинах
        # Час життя refresh токена (60 днів - більше ніж access)
        self.refresh_token_expire_minutes = 60 * 24 * 60  # 60 днів у хвилинах

    def _derive_key(self, user_id: str) -> str:
        """
        Повертає модифікований секретний ключ з використанням HMAC,
        який враховує user_id. Використовуємо HMAC з SHA256.
        """
        # Перетворюємо базовий секретний ключ та user_id в байти
        base_key_bytes = self.base_secret_key.encode('utf-8')
        user_id_bytes = user_id.encode('utf-8')
        # Обчислюємо HMAC, використовуючи user_id як повідомлення
        derived_key = hmac.new(
            key=base_key_bytes,
            msg=user_id_bytes,
            digestmod=hashlib.sha256
        ).hexdigest()
        return derived_key

    def generate_token(self, user_id: str, token_type: str = "access") -> str:
        """
        Генерує JWT-токен для користувача.
        
        Args:
            user_id: Ідентифікатор користувача
            token_type: Тип токена ("access" або "refresh")
            
        Returns:
            str: JWT-токен
        """
        try:
            # Визначаємо термін дії в залежності від типу токена
            if token_type == "refresh":
                expire_minutes = self.refresh_token_expire_minutes
            else:
                expire_minutes = self.access_token_expire_minutes
            
            payload = {
                "sub": str(user_id),  # Переконуємось що user_id це строка
                "jti": str(uuid.uuid4()),  # Унікальний ідентифікатор токена
                "exp": datetime.utcnow() + timedelta(minutes=expire_minutes),
                "iat": datetime.utcnow(),
                "token_type": token_type
            }
            
            signing_key = self._derive_key(str(user_id))
            token = PyJWT.encode(
                payload,
                signing_key,
                algorithm=self.algorithm
            )
            
            return token
        except Exception as e:
            self.logger.error(f"Token generation error: {str(e)}")
            raise AuthException(AuthErrorCode.TOKEN_GENERATION_ERROR)

    async def validate_token(self, token: str, expected_type: str = "access") -> TokenPayload:
        """
        Перевіряє токен та наявність користувача в базі.
        
        Args:
            token: JWT токен
            expected_type: Очікуваний тип токена ("access" або "refresh")
        """
        try:
            # Спочатку декодуємо без перевірки підпису щоб отримати user_id
            unverified_payload = PyJWT.decode(token, options={"verify_signature": False})
            user_id = unverified_payload.get("sub")
            token_type = unverified_payload.get("token_type", "access")

            if not user_id:
                raise AuthException(AuthErrorCode.INVALID_TOKEN)
            
            # Перевірка типу токена
            if token_type != expected_type:
                raise AuthException(AuthErrorCode.INVALID_TOKEN)

            try:
                object_id = ObjectId(user_id)
            except Exception:
                raise AuthException(AuthErrorCode.INVALID_TOKEN)

            # Перевірка існування користувача в обох колекціях
            user = await self.db.users.find_one({"_id": object_id})
            admin = await self.db.admins.find_one({"_id": object_id})
            
            if not user and not admin:
                raise AuthException(AuthErrorCode.USER_NOT_FOUND)

            # Отримуємо ключ підпису та перевіряємо токен
            signing_key = self._derive_key(str(user_id))
            decoded = PyJWT.decode(
                token, 
                signing_key, 
                algorithms=[self.algorithm],
                options={"require": ["exp", "sub"]}
            )
            return TokenPayload(**decoded)

        except AuthException:
            raise
        except Exception as e:
            self.logger.error(f"Unexpected validation error: {str(e)}")
            raise AuthException(AuthErrorCode.INVALID_TOKEN)

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """
        Оновлює access токен за допомогою refresh токена.
        
        Args:
            refresh_token: Refresh токен
            
        Returns:
            dict: Новий access та refresh токени
        """
        try:
            # Перевіряємо refresh токен
            payload = await self.validate_token(refresh_token, expected_type="refresh")
            user_id = payload.sub
            
            # Генеруємо нові токени
            new_access_token = self.generate_token(user_id, "access")
            new_refresh_token = self.generate_token(user_id, "refresh")
            
            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer"
            }
            
        except AuthException:
            raise
        except Exception as e:
            self.logger.error(f"Token refresh error: {str(e)}")
            raise AuthException(AuthErrorCode.TOKEN_GENERATION_ERROR)

    async def get_current_user(self, token: str = Depends(OAuth2PasswordBearer(tokenUrl="/auth/login"))) -> str:
        try:
            payload = await self.validate_token(token)
            return payload.sub
        except AuthException as e:
            raise e
        except Exception as e:
            self.logger.error(f"Error in get_current_user: {str(e)}")
            raise AuthException(AuthErrorCode.INVALID_TOKEN)
    
    async def get_current_user_with_role(self, token: str) -> dict:
        """
        Отримує поточного користувача та його роль.
        
        Returns:
            dict: {"user_id": str, "user_type": str, "role": str}
        """
        try:
            payload = await self.validate_token(token)
            user_id = payload.sub
            
            # Спочатку шукаємо в адмінах
            admin = await self.db.admins.find_one({"_id": ObjectId(user_id)})
            if admin:
                return {
                    "user_id": user_id,
                    "user_type": "admin",
                    "role": admin.get("role", "admin"),
                    "user_data": admin
                }
            
            # Якщо не знайшли в адмінах, шукаємо в користувачах
            user = await self.db.users.find_one({"_id": ObjectId(user_id)})
            if user:
                return {
                    "user_id": user_id,
                    "user_type": user.get("user_type", "client"),
                    "role": "client",
                    "user_data": user
                }
            
            # Якщо не знайшли ніде - це реальна помилка
            raise AuthException(AuthErrorCode.USER_NOT_FOUND)
            
        except AuthException:
            raise
        except Exception as e:
            self.logger.error(f"Error in get_current_user_with_role: {str(e)}")
            raise AuthException(AuthErrorCode.INVALID_TOKEN)
    
    async def require_admin_role(self, token: str) -> dict:
        """
        Перевіряє що користувач є адміном.
        
        Returns:
            dict: Дані адміністратора
        """
        user_info = await self.get_current_user_with_role(token)
        
        if user_info["user_type"] != "admin":
            raise AuthException(AuthErrorCode.INSUFFICIENT_PERMISSIONS)
        
        return user_info
    
    def create_access_token(self, user_id: str) -> str:
        """
        Створює access токен для користувача.
        """
        return self.generate_token(user_id, "access")
    
    def create_refresh_token(self, user_id: str) -> str:
        """
        Створює refresh токен для користувача.
        """
        return self.generate_token(user_id, "refresh")
    
    def decode_token(self, token: str) -> dict:
        """
        Декодує токен без перевірки в базі даних.
        """
        try:
            # Спочатку декодуємо без перевірки підпису щоб отримати user_id
            unverified_payload = PyJWT.decode(token, options={"verify_signature": False})
            user_id = unverified_payload.get("sub")

            if not user_id:
                raise AuthException(AuthErrorCode.INVALID_TOKEN)

            # Отримуємо ключ підпису та перевіряємо токен
            signing_key = self._derive_key(str(user_id))
            decoded = PyJWT.decode(
                token, 
                signing_key, 
                algorithms=[self.algorithm],
                options={"require": ["exp", "sub"]}
            )
            return decoded

        except Exception as e:
            self.logger.error(f"Token decode error: {str(e)}")
            raise AuthException(AuthErrorCode.INVALID_TOKEN)