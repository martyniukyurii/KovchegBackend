from fastapi import Request, Query, HTTPException, status
from typing import Dict, Any, Optional, List
from api.response import Response
from tools.database import Database
from tools.config import DatabaseConfig
from tools.embedding_service import EmbeddingService
from datetime import datetime
import os
import warnings
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document
from api.endpoints.users import convert_objectid
import asyncio

# Приховуємо попередження від LangChain
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_openai")


class SmartSearchEndpoints:
    def __init__(self):
        self.db = Database()
        self.config = DatabaseConfig()
        # Ініціалізація OpenAI embeddings
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model="text-embedding-ada-002"
        )

    async def smart_search(
        self,
        request: Request,
        query: str = Query(..., description="Запит людською мовою для пошуку нерухомості"),
        limit: int = Query(10, ge=1, le=50, description="Кількість результатів"),
        collection_key: Optional[str] = Query("all", description="В якій колекції шукати: properties, parsed_listings, all")
    ) -> Dict[str, Any]:
        """
        Розумний пошук нерухомості за запитом людською мовою.
        Використовує векторні ембединги для семантичного пошуку.
        """
        try:
            # Генерація векторного ембедингу для запиту
            query_embedding = await self._get_embedding(query)
            results = {}
            # Вибір колекції для пошуку
            if collection_key == "properties":
                properties_results = await self._search_properties(query_embedding, limit)
                properties_results = convert_objectid(properties_results)
                results["properties"] = properties_results
            elif collection_key == "parsed_listings":
                listings_results = await self._search_parsed_listings(query_embedding, limit)
                listings_results = convert_objectid(listings_results)
                results["parsed_listings"] = listings_results
            else:  # all або будь-яке інше значення
                properties_results = await self._search_properties(query_embedding, limit)
                properties_results = convert_objectid(properties_results)
                listings_results = await self._search_parsed_listings(query_embedding, limit)
                listings_results = convert_objectid(listings_results)
                results["properties"] = properties_results
                results["parsed_listings"] = listings_results
                combined_results = await self._combine_and_rank_results(
                    properties_results,
                    listings_results,
                    limit
                )
                combined_results = convert_objectid(combined_results)
                results["combined"] = combined_results
            # Збереження запиту в історію пошуку (якщо користувач авторизований)
            await self._save_search_query(request, query)
            return Response.success({
                "query": query,
                "results": results,
                "collection_key": collection_key,
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            return Response.error(
                message=f"Помилка при розумному пошуку: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def create_embeddings(self, request: Request) -> Dict[str, Any]:
        """
        Створити векторні ембединги для існуючих записів в базі даних.
        Цей ендпойнт потрібно викликати один раз для ініціалізації.
        """
        try:
            # Отримання всіх properties без ембедингів
            properties = await self.db.properties.find({"vector_embedding": {"$exists": False}})
            
            # Отримання всіх parsed_listings без ембедингів
            parsed_listings = await self.db.parsed_listings.find({"vector_embedding": {"$exists": False}})
            
            properties_updated = 0
            listings_updated = 0
            properties_skipped = 0
            listings_skipped = 0
            
            # Створення ембедингів для properties
            for prop in properties:
                try:
                    if not isinstance(prop, dict):
                        properties_skipped += 1
                        continue
                    if "_id" not in prop or "title" not in prop:
                        properties_skipped += 1
                        continue
                    text_content = self._prepare_property_text(prop)
                    embedding = await self._get_embedding(text_content)
                    await self.db.properties.update_one(
                        {"_id": prop["_id"]},
                        {"$set": {"vector_embedding": embedding}}
                    )
                    properties_updated += 1
                except Exception:
                    properties_skipped += 1
                    continue
            # Створення ембедингів для parsed_listings
            for listing in parsed_listings:
                try:
                    if not isinstance(listing, dict):
                        listings_skipped += 1
                        continue
                    if "_id" not in listing or "title" not in listing:
                        listings_skipped += 1
                        continue
                    text_content = self._prepare_listing_text(listing)
                    embedding = await self._get_embedding(text_content)
                    await self.db.parsed_listings.update_one(
                        {"_id": listing["_id"]},
                        {"$set": {"vector_embedding": embedding}}
                    )
                    listings_updated += 1
                except Exception:
                    listings_skipped += 1
                    continue
            
            # Створення векторних індексів якщо їх ще немає
            await self.db.create_vector_indexes()
            
            return Response.success({
                "message": "Векторні ембединги успішно створено",
                "properties_updated": properties_updated,
                "listings_updated": listings_updated,
                "properties_skipped": properties_skipped,
                "listings_skipped": listings_skipped
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при створенні ембедингів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def _get_embedding(self, text: str) -> List[float]:
        """Отримати векторний ембединг для тексту."""
        try:
            # Використання asyncio для асинхронного виклику
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None, 
                lambda: self.embeddings.embed_query(text)
            )
            return embedding
        except Exception as e:
            raise Exception(f"Помилка при створенні ембедингу: {str(e)}")

    async def _search_properties(self, query_embedding: List[float], limit: int) -> List[Dict]:
        """Пошук в колекції properties."""
        try:
            results = await self.db.properties.vector_search(
                vector=query_embedding,
                limit=limit
            )
            return results
        except Exception as e:
            print(f"Помилка при пошуку в properties: {e}")
            return []

    async def _search_parsed_listings(self, query_embedding: List[float], limit: int) -> List[Dict]:
        """Пошук в колекції parsed_listings."""
        try:
            results = await self.db.parsed_listings.vector_search(
                vector=query_embedding,
                limit=limit
            )
            return results
        except Exception as e:
            print(f"Помилка при пошуку в parsed_listings: {e}")
            return []

    def _prepare_property_text(self, property_data: Dict) -> str:
        """Підготовка тексту для створення ембедингу з даних property."""
        parts = []
        
        # Основна інформація
        if property_data.get("title"):
            parts.append(property_data["title"])
        
        if property_data.get("description"):
            parts.append(property_data["description"])
        
        # Локація
        location = property_data.get("location", {})
        if location.get("city"):
            parts.append(f"Місто: {location['city']}")
        if location.get("district"):
            parts.append(f"Район: {location['district']}")
        if location.get("address"):
            parts.append(f"Адреса: {location['address']}")
        
        # Характеристики
        if property_data.get("property_type"):
            parts.append(f"Тип: {property_data['property_type']}")
        
        if property_data.get("transaction_type"):
            parts.append(f"Операція: {property_data['transaction_type']}")
        
        # Ціна
        price = property_data.get("price", {})
        if price.get("amount"):
            currency = price.get("currency", "грн")
            parts.append(f"Ціна: {price['amount']} {currency}")
        
        # Площа та кімнати
        if property_data.get("area"):
            parts.append(f"Площа: {property_data['area']} кв.м")
        
        if property_data.get("rooms"):
            parts.append(f"Кімнат: {property_data['rooms']}")
        
        # Характеристики
        features = property_data.get("features", {})
        if features.get("bedrooms"):
            parts.append(f"Спалень: {features['bedrooms']}")
        if features.get("bathrooms"):
            parts.append(f"Санвузлів: {features['bathrooms']}")
        if features.get("floor"):
            parts.append(f"Поверх: {features['floor']}")
        if features.get("floors_total"):
            parts.append(f"Поверхів всього: {features['floors_total']}")
        
        # Зручності
        amenities = features.get("amenities", [])
        if amenities:
            parts.append(f"Зручності: {', '.join(amenities)}")
        
        return " ".join(parts)

    def _prepare_listing_text(self, listing_data: Dict) -> str:
        """Підготовка тексту для створення ембедингу з даних parsed_listing."""
        parts = []
        
        # Основна інформація
        if listing_data.get("title"):
            parts.append(listing_data["title"])
        
        if listing_data.get("description"):
            parts.append(listing_data["description"])
        
        # Локація
        location = listing_data.get("location", {})
        if location.get("city"):
            parts.append(f"Місто: {location['city']}")
        if location.get("address"):
            parts.append(f"Адреса: {location['address']}")
        
        # Тип нерухомості
        if listing_data.get("property_type"):
            parts.append(f"Тип: {listing_data['property_type']}")
        
        # Ціна
        price = listing_data.get("price", {})
        if price.get("amount"):
            currency = price.get("currency", "грн")
            parts.append(f"Ціна: {price['amount']} {currency}")
        
        # Ціна оренди
        rent_price = listing_data.get("rent_price", {})
        if rent_price.get("amount"):
            currency = rent_price.get("currency", "грн")
            period = rent_price.get("period", "місяць")
            parts.append(f"Оренда: {rent_price['amount']} {currency}/{period}")
        
        # Характеристики
        features = listing_data.get("features", {})
        if features.get("area"):
            parts.append(f"Площа: {features['area']} кв.м")
        if features.get("bedrooms"):
            parts.append(f"Спалень: {features['bedrooms']}")
        if features.get("bathrooms"):
            parts.append(f"Санвузлів: {features['bathrooms']}")
        
        # Джерело
        source = listing_data.get("source", {})
        if source.get("platform"):
            parts.append(f"Джерело: {source['platform']}")
        
        return " ".join(parts)

    async def _combine_and_rank_results(
        self, 
        properties: List[Dict], 
        listings: List[Dict], 
        limit: int
    ) -> List[Dict]:
        """Комбінування та ранжування результатів з різних колекцій."""
        combined = []
        
        # Додавання properties з позначкою типу
        for prop in properties:
            prop["_source_type"] = "property"
            # Конвертація ObjectId до string для серіалізації
            if "_id" in prop:
                prop["_id"] = str(prop["_id"])
            # Видалення векторного ембедингу з відповіді
            if "vector_embedding" in prop:
                del prop["vector_embedding"]
            combined.append(prop)
        
        # Додавання listings з позначкою типу
        for listing in listings:
            listing["_source_type"] = "parsed_listing"
            # Конвертація ObjectId до string для серіалізації
            if "_id" in listing:
                listing["_id"] = str(listing["_id"])
            # Видалення векторного ембедингу з відповіді
            if "vector_embedding" in listing:
                del listing["vector_embedding"]
            combined.append(listing)
        
        # Сортування за score (якщо є) або за датою створення
        combined.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return combined[:limit]

    async def _save_search_query(self, request: Request, query: str):
        """Збереження запиту в історію пошуку користувача."""
        try:
            # Спроба отримати користувача з токена (якщо є)
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                from api.jwt_handler import JWTHandler
                jwt_handler = JWTHandler()
                token = auth_header.split(" ")[1]
                payload = jwt_handler.decode_token(token)
                user_id = payload.get("sub")
                
                if user_id:
                    # Додавання запиту до історії пошуку користувача
                    await self.db.users.update_one(
                        {"_id": user_id},
                        {
                            "$push": {
                                "search_history": {
                                    "query": query,
                                    "timestamp": datetime.utcnow().isoformat(),
                                    "search_type": "smart_search"
                                }
                            }
                        }
                    )
        except Exception:
            # Ігноруємо помилки збереження історії
            pass 