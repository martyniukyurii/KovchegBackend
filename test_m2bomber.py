import asyncio
import json
import sys
from pathlib import Path

# Додаємо system до path
sys.path.append(str(Path(__file__).parent / "system"))

from parsers.m2bomber_parser import M2BomberParser

async def test_m2bomber():
    # Тестові дані
    test_urls = [
        {
            "url": "https://ua.m2bomber.com/commercial-sell/cernivecka-oblast-3-72526",
            "site": "M2BOMBER",
            "type": "commerce"
        }
    ]
    
    parser = M2BomberParser()
    
    try:
        print("🧪 Тестуємо M2Bomber парсер...")
        results = await parser.parse_all_m2bomber_urls(test_urls)
        
        print(f"\n✅ Результат: {len(results)} оголошень")
        
        if results:
            print("\n📋 Перше оголошення:")
            first_result = results[0]
            for key, value in first_result.items():
                if key == 'images':
                    print(f"  {key}: {len(value) if value else 0} зображень")
                elif key == 'description':
                    print(f"  {key}: {value[:100] if value else 'N/A'}...")
                else:
                    print(f"  {key}: {value}")
        
    except Exception as e:
        print(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_m2bomber()) 