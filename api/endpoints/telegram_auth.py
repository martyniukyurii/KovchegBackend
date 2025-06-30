from fastapi import Depends, HTTPException, status, Request
from typing import Dict, Any, Optional
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime, timedelta
import secrets
import uuid
from api.jwt_handler import JWTHandler


class TelegramAuthEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def authenticate(self, request: Request) -> Dict[str, Any]:
        """
        Початок процесу автентифікації через Telegram.
        """
        try:
            data = await request.json()
            telegram_id = data.get("telegram_id")
            
            if not telegram_id:
                return Response.error("Telegram ID обов'язковий", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Генерація коду верифікації
            verification_code = str(secrets.randbelow(10000)).zfill(4)
            
            # Перевірка, чи існує користувач з таким Telegram ID
            user = await self.db.users.find_one({"telegram_id": telegram_id})
            
            if not user:
                # Якщо користувача не знайдено, зберігаємо код верифікації для подальшої реєстрації
                verification_data = {
                    "telegram_id": telegram_id,
                    "code": verification_code,
                    "created_at": datetime.utcnow(),
                    "expires_at": datetime.utcnow() + timedelta(minutes=5)
                }
                await self.db.verification_codes.create(verification_data)
                
                # TODO: Відправка коду верифікації через Telegram Bot API
                
                return Response.success({
                    "message": "Код верифікації надіслано у Telegram",
                    "is_registered": False
                })
            else:
                # Якщо користувач знайдений, зберігаємо код верифікації для входу
                verification_data = {
                    "user_id": user["_id"],
                    "telegram_id": telegram_id,
                    "code": verification_code,
                    "created_at": datetime.utcnow(),
                    "expires_at": datetime.utcnow() + timedelta(minutes=5)
                }
                await self.db.verification_codes.create(verification_data)
                
                # TODO: Відправка коду верифікації через Telegram Bot API
                
                return Response.success({
                    "message": "Код верифікації надіслано у Telegram",
                    "is_registered": True
                })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при автентифікації через Telegram: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def verify_telegram_code(self, request: Request) -> Dict[str, Any]:
        """
        Верифікація коду, отриманого через Telegram.
        """
        try:
            data = await request.json()
            telegram_id = data.get("telegram_id")
            code = data.get("code")
            
            if not telegram_id or not code:
                return Response.error("Telegram ID та код обов'язкові", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Пошук коду верифікації
            verification = await self.db.verification_codes.find_one({
                "telegram_id": telegram_id,
                "code": code
            })
            
            if not verification:
                raise AuthException(AuthErrorCode.INVALID_VERIFICATION_CODE)
            
            # Перевірка терміну дії коду
            if verification["expires_at"] < datetime.utcnow():
                await self.db.verification_codes.delete({"telegram_id": telegram_id, "code": code})
                raise AuthException(AuthErrorCode.INVALID_VERIFICATION_CODE)
            
            # Перевірка, чи існує користувач з таким Telegram ID
            user = await self.db.users.find_one({"telegram_id": telegram_id})
            
            if not user:
                # Якщо користувача не знайдено, повертаємо успішний результат верифікації,
                # але клієнт повинен виконати додаткову реєстрацію
                return Response.success({
                    "message": "Код верифіковано успішно. Необхідна додаткова реєстрація.",
                    "is_registered": False,
                    "telegram_id": telegram_id
                })
            else:
                # Якщо користувач знайдений, генеруємо токени
                access_token = self.jwt_handler.create_access_token(user["_id"])
                refresh_token = self.jwt_handler.create_refresh_token(user["_id"])
                
                # Логування події
                event_logger = EventLogger(user)
                await event_logger.log_custom_event(
                    event_type="telegram_login",
                    description="Користувач увійшов через Telegram"
                )
                
                # Видалення коду верифікації
                await self.db.verification_codes.delete({"telegram_id": telegram_id, "code": code})
                
                # Підготовка даних користувача для відповіді
                user_data = {
                    "id": user["_id"],
                    "email": user.get("email", ""),
                    "first_name": user.get("first_name", ""),
                    "last_name": user.get("last_name", ""),
                    "telegram_id": telegram_id,
                    "is_verified": user.get("is_verified", False)
                }
                
                return Response.success({
                    "user": user_data,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "bearer",
                    "is_registered": True
                })
            
        except AuthException as e:
            return Response.error(
                message=e.detail["detail"],
                status_code=e.status_code,
                details={"code": e.detail["code"]}
            )
        except Exception as e:
            return Response.error(
                message=f"Помилка при верифікації коду Telegram: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 