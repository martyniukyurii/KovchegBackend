import asyncio
import sys
from pathlib import Path

# Додаємо кореневу директорію до Python path
sys.path.append(str(Path(__file__).parent))

from bot.telegram_bot import TelegramBot

async def test_telegram_integration():
    """Тестуємо інтеграцію Telegram з готовими даними"""
    
    print("🧪 Тестуємо інтеграцію Telegram з готовими даними...")
    
    # Тестові дані що імітують результати парсерів
    test_results = [
        {
            'title': 'Тест комерційне приміщення OLX',
            'price': 1500,
            'currency': 'USD',
            'price_uah': 62667,
            'price_usd': 1500,
            'price_eur': 1278,
            'phone': '+380501234567',
            'location': 'Центр, Чернівці',
            'area': 120.0,
            'floor': 2,
            'tags': ['офіс', 'центр', 'євроремонт'],
            'url': 'https://www.olx.ua/test/1',
            'property_type': 'commerce',
            'images': [
                'https://ireland.apollo.olxcdn.com:443/v1/files/test1/image;s=1000x563',
                'https://ireland.apollo.olxcdn.com:443/v1/files/test2/image;s=1000x563'
            ]
        },
        {
            'title': 'Тест квартира для оренди M2Bomber',
            'price': 8000,
            'currency': 'UAH',
            'price_uah': 8000,
            'price_usd': 191,
            'price_eur': 163,
            'phone': '+380977777777',
            'location': 'Проспект, Чернівці',
            'area': 65.0,
            'floor': 5,
            'tags': ['2 кімнати', 'балкон', 'меблі'],
            'url': 'https://ua.m2bomber.com/test/2',
            'property_type': 'orenda',
            'images': [
                'https://ua.m2bomber.com/storage/test/normal-images/1_123456',
                'https://ua.m2bomber.com/storage/test/normal-images/2_123456'
            ]
        },
        {
            'title': 'Тест продаж будинку',
            'price': 85000,
            'currency': 'USD',
            'price_uah': 3551198,
            'price_usd': 85000,
            'price_eur': 72466,
            'phone': '+380631111111',
            'location': 'Садгора, Чернівці',
            'area': 180.0,
            'tags': ['будинок', 'ділянка 6 соток', 'гараж'],
            'url': 'https://www.olx.ua/test/3',
            'property_type': 'prodazh',
            'images': []
        }
    ]
    
    try:
        bot = TelegramBot()
        
        print(f"📤 Відправляємо {len(test_results)} тестових повідомлень...")
        
        sent_count = 0
        for i, result in enumerate(test_results):
            print(f"  📱 Відправляємо {i+1}/{len(test_results)}: {result['title'][:40]}...")
            
            success = await bot.send_to_channel(result)
            if success:
                sent_count += 1
                print(f"    ✅ Успішно відправлено в канал для типу '{result['property_type']}'")
            else:
                print(f"    ❌ Помилка відправки")
            
            # Пауза між повідомленнями
            await asyncio.sleep(2)
        
        print(f"\n📊 Результат: {sent_count}/{len(test_results)} повідомлень відправлено успішно")
        
        await bot.close()
        
        return sent_count == len(test_results)
        
    except Exception as e:
        print(f"❌ Помилка тестування: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_telegram_integration())
    if success:
        print("🎉 Тест пройшов успішно!")
    else:
        print("�� Тест не пройшов!") 