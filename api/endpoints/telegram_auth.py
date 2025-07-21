import os
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any
from fastapi import Request, status
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from api.jwt_handler import JWTHandler
from dotenv import load_dotenv

load_dotenv()

class TelegramAuthEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

        # Власники CRM (з .env)
        owner_chat_ids_str = os.getenv('OWNER_CHAT_IDS', '')
        self.owner_chat_ids = [int(chat_id.strip()) for chat_id in owner_chat_ids_str.split(',') if chat_id.strip()]
        
        # Токен бота для верифікації
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в змінних середовища")

    def _verify_telegram_widget_data(self, user_data: Dict[str, Any]) -> bool:
        """
        Верифікація даних від Telegram Login Widget згідно з офіційною документацією
        https://core.telegram.org/widgets/login#checking-authorization
        """
        try:
            # Витягуємо hash
            received_hash = user_data.get('hash')
            if not received_hash:
                return False
            
            # Видаляємо hash з даних для верифікації
            data_to_verify = {k: v for k, v in user_data.items() if k != 'hash'}
            
            # Сортуємо ключі та створюємо рядок для перевірки
            data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(data_to_verify.items())])
            
            # Створюємо секретний ключ з токена бота
            secret_key = hashlib.sha256(self.bot_token.encode()).digest()
            
            # Створюємо підпис
            calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
            
            # Перевіряємо відповідність хешів
            if not hmac.compare_digest(calculated_hash, received_hash):
                return False
            
            # Перевіряємо термін дії (не більше 1 дня)
            auth_date = int(data_to_verify.get('auth_date', 0))
            current_time = int(datetime.utcnow().timestamp())
            if current_time - auth_date > 86400:  # 24 години
                return False
            
            return True
            
        except Exception as e:
            return False



    async def authenticate_widget(self, request: Request) -> Dict[str, Any]:
        """
        Автентифікація через Telegram Login Widget
        """
        try:
            data = await request.json()
            
            # Перевіряємо наявність обов'язкових полів
            required_fields = ['id', 'auth_date', 'hash']
            for field in required_fields:
                if field not in data:
                    return Response.error(
                        f"Поле '{field}' обов'язкове", 
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
            
            # Верифікуємо дані від Telegram Login Widget
            if not self._verify_telegram_widget_data(data):
                return Response.error(
                    "Невірні дані від Telegram", 
                    status_code=status.HTTP_401_UNAUTHORIZED
                )
            
            telegram_id = data['id']
            
            # Перевіряємо, чи користувач є адміном або власником
            admin = await self.db.admins.find_one({"telegram_id": telegram_id})
            is_owner = telegram_id in self.owner_chat_ids
            
            if not admin and not is_owner:
                return Response.error(
                    "Доступ заборонено. Telegram аутентифікація доступна тільки для адмінів.",
                    status_code=status.HTTP_403_FORBIDDEN
                )
            
            if admin:
                # Адмін вже існує - відразу генеруємо токени
                access_token = self.jwt_handler.create_access_token(str(admin["_id"]))
                refresh_token = self.jwt_handler.create_refresh_token(str(admin["_id"]))
                
                # Логування події
                event_logger = EventLogger(admin)
                await event_logger.log_custom_event(
                    event_type="admin_telegram_widget_login",
                    description="Адмін увійшов через Telegram Login Widget"
                )
                
                # Підготовка даних адміна для відповіді
                admin_data = {
                    "id": str(admin["_id"]),
                    "email": admin.get("email", ""),
                    "first_name": admin.get("first_name", data.get('first_name', '')),
                    "last_name": admin.get("last_name", data.get('last_name', '')),
                    "telegram_id": telegram_id,
                    "role": admin.get("role", "admin"),
                    "is_verified": admin.get("is_verified", False)
                }
                
                return Response.success({
                    "admin": admin_data,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "bearer",
                    "user_type": "admin",
                    "auth_method": "telegram_widget"
                })
            else:
                # Власник ще не зареєстрований - потрібна реєстрація
                return Response.success({
                    "message": "Власник не зареєстрований. Потрібна реєстрація через бот або Web App.",
                    "is_registered": False,
                    "user_type": "owner",
                    "telegram_data": {
                        "id": telegram_id,
                        "first_name": data.get('first_name', ''),
                        "last_name": data.get('last_name', ''),
                        "username": data.get('username', ''),
                        "photo_url": data.get('photo_url', '')
                    }
                })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при автентифікації через Telegram Widget: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 



 