import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from api.router import Router
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


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


app = FastAPI(
    title="Kovcheg API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

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

@app.on_event("startup")
async def startup_event():
    """Виконується при старті застосунку"""
    router = Router(app)
    await router.initialize()

if __name__ == "__main__":
    print("🚀 Запуск Kovcheg API сервера...")
    print("📍 Документація буде доступна за адресою: http://0.0.0.0:8001/api/docs")
    print("🔍 Розумний пошук: http://0.0.0.0:8001/search/")
    
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8001, 
        reload=True,
        log_level="info"
    )