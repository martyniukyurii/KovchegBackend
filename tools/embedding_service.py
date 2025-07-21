import os
import warnings
from typing import List, Optional
from langchain_openai import OpenAIEmbeddings
from tools.logger import Logger
from dotenv import load_dotenv

# Завантажуємо змінні середовища
load_dotenv()

# Приховуємо попередження від LangChain
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_openai")

logger = Logger()

class EmbeddingService:
    """Сервіс для створення векторних ембедингів"""
    
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model="text-embedding-ada-002"
        )
    
    def prepare_listing_text(self, listing_data: dict) -> str:
        """Підготовляє текст з parsed listing для створення ембедингу (працює з обома структурами: парсер + API)"""
        parts = []
        
        # Основна інформація
        if listing_data.get("title"):
            parts.append(f"Назва: {listing_data['title']}")
        
        if listing_data.get("description"):
            parts.append(f"Опис: {listing_data['description']}")
        
        if listing_data.get("property_type"):
            parts.append(f"Тип: {listing_data['property_type']}")
        
        # Ціна (парсер використовує price, price_usd, price_eur, price_uah)
        if listing_data.get("price"):
            currency = listing_data.get("currency", "UAH")
            parts.append(f"Ціна: {listing_data['price']} {currency}")
        
        # Додаткові ціни від парсера
        if listing_data.get("price_usd"):
            parts.append(f"Ціна USD: {listing_data['price_usd']}")
        if listing_data.get("price_eur"):
            parts.append(f"Ціна EUR: {listing_data['price_eur']}")
        
        # Площа та кімнати
        if listing_data.get("area"):
            parts.append(f"Площа: {listing_data['area']} м²")
        
        if listing_data.get("rooms"):
            parts.append(f"Кімнат: {listing_data['rooms']}")
        
        # Поверх (тільки у парсера)
        if listing_data.get("floor"):
            parts.append(f"Поверх: {listing_data['floor']}")
        
        # Локація (парсер: рядок, API: об'єкт)
        location = listing_data.get("location")
        if isinstance(location, dict):
            # API структура
            if location.get("city"):
                parts.append(f"Місто: {location['city']}")
            if location.get("address"):
                parts.append(f"Адреса: {location['address']}")
        elif isinstance(location, str) and location.strip():
            # Парсер структура
            parts.append(f"Локація: {location}")
        
        # Особливості/теги (API: features[], парсер: tags[])
        features = listing_data.get("features", [])
        tags = listing_data.get("tags", [])
        
        if features and isinstance(features, list):
            features_text = ", ".join(str(f) for f in features[:10])
            parts.append(f"Особливості: {features_text}")
        elif tags and isinstance(tags, list):
            tags_text = ", ".join(str(t) for t in tags[:10])
            parts.append(f"Теги: {tags_text}")
        
        # Контакти (парсер: phone, API: contact_info)
        phone = listing_data.get("phone")
        contact_info = listing_data.get("contact_info", {})
        
        if phone:
            parts.append(f"Телефон: {phone}")
        elif contact_info.get("phone"):
            parts.append(f"Телефон: {contact_info['phone']}")
        
        # Джерело
        if listing_data.get("source"):
            parts.append(f"Джерело: {listing_data['source']}")
        
        # URL
        if listing_data.get("url"):
            parts.append(f"URL: {listing_data['url']}")
        
        return " | ".join(parts)
    
    def prepare_property_text(self, property_data: dict) -> str:
        """Підготовляє текст з property для створення ембедингу"""
        parts = []
        
        # Основна інформація
        if property_data.get("title"):
            parts.append(f"Назва: {property_data['title']}")
        
        if property_data.get("description"):
            parts.append(f"Опис: {property_data['description']}")
        
        if property_data.get("property_type"):
            parts.append(f"Тип: {property_data['property_type']}")
        
        if property_data.get("transaction_type"):
            parts.append(f"Транзакція: {property_data['transaction_type']}")
        
        # Ціна
        if property_data.get("price"):
            currency = property_data.get("currency", "USD") 
            parts.append(f"Ціна: {property_data['price']} {currency}")
        
        # Площа та кімнати
        if property_data.get("area"):
            parts.append(f"Площа: {property_data['area']} м²")
        
        if property_data.get("rooms"):
            parts.append(f"Кімнат: {property_data['rooms']}")
        
        # Локація
        location = property_data.get("location", {})
        if isinstance(location, dict):
            if location.get("city"):
                parts.append(f"Місто: {location['city']}")
            if location.get("address"):
                parts.append(f"Адреса: {location['address']}")
        
        # Особливості
        if property_data.get("features"):
            features = property_data["features"]
            if isinstance(features, list):
                features_text = ", ".join(str(f) for f in features[:10])
                parts.append(f"Особливості: {features_text}")
        
        return " | ".join(parts)
    
    async def create_embedding(self, text: str) -> Optional[List[float]]:
        """Створює векторний ембединг для тексту"""
        try:
            if not text or not text.strip():
                logger.warning("Порожній текст для створення ембедингу")
                return None
            
            # Обмежуємо довжину тексту (OpenAI має ліміт)
            max_length = 8000  # Безпечний ліміт
            if len(text) > max_length:
                text = text[:max_length]
                logger.info(f"Текст обрізано до {max_length} символів")
            
            embedding = await self.embeddings.aembed_query(text)
            
            if embedding and len(embedding) > 0:
                return embedding
            else:
                logger.error("Отримано порожній ембединг")
                return None
                
        except Exception as e:
            logger.error(f"Помилка створення ембедингу: {e}")
            return None
    
    async def create_listing_embedding(self, listing_data: dict) -> Optional[List[float]]:
        """Створює ембединг для parsed listing"""
        text = self.prepare_listing_text(listing_data)
        return await self.create_embedding(text)
    
    async def create_property_embedding(self, property_data: dict) -> Optional[List[float]]:
        """Створює ембединг для property"""
        text = self.prepare_property_text(property_data)
        return await self.create_embedding(text) 