import os
import io
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from tools.logger import Logger
from tools.config import GoogleDriveConfig

# Приховуємо зайві логи від Google OAuth бібліотек
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
logging.getLogger('google_auth_httplib2').setLevel(logging.ERROR)
logging.getLogger('oauth2client').setLevel(logging.ERROR)

class GoogleDriveService:
    def __init__(self):
        self.logger = Logger()
        self.config = GoogleDriveConfig()
        self.service = None
        self.folder_id = None
        self.scopes = ['https://www.googleapis.com/auth/drive']
        
        # Ініціалізуємо сервіс
        self._initialize_service()
    
    def _initialize_service(self):
        """Ініціалізація Google Drive API сервісу"""
        try:
            # Перевіряємо чи є credentials
            if not self.config.has_credentials():
                self.logger.warning("Google OAuth credentials не налаштовані в .env файлі")
                return
            
            creds = None
            
            # Створюємо credentials з .env змінних якщо є токени
            if self.config.has_tokens():
                token_info = {
                    'token': self.config.GOOGLE_ACCESS_TOKEN,
                    'refresh_token': self.config.GOOGLE_REFRESH_TOKEN,
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'client_id': self.config.GOOGLE_CLIENT_ID,
                    'client_secret': self.config.GOOGLE_CLIENT_SECRET,
                    'scopes': self.scopes
                }
                
                # Додаємо expiry якщо є
                if self.config.GOOGLE_TOKEN_EXPIRY:
                    try:
                        token_info['expiry'] = self.config.GOOGLE_TOKEN_EXPIRY
                    except:
                        pass
                
                creds = Credentials.from_authorized_user_info(token_info, self.scopes)
            
            # Оновлюємо токен якщо потрібно
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # Оновлюємо токени в пам'яті (але не записуємо в .env автоматично)
                    self.logger.info("Google OAuth токен оновлено. Рекомендується оновити GOOGLE_ACCESS_TOKEN в .env")
                except Exception as refresh_error:
                    self.logger.error(f"Не вдалося оновити токен: {refresh_error}")
                    return
            
            if creds and creds.valid:
                # Створюємо сервіс
                self.service = build('drive', 'v3', credentials=creds)
                self.logger.info("Google Drive сервіс успішно ініціалізовано")
                
                # Ініціалізуємо основну папку
                self._initialize_main_folder()
                
            else:
                self.logger.warning("Google OAuth токени недійсні або відсутні. Використовуйте OAuth flow для отримання токенів")
                
        except Exception as e:
            self.logger.error(f"Помилка ініціалізації Google Drive: {str(e)}")
    
    def _initialize_main_folder(self):
        """Ініціалізуємо основну папку CRM_Documents"""
        if not self.service:
            return
        
        try:
            self.folder_id = self._get_or_create_folder("CRM_Documents")
            
            # Надаємо доступ до папки власнику акаунту (тихо)
            self._share_folder_with_user(self.folder_id, "reader")
            
        except Exception as e:
            self.logger.error(f"Помилка ініціалізації основної папки: {str(e)}")
    
    def _get_or_create_folder(self, folder_name: str, parent_id: str = None) -> Optional[str]:
        """Отримуємо або створюємо папку"""
        try:
            # Спочатку шукаємо існуючу папку
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
            if parent_id:
                query += f" and parents in '{parent_id}'"
            
            results = self.service.files().list(q=query, fields="files(id,name)").execute()
            folders = results.get('files', [])
            
            if folders:
                return folders[0]['id']
            
            # Якщо папка не існує - створюємо
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_id:
                file_metadata['parents'] = [parent_id]
            
            folder = self.service.files().create(body=file_metadata, fields='id').execute()
            return folder.get('id')
            
        except HttpError as e:
            self.logger.error(f"Помилка створення/отримання папки {folder_name}: {str(e)}")
            return None
    
    def _share_folder_with_user(self, folder_id: str, role: str = "reader", user_email: str = None):
        """Надати доступ до папки користувачу"""
        try:
            if not user_email:
                # Отримуємо email поточного користувача з токена
                about = self.service.about().get(fields="user").execute()
                user_email = about['user']['emailAddress']
            
            permission = {
                'role': role,
                'type': 'user',
                'emailAddress': user_email
            }
            
            self.service.permissions().create(
                fileId=folder_id,
                body=permission,
                sendNotificationEmail=False
            ).execute()
            
        except HttpError as e:
            if e.status_code != 403:  # Тільки критичні помилки, не "already has access"
                self.logger.error(f"Помилка надання доступу до папки: {str(e)}")
        except Exception as e:
            self.logger.error(f"Загальна помилка надання доступу: {str(e)}")

    async def upload_file(self, file_content: bytes, filename: str, mime_type: str, 
                         category: str = "general") -> Optional[Dict[str, Any]]:
        """Завантажити файл на Google Drive"""
        try:
            if not self.service or not self.folder_id:
                self.logger.error("Google Drive сервіс не ініціалізовано")
                return None
            
            # Файли зберігаються прямо в CRM_Documents папці, без підпапок
            # Метадані файлу
            file_metadata = {
                'name': filename,
                'parents': [self.folder_id]
            }
            
            # Завантаження файлу
            media = MediaIoBaseUpload(
                io.BytesIO(file_content),
                mimetype=mime_type,
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,size,mimeType,webViewLink,webContentLink'
            ).execute()
            
            # Встановлюємо публічний доступ для перегляду
            self.service.permissions().create(
                fileId=file['id'],
                body={'role': 'reader', 'type': 'anyone'}
            ).execute()
            
            self.logger.info(f"Файл {filename} завантажено на Google Drive з ID: {file.get('id')}")
            
            return {
                'file_id': file.get('id'),
                'filename': file.get('name'),
                'size': int(file.get('size', 0)),
                'mime_type': file.get('mimeType'),
                'web_view_link': file.get('webViewLink'),
                'download_link': file.get('webContentLink')
            }
            
        except HttpError as e:
            self.logger.error(f"Помилка завантаження файлу {filename}: {str(e)}")
            return None
    
    async def download_file(self, file_id: str) -> Optional[bytes]:
        """Завантажити файл з Google Drive"""
        try:
            if not self.service:
                return None
            
            request = self.service.files().get_media(fileId=file_id)
            file_content = io.BytesIO()
            downloader = MediaIoBaseDownload(file_content, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            return file_content.getvalue()
            
        except HttpError as e:
            self.logger.error(f"Помилка завантаження файлу {file_id}: {str(e)}")
            return None
    
    async def delete_file(self, file_id: str) -> bool:
        """Видалити файл з Google Drive"""
        try:
            if not self.service:
                self.logger.error("Google Drive сервіс не доступний")
                return False
            
            # Спочатку перевіряємо чи файл існує
            try:
                file_info = self.service.files().get(fileId=file_id, fields="id,name,parents").execute()
                self.logger.info(f"🗂️ Файл знайдено: {file_info.get('name')} (ID: {file_id})")
            except HttpError as e:
                if e.status_code == 404:
                    self.logger.warning(f"⚠️ Файл {file_id} не знайдено на Google Drive (можливо вже видалено)")
                    return True  # Вважаємо успішним якщо файл не існує
                else:
                    raise e
            
            # Видаляємо файл (повністю, bypassing кошик)
            self.service.files().delete(fileId=file_id).execute()
            self.logger.info(f"✅ Файл {file_id} успішно видалено з Google Drive (повністю)")
            
            # Перевіряємо чи файл дійсно видалився
            try:
                self.service.files().get(fileId=file_id).execute()
                self.logger.error(f"❌ ПОМИЛКА: Файл {file_id} все ще існує після видалення!")
                return False
            except HttpError as e:
                if e.status_code == 404:
                    self.logger.info(f"✅ Підтверджено: файл {file_id} більше не існує")
                    return True
                else:
                    self.logger.error(f"❌ Помилка перевірки видалення: {str(e)}")
                    return False
            
        except HttpError as e:
            self.logger.error(f"❌ Помилка видалення файлу {file_id}: {str(e)}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Загальна помилка видалення файлу {file_id}: {str(e)}")
            return False
    
    def is_available(self) -> bool:
        """Перевірити чи доступний Google Drive сервіс"""
        return self.service is not None and self.folder_id is not None

    def get_oauth_url(self, redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob") -> Optional[str]:
        """Генерує OAuth URL для отримання токенів"""
        try:
            if not self.config.has_credentials():
                self.logger.error("Google OAuth credentials не налаштовані")
                return None
            
            # Створюємо OAuth flow
            client_config = {
                "web": {
                    "client_id": self.config.GOOGLE_CLIENT_ID,
                    "client_secret": self.config.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            }
            
            flow = Flow.from_client_config(
                client_config,
                scopes=self.scopes,
                redirect_uri=redirect_uri
            )
            
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            return auth_url
            
        except Exception as e:
            self.logger.error(f"Помилка генерації OAuth URL: {str(e)}")
            return None
    
    def exchange_code_for_tokens(self, code: str, redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob") -> Optional[Dict]:
        """Обмінює authorization code на токени"""
        try:
            if not self.config.has_credentials():
                self.logger.error("Google OAuth credentials не налаштовані")
                return None
            
            # Створюємо OAuth flow
            client_config = {
                "web": {
                    "client_id": self.config.GOOGLE_CLIENT_ID,
                    "client_secret": self.config.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            }
            
            flow = Flow.from_client_config(
                client_config,
                scopes=self.scopes,
                redirect_uri=redirect_uri
            )
            
            # Обмінюємо код на токени
            flow.fetch_token(code=code)
            
            creds = flow.credentials
            
            # Повертаємо токени для збереження в .env
            return {
                'access_token': creds.token,
                'refresh_token': creds.refresh_token,
                'expiry': creds.expiry.isoformat() if creds.expiry else None
            }
            
        except Exception as e:
            self.logger.error(f"Помилка обміну коду на токени: {str(e)}")
            return None

# Глобальний екземпляр сервісу
google_drive_service = GoogleDriveService() 