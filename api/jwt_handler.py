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


class JWTHandler:
    def __init__(self):
        self.config = Config()  # Отримуємо конфігурацію
        self.logger = Logger()  # Ініціалізуємо логер
        self.db = Database()
        self.algorithm = 'HS256'
        # Базовий секретний ключ з конфігурації
        self.base_secret_key = self.config.JWT_SECRET_KEY
        # Час життя токена (30 днів)
        self.access_token_expire_minutes = 30 * 24 * 60  # 30 днів у хвилинах

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

    def generate_token(self, user_id: str) -> str:
        """
        Генерує JWT-токен для користувача.
        
        Args:
            user_id: Ідентифікатор користувача
            
        Returns:
            str: JWT-токен
        """
        try:
            payload = {
                "sub": str(user_id),  # Переконуємось що user_id це строка
                "jti": str(uuid.uuid4()),  # Унікальний ідентифікатор токена
                "exp": datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes),
                "iat": datetime.utcnow()
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

    async def validate_token(self, token: str) -> TokenPayload:
        """
        Перевіряє токен та наявність користувача в базі.
        """
        try:
            # Спочатку декодуємо без перевірки підпису щоб отримати user_id
            unverified_payload = PyJWT.decode(token, options={"verify_signature": False})
            user_id = unverified_payload.get("sub")

            if not user_id:
                raise AuthException(AuthErrorCode.INVALID_TOKEN)

            try:
                object_id = ObjectId(user_id)
            except Exception:
                raise AuthException(AuthErrorCode.INVALID_TOKEN)

            # Перевірка існування користувача
            user = await self.db.users.find_one({"_id": object_id})
            if not user:
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

    async def get_current_user(self, token: str = Depends(OAuth2PasswordBearer(tokenUrl="/auth/login"))) -> str:
        try:
            payload = await self.validate_token(token)
            return payload.sub
        except AuthException as e:
            raise e
        except Exception as e:
            self.logger.error(f"Error in get_current_user: {str(e)}")
            raise AuthException(AuthErrorCode.INVALID_TOKEN)
    
    def create_access_token(self, user_id: str) -> str:
        """
        Створює access токен для користувача.
        """
        return self.generate_token(user_id)
    
    def create_refresh_token(self, user_id: str) -> str:
        """
        Створює refresh токен для користувача.
        """
        return self.generate_token(user_id)
    
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