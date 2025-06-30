import asyncio
import sys
from pathlib import Path

# Додаємо кореневу директорію до Python path
sys.path.append(str(Path(__file__).parent))

from system.parsers.olx_parser import OLXParser

async def test_parser_results():
    """Тестуємо чи повертають парсери результати"""
    
    print("🧪 Тестуємо повернення результатів OLX парсера...")
    
    try:
        parser = OLXParser()
        await parser.init_browser()
        
        # Тестуємо з одним URL
        test_urls = [{
            'url': 'https://www.olx.ua/nedvizhimost/kommercheskaya-nedvizhimost/chernovtsy/?currency=UAH&search%5Border%5D=created_at:desc',
            'site': 'OLX',
            'type': 'commerce'
        }]
        
        print(f"📋 Парсимо {len(test_urls)} URL...")
        
        results = await parser.parse_all_olx_urls(test_urls)
        
        print(f"✅ Отримано {len(results)} результатів")
        
        if results:
            print("🎯 Перші 3 результати:")
            for i, result in enumerate(results[:3]):
                print(f"  {i+1}. {result.get('title', 'Без назви')[:50]}...")
                print(f"     URL: {result.get('url', 'N/A')}")
                print(f"     Тип: {result.get('property_type', 'N/A')}")
                print()
        else:
            print("❌ Результатів немає!")
            
        await parser.close_browser()
        
        return results
        
    except Exception as e:
        print(f"❌ Помилка тестування: {e}")
        return []

if __name__ == "__main__":
    results = asyncio.run(test_parser_results())
    print(f"\n📊 Загалом отримано: {len(results)} результатів") 