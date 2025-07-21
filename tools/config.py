import os
from dotenv import load_dotenv


class Config:
    def __init__(self):
        # Завантаження змінних з кореневого .env файлу проекту
        load_dotenv()

        required_vars = ["OPENAI_API_KEY", "JWT_SECRET_KEY", "RESEND_API_KEY"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            raise ConfigError(
                f"Відсутні обов'язкові змінні в .env файлі: {', '.join(missing_vars)}"
            )

        # Ініціалізація значень
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # api key openai
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")  # jwt secret key
        self.RESEND_API_KEY = os.getenv("RESEND_API_KEY")  # resend.com - validation email


class GoogleDriveConfig:
    def __init__(self):
        # Завантаження змінних з кореневого .env файлу проекту
        load_dotenv()
        
        # Google OAuth credentials
        self.GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
        self.GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
        self.GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "braided-grammar-295920")
        
        # Google OAuth tokens (опціонально, можуть бути None)
        self.GOOGLE_ACCESS_TOKEN = os.getenv("GOOGLE_ACCESS_TOKEN")
        self.GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")
        self.GOOGLE_TOKEN_EXPIRY = os.getenv("GOOGLE_TOKEN_EXPIRY")
    
    def has_credentials(self) -> bool:
        """Перевіряє чи є необхідні credentials"""
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)
    
    def has_tokens(self) -> bool:
        """Перевіряє чи є збережені токени"""
        return bool(self.GOOGLE_ACCESS_TOKEN and self.GOOGLE_REFRESH_TOKEN)


class ConfigError(Exception):
    """Виняток для помилок конфігурації"""
    pass


class DatabaseConfig:
    def __init__(self):
        # Завантаження змінних з кореневого .env файлу проекту
        load_dotenv()

        # Перевіряємо чи є DB_URI
        self.DB_URI = os.getenv("DB_URI")

        if not self.DB_URI:
            raise ConfigError(
                "Відсутня обов'язкова змінна DB_URI в .env файлі. "
                "Приклад: DB_URI=mongodb://username:password@localhost:27017/database_name"
            )

        # Витягуємо назву бази з URI
        try:
            # Витягуємо назву бази з кінця URI
            if '/' in self.DB_URI.split('/')[-1]:
                self.DB_NAME = self.DB_URI.split('/')[-1]
            else:
                self.DB_NAME = "kovcheg_db"  # За замовчуванням
        except:
            self.DB_NAME = "kovcheg_db"  # За замовчуванням

    def get_connection_string(self):
        """Повертає рядок підключення до бази даних."""
        return self.DB_URI
