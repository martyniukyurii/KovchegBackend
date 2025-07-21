import sys
import os
import asyncio
from datetime import datetime, time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.router import Router
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from bot.telegram_bot import TelegramBot

# Додавання ліфспен подій
from contextlib import asynccontextmanager

# Додаємо стандартний CORS middleware як резервний варіант
from tools.database import Database
from tools.logger import Logger

logger = Logger()


class CustomCorsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Обробляємо OPTIONS запити
        if request.method == "OPTIONS":
            return JSONResponse(
                content={},
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
                    "Access-Control-Max-Age": "600",
                }
            )
        
        # Обробляємо інші запити
        response = await call_next(request)
        
        # Додаємо CORS заголовки до всіх відповідей
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управління життєвим циклом додатка"""
    # Startup
    print("⭐ LIFESPAN STARTUP ПОЧАВСЯ!")
    logger.info("🚀 Запуск API сервера...")
    
    # Ініціалізація бази даних
    db = Database()
    await db.setup_indexes()
    
    # Ініціалізація роутера
    try:
        logger.info("🔧 Початок ініціалізації роутера...")
        router = Router(app)
        await router.initialize()
        logger.info("✅ Роутер успішно ініціалізовано")
    except Exception as e:
        logger.error(f"❌ Помилка ініціалізації роутера: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # Запуск фонових задач
    from api.background_tasks import background_manager
    await background_manager.start()
    
    # Запускаємо Telegram бота в фоновому режимі
    from bot.telegram_bot import TelegramBot
    telegram_bot = TelegramBot()
    asyncio.create_task(telegram_bot.start_admin_bot())
    
    try:
        yield
    finally:
        # Shutdown
        logger.info("🛑 Зупинка API сервера...")
        await background_manager.stop()

# Оновлюємо FastAPI app щоб використовувати lifespan
app = FastAPI(
    title="Kovcheg Backend API",
    description="API для системи керування нерухомістю",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc", 
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Роути будуть додані в lifespan

# Додаємо статичні файли
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Додаємо наш власний CORS middleware
app.add_middleware(CustomCorsMiddleware)

# Додаємо стандартний CORS middleware як резервний варіант
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint для моніторингу"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

# Startup event тепер в lifespan функції

if __name__ == "__main__":
    print("🚀 Запуск Kovcheg API сервера...")
    print("📍 Документація буде доступна за адресою: http://0.0.0.0:8002/docs")
    print("🔍 Розумний пошук: http://0.0.0.0:8002/search/")
    
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8002, 
        reload=True,
        log_level="info"
    )