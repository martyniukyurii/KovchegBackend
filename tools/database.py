from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from tools.logger import Logger
from tools.config import DatabaseConfig
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

logger = Logger()


class SyncDatabase:
    """Синхронна версія Database для використання в парсерах"""
    def __init__(self):
        self.config = DatabaseConfig()
        self.uri = self.config.get_connection_string()
        self._client: Optional[MongoClient] = None
        
        # Ініціалізація властивостей для колекцій
        self.parsed_listings = SyncCollectionHandler(self, "parsed_listings")

    def _get_client(self) -> MongoClient:
        """Повертає синхронного клієнта MongoDB."""
        if not self._client:
            # Додаємо SSL параметри для MongoDB Atlas
            self._client = MongoClient(
                self.uri,
                tls=True,
                tlsAllowInvalidCertificates=True,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=20000
            )
        return self._client

    def _get_collection(self, collection_name: str):
        """Повертає колекцію з відповідної бази даних."""
        client = self._get_client()
        db = client[self.config.DB_NAME]
        return db[collection_name]


class SyncCollectionHandler:
    """Синхронний обробник операцій для конкретної колекції."""

    def __init__(self, db_instance: SyncDatabase, collection_name: str):
        self.db = db_instance
        self.collection_name = collection_name

    def create(self, data: Dict) -> Optional[str]:
        """Створює новий документ в колекції."""
        try:
            collection = self.db._get_collection(self.collection_name)
            result = collection.insert_one(data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error creating document in {self.collection_name}: {e}")
            return None

    def find_one(self, query: Dict) -> Optional[Dict]:
        """Знаходить один документ в колекції."""
        try:
            collection = self.db._get_collection(self.collection_name)
            result = collection.find_one(query)
            return result
        except Exception as e:
            logger.error(f"Error finding document in {self.collection_name}: {e}")
            return None

    def insert_one(self, data: Dict) -> Optional[str]:
        """Вставляє один документ в колекцію."""
        try:
            collection = self.db._get_collection(self.collection_name)
            result = collection.insert_one(data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error inserting document in {self.collection_name}: {e}")
            return None

    def delete_many(self, query: Dict) -> int:
        """Видаляє багато документів з колекції."""
        try:
            collection = self.db._get_collection(self.collection_name)
            result = collection.delete_many(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error deleting documents from {self.collection_name}: {e}")
            return 0

    def count_documents(self, query: Dict = None) -> int:
        """Рахує кількість документів в колекції."""
        try:
            collection = self.db._get_collection(self.collection_name)
            if query is None:
                query = {}
            return collection.count_documents(query)
        except Exception as e:
            logger.error(f"Error counting documents in {self.collection_name}: {e}")
            return 0


class Database:
    def __init__(self):
        self.config = DatabaseConfig()
        self.uri = self.config.get_connection_string()
        self._client: Optional[AsyncIOMotorClient] = None

        # Ініціалізація властивостей для колекцій
        self.users = CollectionHandler(self, "users")
        self.verification_codes = CollectionHandler(self, "verification_codes")
        self.admins = CollectionHandler(self, "admins")
        self.properties = CollectionHandler(self, "properties")
        self.agents = CollectionHandler(self, "agents")
        self.clients = CollectionHandler(self, "clients")
        self.deals = CollectionHandler(self, "deals")
        self.calendar_events = CollectionHandler(self, "calendar_events")
        self.documents = CollectionHandler(self, "documents")
        self.marketing_campaigns = CollectionHandler(self, "marketing_campaigns")
        self.notifications = CollectionHandler(self, "notifications")
        self.training_programs = CollectionHandler(self, "training_programs")
        self.activity_journal = CollectionHandler(self, "activity_journal")
        self.parsed_listings = CollectionHandler(self, "parsed_listings")
        self.agent_daily_tasks = CollectionHandler(self, "agent_daily_tasks")
        self.logs = CollectionHandler(self, "logs")

    async def _get_client(self) -> AsyncIOMotorClient:
        """Повертає асинхронного клієнта MongoDB."""
        if not self._client:
            # Додаємо SSL параметри для MongoDB Atlas
            self._client = AsyncIOMotorClient(
                self.uri,
                tls=True,
                tlsAllowInvalidCertificates=True,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=20000
            )
        return self._client

    async def _get_collection(self, collection_name: str, user: Optional[Dict] = None):
        """Повертає колекцію з відповідної бази даних."""
        client = await self._get_client()
        db_name = user["collection_title"] if user else self.config.DB_NAME
        return client[db_name][collection_name]

    async def setup_indexes(self):
        """Створює індекси для оптимізації запитів."""
        try:
            client = await self._get_client()
            db = client[self.config.DB_NAME]

            # Індекси для users
            await db.users.create_index([("email", 1)], unique=True)
            await db.users.create_index([("login", 1)], unique=True)
            await db.users.create_index([("telegram_id", 1)], sparse=True)

            # Індекси для verification_codes
            await db.verification_codes.create_index([("user_id", 1)])
            await db.verification_codes.create_index([("created_at", 1)], expireAfterSeconds=86400)  # 24 години

            # Індекси для properties
            await db.properties.create_index([("location.city", 1)])
            await db.properties.create_index([("price.amount", 1)])
            await db.properties.create_index([("status.for_sale", 1)])
            await db.properties.create_index([("status.for_rent", 1)])
            await db.properties.create_index([("agent_id", 1)])
            await db.properties.create_index([("owner_id", 1)])
            
            # Індекси для agents
            await db.agents.create_index([("user_id", 1)], unique=True)
            
            # Індекси для clients
            await db.clients.create_index([("agent_id", 1)])
            await db.clients.create_index([("user_id", 1)], sparse=True)
            await db.clients.create_index([("email", 1)], sparse=True)
            await db.clients.create_index([("phone", 1)], sparse=True)
            
            # Індекси для deals
            await db.deals.create_index([("property_id", 1)])
            await db.deals.create_index([("agent_id", 1)])
            await db.deals.create_index([("seller_id", 1)])
            await db.deals.create_index([("buyer_id", 1)])
            
            # Індекси для calendar_events
            await db.calendar_events.create_index([("start_time", 1)])
            await db.calendar_events.create_index([("participants.agents", 1)])
            await db.calendar_events.create_index([("participants.clients", 1)])
            
            # Індекси для activity_journal
            await db.activity_journal.create_index([("timestamp", 1)])
            await db.activity_journal.create_index([("related_to.id", 1)])
            await db.activity_journal.create_index([("participants.agents", 1)])
            await db.activity_journal.create_index([("participants.clients", 1)])
            
            # Індекси для parsed_listings
            await db.parsed_listings.create_index([("source.platform", 1)])
            await db.parsed_listings.create_index([("source.original_listing_id", 1)])
            await db.parsed_listings.create_index([("parsed_at", 1)])
            await db.parsed_listings.create_index([("is_active", 1)])
            
            # Індекси для agent_daily_tasks
            await db.agent_daily_tasks.create_index([("agent_id", 1), ("date", 1)], unique=True)
            await db.agent_daily_tasks.create_index([("expires_at", 1)], expireAfterSeconds=0)  # TTL індекс

            # TTL для логів (7 днів)
            await db.logs.create_index([("timestamp", 1)], expireAfterSeconds=604800)  # 7 днів

            logger.info("Індекси успішно створено")
        except Exception as e:
            logger.error(f"Помилка створення індексів: {e}")
            pass

    async def log_event(self, event_type: str, description: str, user_id: Optional[str] = None) -> Optional[str]:
        """Логує подію в колекцію logs."""
        log_entry = {
            "timestamp": datetime.utcnow(),
            "event_type": event_type,
            "description": description,
            "user_id": user_id
        }
        return await self.logs.create(log_entry)

    async def create_vector_indexes(self):
        """Створює векторні індекси для пошуку подібних об'єктів."""
        try:
            client = await self._get_client()
            db = client[self.config.DB_NAME]
            
            # Векторний індекс для properties
            await db.command({
                "createIndexes": "properties",
                "indexes": [{
                    "name": "vector_embedding",
                    "key": {"vector_embedding": "hnsw"},
                    "params": {
                        "dimensions": 1536,  # Розмірність вектора OpenAI
                        "similarity": "cosine"
                    }
                }]
            })
            
            # Векторний індекс для parsed_listings
            await db.command({
                "createIndexes": "parsed_listings",
                "indexes": [{
                    "name": "vector_embedding",
                    "key": {"vector_embedding": "hnsw"},
                    "params": {
                        "dimensions": 1536,  # Розмірність вектора OpenAI
                        "similarity": "cosine"
                    }
                }]
            })
            
            logger.info("Векторні індекси успішно створено")
        except Exception as e:
            logger.error(f"Помилка створення векторних індексів: {e}")
            pass


class CollectionHandler:
    """Обробник операцій для конкретної колекції."""

    def __init__(self, db_instance: Database, collection_name: str):
        self.db = db_instance
        self.collection_name = collection_name

    async def create(self, data: Dict, user: Optional[Dict] = None) -> Optional[str]:
        """Створює новий документ в колекції."""
        try:
            collection = await self.db._get_collection(self.collection_name, user)
            result = await collection.insert_one(data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error creating document in {self.collection_name}: {e}")
            return None

    async def update(self, query: Dict, update_data: Dict, user: Optional[Dict] = None) -> int:
        """Оновлює документи в колекції."""
        try:
            collection = await self.db._get_collection(self.collection_name, user)
            result = await collection.update_many(query, {"$set": update_data})
            return result.modified_count
        except Exception as e:
            logger.error(f"Error updating documents in {self.collection_name}: {e}")
            return 0

    async def update_one(self, query: Dict, update_data: Dict, user: Optional[Dict] = None) -> int:
        """Оновлює один документ в колекції."""
        try:
            collection = await self.db._get_collection(self.collection_name, user)
            result = await collection.update_one(query, update_data)
            return result.modified_count
        except Exception as e:
            logger.error(f"Error updating document in {self.collection_name}: {e}")
            return 0

    async def delete(self, query: Dict, user: Optional[Dict] = None) -> int:
        """Видаляє документи з колекції."""
        try:
            collection = await self.db._get_collection(self.collection_name, user)
            result = await collection.delete_many(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error deleting documents from {self.collection_name}: {e}")
            return 0

    async def find_one(self, query: Dict, user: Optional[Dict] = None) -> Optional[Dict]:
        """Знаходить один документ в колекції."""
        try:
            collection = await self.db._get_collection(self.collection_name, user)
            result = await collection.find_one(query)
            return result
        except Exception as e:
            logger.error(f"Error finding document in {self.collection_name}: {e}")
            return None

    async def find_many(self, query: Dict, user: Optional[Dict] = None) -> List[Dict]:
        """Знаходить багато документів в колекції."""
        try:
            collection = await self.db._get_collection(self.collection_name, user)
            cursor = collection.find(query)
            return await cursor.to_list(length=None)
        except Exception as e:
            logger.error(f"Error finding documents in {self.collection_name}: {e}")
            return []

    async def count_documents(self, query: Dict, user: Optional[Dict] = None) -> int:
        """Підраховує кількість документів в колекції, що відповідають запиту."""
        try:
            collection = await self.db._get_collection(self.collection_name, user)
            return await collection.count_documents(query)
        except Exception as e:
            logger.error(f"Error counting documents in {self.collection_name}: {e}")
            return 0

    async def find(self, query: Dict, skip: int = 0, limit: int = 0, sort: list = None, projection: Dict = None, user: Optional[Dict] = None) -> List[Dict]:
        """Знаходить документи з підтримкою пагінації, сортування та проекції."""
        try:
            collection = await self.db._get_collection(self.collection_name, user)
            cursor = collection.find(query, projection)
            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            return await cursor.to_list(length=None)
        except Exception as e:
            logger.error(f"Error finding documents in {self.collection_name}: {e}")
            return []

    async def aggregate(self, pipeline: List[Dict], user: Optional[Dict] = None) -> List[Dict]:
        """Виконує агрегацію в колекції."""
        try:
            collection = await self.db._get_collection(self.collection_name, user)
            cursor = collection.aggregate(pipeline)
            return await cursor.to_list(length=None)
        except Exception as e:
            logger.error(f"Error aggregating in {self.collection_name}: {e}")
            return []

    async def create_index(self, keys: List[tuple], **kwargs) -> str:
        """Створює індекс в колекції."""
        try:
            collection = await self.db._get_collection(self.collection_name)
            result = await collection.create_index(keys, **kwargs)
            return result
        except Exception as e:
            logger.error(f"Error creating index in {self.collection_name}: {e}")
            raise
            
    async def vector_search(self, vector: List[float], limit: int = 10, user: Optional[Dict] = None) -> List[Dict]:
        """Виконує пошук за векторним індексом."""
        try:
            collection = await self.db._get_collection(self.collection_name, user)
            
            # Спробуємо спочатку MongoDB Atlas Vector Search
            try:
                pipeline = [
                    {
                        "$vectorSearch": {
                            "index": "vector_embedding_index",
                            "path": "vector_embedding",
                            "queryVector": vector,
                            "numCandidates": limit * 2,
                            "limit": limit
                        }
                    },
                    {
                        "$addFields": {
                            "score": {"$meta": "vectorSearchScore"}
                        }
                    }
                ]
                cursor = collection.aggregate(pipeline)
                results = await cursor.to_list(length=None)
                if results:
                    return results
            except Exception as atlas_error:
                logger.info(f"Atlas Vector Search не доступний, використовуємо cosine similarity: {atlas_error}")
            
            # Fallback до cosine similarity обчислення
            pipeline = [
                {
                    "$match": {
                        "vector_embedding": {"$exists": True}
                    }
                },
                {
                    "$addFields": {
                        "score": {
                            "$let": {
                                "vars": {
                                    "dotProduct": {
                                        "$reduce": {
                                            "input": {"$range": [0, {"$size": "$vector_embedding"}]},
                                            "initialValue": 0,
                                            "in": {
                                                "$add": [
                                                    "$$value",
                                                    {"$multiply": [
                                                        {"$arrayElemAt": ["$vector_embedding", "$$this"]},
                                                        {"$arrayElemAt": [vector, "$$this"]}
                                                    ]}
                                                ]
                                            }
                                        }
                                    },
                                    "normA": {
                                        "$sqrt": {
                                            "$reduce": {
                                                "input": "$vector_embedding",
                                                "initialValue": 0,
                                                "in": {"$add": ["$$value", {"$multiply": ["$$this", "$$this"]}]}
                                            }
                                        }
                                    },
                                    "normB": {
                                        "$sqrt": {
                                            "$reduce": {
                                                "input": vector,
                                                "initialValue": 0,
                                                "in": {"$add": ["$$value", {"$multiply": ["$$this", "$$this"]}]}
                                            }
                                        }
                                    }
                                },
                                "in": {
                                    "$cond": {
                                        "if": {"$and": [{"$gt": ["$$normA", 0]}, {"$gt": ["$$normB", 0]}]},
                                        "then": {"$divide": ["$$dotProduct", {"$multiply": ["$$normA", "$$normB"]}]},
                                        "else": 0
                                    }
                                }
                            }
                        }
                    }
                },
                {"$sort": {"score": -1}},
                {"$limit": limit}
            ]
            
            cursor = collection.aggregate(pipeline)
            return await cursor.to_list(length=None)
            
        except Exception as e:
            logger.error(f"Error performing vector search in {self.collection_name}: {e}")
            return []
