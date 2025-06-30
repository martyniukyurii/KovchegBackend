import asyncio
import sys
from pathlib import Path

# Додаємо кореневу директорію до Python path
sys.path.append(str(Path(__file__).parent))

from bot.telegram_bot import TelegramBot

async def test_telegram_bot():
    """Тестуємо Telegram бота"""
    
    # Тестові дані з реальними зображеннями M2Bomber
    test_listing = {
        'title': 'Тест з реальними зображеннями M2Bomber',
        'price': 12500,
        'currency': 'UAH', 
        'phone': '+380977685537',
        'location': 'Новодністровськ, Чернівці',
        'area': 1000.0,
        'tags': ['1000 м²', 'автосервіс'],
        'url': 'https://ua.m2bomber.com/obj/1327083872/view/commercial-sell/dnistrovskii-raion-3-11905201/prodaetsa-avtoservis',
        'property_type': 'commerce',
        'images': [
            'https://ua.m2bomber.com/storage/obj/1327083872/normal-images/8_1750978742',
            'https://ua.m2bomber.com/storage/obj/1327083872/normal-images/0_1750978742',
            'https://ua.m2bomber.com/storage/obj/1327083872/normal-images/1_1750978742'
        ]
    }
    
    print("🤖 Тестуємо Telegram бота з реальними зображеннями M2Bomber...")
    
    try:
        bot = TelegramBot()
        
        print(f"📤 Відправляємо тестове повідомлення в канал @comodc...")
        
        result = await bot.send_to_channel(test_listing)
        
        if result:
            print("✅ Повідомлення успішно відправлено!")
        else:
            print("❌ Помилка відправки повідомлення")
            
        await bot.close()
        
    except Exception as e:
        print(f"❌ Помилка тестування бота: {e}")

if __name__ == "__main__":
    asyncio.run(test_telegram_bot()) 