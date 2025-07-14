import os
import httpx
import jwt
from typing import Dict, Any, Optional
from tools.logger import Logger
import json
from datetime import datetime

logger = Logger()

class OAuth2Service:
    def __init__(self):
        # Google OAuth2
        self.google_client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        
        # Apple OAuth2
        self.apple_client_id = os.getenv('APPLE_CLIENT_ID')
        self.apple_team_id = os.getenv('APPLE_TEAM_ID')
        self.apple_key_id = os.getenv('APPLE_KEY_ID')
        self.apple_private_key = os.getenv('APPLE_PRIVATE_KEY')
        
        # URLs
        self.google_token_url = "https://oauth2.googleapis.com/token"
        self.google_userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        self.apple_token_url = "https://appleid.apple.com/auth/token"
        self.apple_keys_url = "https://appleid.apple.com/auth/keys"
        
    async def verify_google_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Верифікація Google OAuth2 токена"""
        try:
            if not self.google_client_id:
                logger.error("Google Client ID не налаштовано")
                return None
            
            # Спробуємо отримати інформацію про користувача
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.google_userinfo_url,
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code != 200:
                    logger.error(f"Помилка верифікації Google токена: {response.status_code}")
                    return None
                
                user_info = response.json()
                
                # Перевіряємо, чи email верифіковано
                if not user_info.get("verified_email", False):
                    logger.error("Google email не верифіковано")
                    return None
                
                return {
                    "provider": "google",
                    "provider_id": user_info.get("id"),
                    "email": user_info.get("email"),
                    "first_name": user_info.get("given_name", ""),
                    "last_name": user_info.get("family_name", ""),
                    "picture": user_info.get("picture", ""),
                    "verified_email": user_info.get("verified_email", False)
                }
                
        except Exception as e:
            logger.error(f"Помилка верифікації Google токена: {str(e)}")
            return None
    
    async def verify_apple_token(self, id_token: str) -> Optional[Dict[str, Any]]:
        """Верифікація Apple ID токена"""
        try:
            if not self.apple_client_id:
                logger.error("Apple Client ID не налаштовано")
                return None
            
            # Отримуємо публічні ключі Apple
            async with httpx.AsyncClient() as client:
                keys_response = await client.get(self.apple_keys_url)
                if keys_response.status_code != 200:
                    logger.error("Не вдалося отримати ключі Apple")
                    return None
                
                keys_data = keys_response.json()
                
            # Декодуємо заголовок JWT без верифікації
            unverified_header = jwt.get_unverified_header(id_token)
            key_id = unverified_header.get("kid")
            
            # Знаходимо відповідний ключ
            public_key = None
            for key in keys_data["keys"]:
                if key["kid"] == key_id:
                    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
                    break
            
            if not public_key:
                logger.error("Не знайдено відповідний ключ Apple")
                return None
            
            # Верифікуємо та декодуємо токен
            payload = jwt.decode(
                id_token,
                public_key,
                algorithms=["RS256"],
                audience=self.apple_client_id,
                issuer="https://appleid.apple.com"
            )
            
            # Перевіряємо термін дії
            if payload.get("exp", 0) < datetime.utcnow().timestamp():
                logger.error("Apple токен прострочений")
                return None
            
            # Розбираємо ім'я з email якщо немає окремих полів
            email = payload.get("email", "")
            email_parts = email.split("@")[0] if email else ""
            
            return {
                "provider": "apple",
                "provider_id": payload.get("sub"),
                "email": email,
                "first_name": payload.get("given_name", email_parts),
                "last_name": payload.get("family_name", ""),
                "verified_email": payload.get("email_verified", True)  # Apple emails завжди верифіковані
            }
            
        except jwt.ExpiredSignatureError:
            logger.error("Apple токен прострочений")
            return None
        except jwt.InvalidTokenError as e:
            logger.error(f"Невірний Apple токен: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Помилка верифікації Apple токена: {str(e)}")
            return None
    
    async def exchange_google_code_for_token(self, auth_code: str, redirect_uri: str) -> Optional[str]:
        """Обмін Google authorization code на access token"""
        try:
            if not self.google_client_id or not self.google_client_secret:
                logger.error("Google OAuth2 credentials не налаштовано")
                return None
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.google_token_url,
                    data={
                        "client_id": self.google_client_id,
                        "client_secret": self.google_client_secret,
                        "code": auth_code,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Помилка обміну Google code: {response.status_code}")
                    return None
                
                token_data = response.json()
                return token_data.get("access_token")
                
        except Exception as e:
            logger.error(f"Помилка обміну Google code: {str(e)}")
            return None
    
    def get_google_auth_url(self, redirect_uri: str, state: str = None) -> str:
        """Генерація URL для авторизації через Google"""
        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            "client_id": self.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline"
        }
        
        if state:
            params["state"] = state
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{base_url}?{query_string}"
    
    def get_apple_auth_url(self, redirect_uri: str, state: str = None) -> str:
        """Генерація URL для авторизації через Apple"""
        base_url = "https://appleid.apple.com/auth/authorize"
        params = {
            "client_id": self.apple_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code id_token",
            "scope": "name email",
            "response_mode": "form_post"
        }
        
        if state:
            params["state"] = state
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{base_url}?{query_string}" 