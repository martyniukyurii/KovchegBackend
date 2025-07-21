# Налаштування Google Drive OAuth

## 1. Отримання Google OAuth Credentials

1. Перейдіть до [Google Cloud Console](https://console.cloud.google.com/)
2. Створіть новий проект або виберіть існуючий
3. Активуйте Google Drive API:
   - Перейдіть в "APIs & Services" > "Library"
   - Знайдіть "Google Drive API" та активуйте його
4. Створіть OAuth 2.0 credentials:
   - Перейдіть в "APIs & Services" > "Credentials"
   - Натисніть "Create Credentials" > "OAuth 2.0 Client IDs"
   - Виберіть тип "Web application"
   - Додайте authorized redirect URIs (наприклад: `http://localhost:8002/auth/google-drive/callback`)

## 2. Налаштування .env файлу

Скопіюйте дані з створених credentials і додайте до .env файлу:

```env
# Google Drive OAuth
GOOGLE_CLIENT_ID=your_client_id_from_google_console
GOOGLE_CLIENT_SECRET=your_client_secret_from_google_console
GOOGLE_PROJECT_ID=your_project_id
```

## 3. Отримання OAuth токенів

Після налаштування credentials, використовуйте API для отримання токенів:

1. **Отримання Authorization URL:**
   ```python
   from tools.google_drive_service import google_drive_service
   
   # Отримати URL для авторизації
   auth_url = google_drive_service.get_oauth_url()
   print(f"Перейдіть за посиланням: {auth_url}")
   ```

2. **Обмін коду на токени:**
   ```python
   # Після переходу по URL та отримання authorization code
   tokens = google_drive_service.exchange_code_for_tokens("your_authorization_code")
   
   if tokens:
       print(f"Access Token: {tokens['access_token']}")
       print(f"Refresh Token: {tokens['refresh_token']}")
       print(f"Expiry: {tokens['expiry']}")
   ```

3. **Додавання токенів до .env:**
   ```env
   GOOGLE_ACCESS_TOKEN=ya29.a0AS3H6Nz3...
   GOOGLE_REFRESH_TOKEN=1//0c8Q-p7s7Ra1j...
   GOOGLE_TOKEN_EXPIRY=2025-12-31T23:59:59Z
   ```

## 4. Перезапуск сервісу

Після додавання всіх змінних до .env файлу, перезапустіть API сервер:

```bash
python3 api/main.py
```

Google Drive сервіс автоматично ініціалізується з новими credentials.

## Безпека

- **НІКОЛИ** не додавайте .env файл до Git
- **НІКОЛИ** не ділитесь токенами в публічних репозиторіях
- Регулярно оновлюйте токени для безпеки
- Використовуйте окремі credentials для production та development

## Troubleshooting

- Якщо токен expired, сервіс автоматично спробує його оновити
- При помилках перевірте правильність CLIENT_ID та CLIENT_SECRET
- Переконайтесь що Google Drive API активовано в Google Cloud Console 