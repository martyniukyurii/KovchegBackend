import asyncio
import sys

# Виправлення для macOS + Python 3.9
if sys.platform == 'darwin' and sys.version_info[:2] == (3, 9):
    class NoOpChildWatcher:
        def add_child_handler(self, *args, **kwargs): pass
        def remove_child_handler(self, *args, **kwargs): pass
        def attach_loop(self, *args, **kwargs): pass
        def close(self): pass
        def is_active(self): return True
        def __enter__(self): return self
        def __exit__(self, *args): pass
    
    # Патч child watcher
    asyncio.events.get_child_watcher = lambda: NoOpChildWatcher()

import json
import random
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from openai import OpenAI
from dotenv import load_dotenv
import aiohttp
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, Browser
import openai
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import requests

# Завантажуємо змінні середовища з .env файлу
load_dotenv()

# Додаємо кореневу директорію проекту до Python path
sys.path.append(str(Path(__file__).parent.parent.parent))

from tools.logger import Logger
from tools.database import SyncDatabase
from tools.embedding_service import EmbeddingService

class OLXParser:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.exchange_rates = {}
        self.logger = Logger()
        self.db = SyncDatabase()
        self.embedding_service = EmbeddingService()  # Додаємо сервіс ембедингів
        
        # Імпортуємо TelegramBot динамічно
        from bot.telegram_bot import TelegramBot
        self.telegram_bot = TelegramBot()
        
    async def setup_browser(self):
        """Налаштування браузера для парсингу з обробкою всіх помилок"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Фікс для Docker середовища
                import os
                os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '0')
                
                # Закриваємо попередні з'єднання якщо є
                if hasattr(self, 'browser') and self.browser:
                    try:
                        await self.browser.close()
                    except:
                        pass
                        
                if hasattr(self, 'playwright') and self.playwright:
                    try:
                        await self.playwright.stop()
                    except:
                        pass
                
                self.playwright = await async_playwright().start()
                
                # Спробуємо Chromium
                try:
                    self.browser = await self.playwright.chromium.launch(
                        headless=True,
                        args=[
                            '--no-sandbox', 
                            '--disable-dev-shm-usage', 
                            '--disable-web-security',
                            '--disable-features=VizDisplayCompositor',
                            '--disable-ipc-flooding-protection',
                            '--disable-background-timer-throttling',
                            '--disable-renderer-backgrounding'
                        ]
                    )
                    browser_name = "Chromium"
                except Exception as chromium_error:
                    self.logger.warning(f"⚠️ Chromium недоступний: {chromium_error}")
                    # Спробуємо Firefox
                    try:
                        self.browser = await self.playwright.firefox.launch(
                            headless=True,
                            args=[
                                '--no-sandbox',
                                '--disable-dev-shm-usage'
                            ]
                        )
                        browser_name = "Firefox"
                    except Exception as firefox_error:
                        self.logger.warning(f"⚠️ Firefox недоступний: {firefox_error}")
                        # Спробуємо Webkit
                        self.browser = await self.playwright.webkit.launch(
                            headless=True
                        )
                        browser_name = "Webkit"
                
                self.context = await self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                )
                
                # Налаштовуємо обробку помилок для контексту
                self.context.set_default_timeout(30000)  # 30 секунд
                
                self.page = await self.context.new_page()
                
                # Обробка помилок сторінки
                self.page.on("pageerror", lambda error: self.logger.warning(f"⚠️ JS помилка на сторінці: {error}"))
                self.page.on("requestfailed", lambda request: self.logger.warning(f"⚠️ Запит не вдався: {request.url}"))
                
                self.logger.info(f"✅ {browser_name} браузер ініціалізовано")
                return True
                
            except Exception as e:
                retry_count += 1
                self.logger.warning(f"⚠️ Спроба {retry_count}/{max_retries} ініціалізації браузера не вдалася: {e}")
                
                if retry_count < max_retries:
                    await asyncio.sleep(5)  # Чекаємо 5 секунд перед повторною спробою
                else:
                    self.logger.error(f"❌ Не вдалося ініціалізувати браузер після {max_retries} спроб")
                    self.browser = None
                    self.context = None
                    self.page = None
                    return False
            
    async def init_browser(self):
        """Ініціалізація браузера"""
        # Фікс для Docker середовища
        import os
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '0')
        
        self.playwright = await async_playwright().start()
        
        # Використовуємо Firefox з додатковими налаштуваннями для серверного середовища
        self.browser = await self.playwright.firefox.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0',
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        
        self.page = await self.context.new_page()
        
        # Встановлюємо таймаути
        self.page.set_default_timeout(60000)
        self.page.set_default_navigation_timeout(60000)
        
    async def close_browser(self):
        """Закриття браузера"""
        try:
            if hasattr(self, 'page') and self.page:
                try:
                    await asyncio.wait_for(self.page.close(), timeout=5.0)
                except:
                    pass
                self.page = None
            if hasattr(self, 'context') and self.context:
                try:
                    await asyncio.wait_for(self.context.close(), timeout=5.0)
                except:
                    pass
                self.context = None
            if hasattr(self, 'browser') and self.browser:
                try:
                    await asyncio.wait_for(self.browser.close(), timeout=5.0)
                except:
                    pass
                self.browser = None
            if hasattr(self, 'playwright') and self.playwright:
                try:
                    await asyncio.wait_for(self.playwright.stop(), timeout=5.0)
                except:
                    pass
                self.playwright = None
        except Exception as e:
            self.logger.warning(f"Помилка при закритті браузера: {e}")
            
    def check_listing_exists(self, url: str) -> bool:
        """Перевіряємо чи існує оголошення в базі"""
        try:
            existing = self.db.parsed_listings.find_one({"url": url})
            return existing is not None
        except Exception as e:
            self.logger.error(f"Помилка перевірки існування оголошення: {e}")
            return False
    
    async def save_to_database(self, listing_data: Dict) -> Optional[str]:
        """Зберігаємо оголошення в MongoDB та відправляємо в Telegram"""
        try:
            # Додаємо мета-дані
            listing_data['parsed_at'] = datetime.now().isoformat()
            listing_data['source'] = 'OLX'
            listing_data['is_active'] = True
            
            # Створюємо векторний ембединг
            try:
                embedding = await self.embedding_service.create_listing_embedding(listing_data)
                if embedding:
                    listing_data['vector_embedding'] = embedding
                else:
                    self.logger.warning(f"⚠️ Не вдалося створити ембединг для: {listing_data.get('title', 'Без назви')}")
            except Exception as embedding_error:
                self.logger.error(f"❌ Помилка створення ембедингу: {embedding_error}")
                # Продовжуємо збереження навіть без ембедингу
            
            # Зберігаємо в базу
            result_id = self.db.parsed_listings.create(listing_data)
            
            if result_id:
                self.logger.info(f"💾 Збережено в MongoDB: {listing_data.get('title', 'Без назви')}")
                
                # Відправляємо в Telegram одразу після збереження
                try:
                    await self.telegram_bot.send_to_channel(listing_data)
                    self.logger.info(f"📤 Відправлено в Telegram: {listing_data.get('title', 'Без назви')}")
                except Exception as telegram_error:
                    self.logger.error(f"❌ Помилка відправки в Telegram: {telegram_error}")
                
                return result_id
            else:
                self.logger.error("Помилка збереження в базу")
                return None
                
        except Exception as e:
            self.logger.error(f"Помилка збереження в MongoDB: {e}")
            return None
            
    async def get_exchange_rates(self) -> Dict[str, float]:
        """Отримуємо актуальні курси валют з API НБУ кожен раз"""
        self.logger.info("🔄 Запит курсів валют до API НБУ...")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
            }
            
            url = 'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json'
            self.logger.info(f"📡 Запит до: {url}")
            
            # Використовуємо requests замість aiohttp
            response = requests.get(url, headers=headers, timeout=10)
            self.logger.info(f"📊 Статус відповіді: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                rates = {'UAH': 1.0}  # UAH як базова валюта
                
                for item in data:
                    if item['cc'] == 'USD':
                        rates['USD'] = item['rate']
                    elif item['cc'] == 'EUR':
                        rates['EUR'] = item['rate']
                        
                self.logger.info(f"✅ Отримано актуальні курси НБУ: USD={rates.get('USD', 'N/A')}, EUR={rates.get('EUR', 'N/A')}")
                return rates
            else:
                self.logger.error(f"❌ Неуспішний статус відповіді: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"❌ Помилка при отриманні курсів НБУ: {e}")
            
        # Якщо не вдалося отримати курси, використовуємо приблизні
        default_rates = {'UAH': 1.0, 'USD': 41.78, 'EUR': 48.99}  # Оновлені приблизні курси
        self.logger.warning("⚠️ Використовуємо приблизні курси валют")
        return default_rates
        
    def convert_price_to_all_currencies(self, price: int, currency: str, rates: Dict[str, float]) -> Dict[str, int]:
        """Конвертуємо ціну в усі валюти"""
        if not price or not currency:
            return {'UAH': None, 'USD': None, 'EUR': None}
            
        try:
            # Спочатку конвертуємо в UAH
            if currency == 'UAH':
                price_uah = price
            else:
                price_uah = price * rates.get(currency, 1.0)
                
            # Тепер конвертуємо в усі валюти
            return {
                'UAH': round(price_uah),
                'USD': round(price_uah / rates.get('USD', 37.0)),
                'EUR': round(price_uah / rates.get('EUR', 40.0))
            }
        except Exception as e:
            self.logger.error(f"Помилка при конвертації ціни: {e}")
            return {'UAH': None, 'USD': None, 'EUR': None}
            

    def extract_listing_urls(self, html_content: str) -> List[str]:
        """Витягуємо посилання на оголошення зі сторінки списку за допомогою регексу"""
        # Регекс для пошуку посилань на оголошення OLX
        # Шукаємо посилання типу /d/uk/obyavlenie/ або /d/obyavlenie/
        pattern = r'href="(/d/(?:uk/)?obyavlenie/[^"]+)"'
        matches = re.findall(pattern, html_content)
        
        # Додаємо базовий домен до відносних посилань
        full_urls = []
        for match in matches:
            if match.startswith('/'):
                full_urls.append(f"https://www.olx.ua{match}")
            else:
                full_urls.append(match)
                
        # Видаляємо дублікати
        return list(set(full_urls))
        
    async def wait_for_page_load(self):
        """Очікуємо завантаження сторінки"""
        try:
            # Чекаємо на завантаження DOM
            await self.page.wait_for_load_state('domcontentloaded', timeout=15000)
            await asyncio.sleep(2)  # Додатковий час для JS
        except Exception as e:
            self.logger.warning(f"Помилка при очікуванні завантаження сторінки: {e}")
            
    async def extract_phone(self) -> Optional[str]:
        """Витягуємо номер телефону"""
        try:
            # Спочатку шукаємо кнопку показу номера
            phone_buttons = [
                'button:has-text("Показать номер")',
                'button:has-text("Показати номер")', 
                'button[data-testid*="phone"]',
                'button[class*="phone"]',
                '[data-cy*="phone"]',
                'button:has-text("xxx-xx-xx")',
                'button:has-text("показать")',
                'button:has-text("показати")'
            ]
            
            for selector in phone_buttons:
                try:
                    button = await self.page.query_selector(selector)
                    if button:
                        # Натискаємо кнопку
                        await button.click()
                        await asyncio.sleep(3)  # Чекаємо завантаження номера
                        break
                except:
                    continue
                    
            # Тепер шукаємо номер телефону в різних місцях
            phone_selectors = [
                '[data-testid*="phone"]',
                '[class*="phone"]',
                '[data-cy*="phone"]',
                'a[href^="tel:"]'
            ]
            
            for selector in phone_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        text = await element.inner_text()
                        # Використовуємо регекс для витягування номера
                        phone_match = re.search(r'(\+?38)?[0-9\s\-\(\)]{10,}', text)
                        if phone_match:
                            phone = re.sub(r'[^\d+]', '', phone_match.group())
                            if len(phone) >= 10:
                                return phone
                except:
                    continue
                    
            # Якщо не знайшли через селектори, шукаємо в тексті сторінки
            page_text = await self.page.inner_text('body')
            phone_patterns = [
                r'\+?38\s?0\d{2}\s?\d{3}\s?\d{2}\s?\d{2}',
                r'0\d{2}\s?\d{3}\s?\d{2}\s?\d{2}',
                r'\d{3}-\d{3}-\d{2}-\d{2}',
                r'\d{3}\s\d{3}\s\d{2}\s\d{2}'
            ]
            
            for pattern in phone_patterns:
                match = re.search(pattern, page_text)
                if match:
                    phone = re.sub(r'[^\d+]', '', match.group())
                    if len(phone) >= 10:
                        return phone
                        
            return None
            
        except Exception as e:
            self.logger.error(f"Помилка при витягуванні телефону: {e}")
            return None
            
    async def extract_images(self) -> List[str]:
        """Витягуємо посилання на зображення об'єкта (до 10 штук) з очікуванням завантаження"""
        try:
            images = []
            max_attempts = 5  # Максимум спроб
            attempt = 0
            
            # Точні селектори для фотографій об'єкта на OLX (на основі реальної структури)
            image_selectors = [
                '[data-testid="image-galery-container"] img',  # Основний контейнер галереї
                '[data-testid="ad-photo"] img',                # Конкретні фото об'єкта
                '[data-cy="adPhotos-swiperSlide"] img',        # Слайди з фотографіями
                '.swiper-zoom-container img',                  # Контейнер зуму
                '.swiper-slide img',                           # Загальний слайдер
                'img[src*="apollo.olxcdn"]',                   # CDN OLX (найважливіший)
                'img[data-src*="apollo.olxcdn"]',              # Lazy loading CDN
                '[data-cy="adPhotos"] img',                    # Альтернативний контейнер
                '[data-testid*="photo"] img',                  # Будь-які photo testid
                '.photo-container img',                        # Контейнер фотографій
                '.gallery img',                                # Галерея
                'img[alt*="квартира"]',                        # Alt з назвою об'єкта
                'img[alt*="будинок"]',
                'img[alt*="приміщення"]',
                'img[alt*="офіс"]',
                'img[alt*="магазин"]',
                'img[alt*="ком"]',                             # комерційні приміщення
                'img[alt*="склад"]',
                'img[alt*="земля"]',
                'img[alt*="ділянка"]'
            ]
            
            while attempt < max_attempts:
                images = []
                
                # Спочатку чекаємо поки завантажиться галерея
                try:
                    await self.page.wait_for_selector('[data-testid="image-galery-container"]', timeout=5000)
                    await asyncio.sleep(1)  # Додатковий час для повного завантаження
                except:
                    self.logger.warning(f"Галерея не завантажилася за 5 секунд, спроба {attempt + 1}")
                
                for selector in image_selectors:
                    try:
                        elements = await self.page.query_selector_all(selector)
                        for element in elements:
                            # Пробуємо різні атрибути зображень
                            src_attrs = ['src', 'data-src', 'data-original', 'data-lazy']
                            src = None
                            
                            for attr in src_attrs:
                                src = await element.get_attribute(attr)
                                if src and self.is_valid_image_url(src):
                                    break
                                    
                            # Також пробуємо srcset
                            if not src:
                                srcset = await element.get_attribute('srcset')
                                if srcset:
                                    # Беремо перше зображення з srcset
                                    first_src = srcset.split(',')[0].split(' ')[0]
                                    if self.is_valid_image_url(first_src):
                                        src = first_src
                            
                            if src and self.is_valid_image_url(src):
                                # Перевіряємо чи це не дублікат
                                if src not in images:
                                    images.append(src)
                                    
                                # Обмежуємо кількість зображень
                                if len(images) >= 10:
                                    break
                                    
                        if len(images) >= 10:
                            break
                            
                    except Exception as e:
                        continue
                
                # Якщо знайшли зображення, виходимо з циклу
                if len(images) > 0:
                    break
                    
                # Якщо зображення не знайдено, чекаємо і пробуємо знову
                attempt += 1
                if attempt < max_attempts:
                    self.logger.warning(f"Зображення не знайдено, спроба {attempt}/{max_attempts}. Чекаємо 3 секунди...")
                    await asyncio.sleep(3)
                    # Прокручуємо сторінку щоб активувати lazy loading
                    await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                    await self.page.evaluate("window.scrollTo(0, 0)")
                    await asyncio.sleep(1)
                    
            if len(images) == 0:
                self.logger.warning("🚨 ЗОБРАЖЕННЯ НЕ ЗНАЙДЕНО після всіх спроб! Перевірте селектори.")
            else:
                self.logger.info(f"✅ Знайдено {len(images)} зображень")
                
            return images
            
        except Exception as e:
            self.logger.error(f"Помилка при витягуванні зображень: {e}")
            return []
            
    def is_valid_image_url(self, url: str) -> bool:
        """Перевіряємо чи є URL валідним зображенням об'єкта"""
        if not url or len(url) < 10:
            return False
            
        url_lower = url.lower()
        
        # Пропускаємо іконки та службові зображення
        invalid_patterns = [
            'placeholder',
            'icon',
            'logo',
            'sprite',
            'avatar',
            'default',
            'blank',
            'data:image',  # base64 зображення
            '.svg',        # SVG іконки
            'full-screen', # Кнопка розгортання
            'location',    # Іконка локації
            'google_play', # Іконки додатків
            'app_store',
            'static/media' # Статичні медіа файли
        ]
        
        for pattern in invalid_patterns:
            if pattern in url_lower:
                return False
        
        # Перевіряємо чи це фотографія з CDN OLX
        is_olx_photo = 'apollo.olxcdn.com' in url_lower and '/files/' in url_lower
        
        # Або має валідне розширення
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        has_valid_extension = any(ext in url_lower for ext in valid_extensions)
        
        # Перевіряємо розмір зображення (OLX додає параметр s= для розмірів)
        has_size_param = ';s=' in url_lower and any(size in url_lower for size in ['x', '2448', '3000', '4000'])
        
        return is_olx_photo or (has_valid_extension and has_size_param)
            
    def extract_location_with_regex(self, text: str) -> Optional[str]:
        """Витягуємо локацію за допомогою регексів як fallback"""
        if not text:
            return None
            
        # Патерни для пошуку адрес в Чернівцях
        patterns = [
            r'(?:вул\.?|вулиця)\s*([А-Яа-яІіЇїЄє\s]+?)(?:\s*,?\s*\d+)?',
            r'(?:пр\.?|проспект)\s*([А-Яа-яІіЇїЄє\s]+?)(?:\s*,?\s*\d+)?',
            r'(?:бул\.?|бульвар)\s*([А-Яа-яІіЇїЄє\s]+?)(?:\s*,?\s*\d+)?',
            r'(?:р-н|район)\s*([А-Яа-яІіЇїЄє\s]+)',
            r'(Центр|Гравітон|Проспект|Рша|Садгора|Роша|Калинка)',
            r'(?:ЖК|жк)\s*([А-Яа-яІіЇїЄє\s]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                location = matches[0].strip()
                if len(location) > 3:  # Мінімальна довжина
                    return location
                    
        return None
        
    async def get_location_from_openai(self, description: str, title: str) -> Optional[str]:
        """Використовуємо OpenAI для визначення локації з опису"""
        # Спочатку пробуємо OpenAI
        try:
            if self.openai_client:
                text = f"Назва: {title or ''}\nОпис: {description or ''}"
                
                response = self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Ти допомагаєш визначити точну адресу з опису нерухомості в Чернівцях. Шукай назви вулиць (з номером будинку чи без), проспектів, районів міста (наприклад: Центр, Гравітон, Проспект тощо). Відповідай ТІЛЬКИ адресою без додаткового тексту. Якщо адресу не знайдено, відповідай 'Не знайдено'."},
                        {"role": "user", "content": f"Знайди адресу або район в цьому тексті про нерухомість в Чернівцях:\n\n{text[:800]}"}
                    ],
                    max_tokens=60,
                    temperature=0.1
                )
                
                location = response.choices[0].message.content.strip()
                if location and location != "Не знайдено":
                    return location
                    
        except Exception as e:
            self.logger.warning(f"OpenAI недоступний: {e}")
            
        # Якщо OpenAI не спрацював, використовуємо регекси
        full_text = f"{title or ''} {description or ''}"
        regex_location = self.extract_location_with_regex(full_text)
        if regex_location:
            self.logger.info(f"Локацію знайдено через regex: {regex_location}")
            return regex_location
            
        return None
            
    async def extract_listing_data(self, url: str) -> Optional[Dict]:
        """Витягуємо дані з одного оголошення"""
        try:
            # Перевіряємо чи браузер доступний
            if not self.page or not self.browser:
                self.logger.warning("Браузер недоступний, спробуємо ініціалізувати...")
                await self.init_browser()
                
            await self.page.goto(url, wait_until='domcontentloaded')
            await self.wait_for_page_load()
            
            # Витягуємо назву з різних місць
            title = None
            
            # Спочатку пробуємо з title тегу
            title_selectors = [
                'title',
                'h1',
                '[data-cy="ad-title"]',
                '[class*="title"]',
                'meta[property="og:title"]'
            ]
            
            for selector in title_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        if selector == 'meta[property="og:title"]':
                            title = await element.get_attribute('content')
                        else:
                            title = await element.inner_text()
                        
                        if title and len(title.strip()) > 5:
                            # Очищуємо title від зайвого тексту
                            title = title.split(' - OLX.ua')[0].strip()
                            title = title.split(' - Дошка')[0].strip()
                            title = title.split(' | OLX')[0].strip()
                            break
                except:
                    continue
            
            # Витягуємо ціну з валютою за допомогою регексу
            page_content = await self.page.content()
            price_patterns = [
                r'(\d+(?:\s?\d+)*)\s*\$',
                r'(\d+(?:\s?\d+)*)\s*USD',
                r'(\d+(?:\s?\d+)*)\s*€',
                r'(\d+(?:\s?\d+)*)\s*EUR',
                r'(\d+(?:\s?\d+)*)\s*грн',
                r'(\d+(?:\s?\d+)*)\s*UAH',
                r'"price":(\d+)',
                r'Ціна[^0-9]*(\d+(?:\s?\d+)*)'
            ]
            
            price = None
            currency = None
            
            for pattern in price_patterns:
                match = re.search(pattern, page_content)
                if match:
                    price_str = match.group(1).replace(' ', '').replace('\u00a0', '')
                    try:
                        price = int(price_str)
                        # Визначаємо валюту
                        if '$' in pattern or 'USD' in pattern:
                            currency = 'USD'
                        elif '€' in pattern or 'EUR' in pattern:
                            currency = 'EUR'
                        elif 'грн' in pattern or 'UAH' in pattern:
                            currency = 'UAH'
                        else:
                            currency = 'USD'  # За замовчуванням
                        break
                    except:
                        continue
                        
            # Витягуємо поверх
            floor = None
            floor_patterns = [
                r'(\d+)\s*поверх',
                r'Поверх[^0-9]*(\d+)',
                r'поверх[^0-9]*(\d+)',
                r'(\d+)\s*-?й?\s*поверх'
            ]
            
            for pattern in floor_patterns:
                match = re.search(pattern, page_content, re.IGNORECASE)
                if match:
                    try:
                        floor = int(match.group(1))
                        break
                    except:
                        continue
                        
            # Витягуємо квадратні метри
            area = None
            area_patterns = [
                r'(\d+(?:[,\.]\d+)?)\s*(?:кв\.?\s*м|м²|m²)',
                r'площа[^0-9]*(\d+(?:[,\.]\d+)?)',
                r'(\d+(?:[,\.]\d+)?)\s*кв',
                r'"area":(\d+(?:\.\d+)?)'
            ]
            
            for pattern in area_patterns:
                match = re.search(pattern, page_content, re.IGNORECASE)
                if match:
                    try:
                        area_str = match.group(1).replace(',', '.')
                        area = float(area_str)
                        break
                    except:
                        continue
                        
            # Витягуємо опис
            description_selectors = [
                '[data-cy="ad_description"]',
                '[class*="description"]',
                '[data-testid*="description"]',
                'meta[name="description"]'
            ]
            
            description = None
            for selector in description_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        if selector == 'meta[name="description"]':
                            description = await element.get_attribute('content')
                        else:
                            description = await element.inner_text()
                        if description and len(description) > 20:
                            break
                except:
                    continue
                    
            # Витягуємо теги (можуть бути в різних місцях)
            tags = []
            try:
                # Шукаємо теги в різних селекторах
                tag_selectors = [
                    '[data-cy*="tag"]',
                    '[class*="tag"]',
                    '[class*="parameter"]',
                    '[data-testid*="parameter"]'
                ]
                
                for selector in tag_selectors:
                    elements = await self.page.query_selector_all(selector)
                    for element in elements:
                        text = await element.inner_text()
                        if text and len(text.strip()) > 0:
                            # Розбиваємо на окремі рядки та очищуємо
                            lines = text.split('\n')
                            for line in lines:
                                line = line.strip()
                                # Пропускаємо "Приватна особа" та порожні рядки
                                if line and line != "Приватна особа" and len(line) > 2:
                                    tags.append(line)
                            
            except Exception as e:
                self.logger.warning(f"Помилка при витягуванні тегів: {e}")
                
            # Витягуємо номер телефону
            phone = await self.extract_phone()
            
            # Витягуємо зображення
            images = await self.extract_images()
            
            # Отримуємо курси валют
            exchange_rates = await self.get_exchange_rates()
            
            # Конвертуємо ціну в усі валюти
            price_all_currencies = self.convert_price_to_all_currencies(price, currency, exchange_rates)
            
            # Визначаємо локацію 
            location = None
            if description or title:
                location = await self.get_location_from_openai(description, title)
                
            return {
                'url': url,
                'title': title,
                'price': price,
                'currency': currency,
                'price_uah': price_all_currencies['UAH'],
                'price_usd': price_all_currencies['USD'],
                'price_eur': price_all_currencies['EUR'],
                'floor': floor,
                'area': area,
                'description': description,
                'tags': tags[:20],  # Збільшуємо кількість тегів
                'phone': phone,
                'location': location,
                'images': images,
                'parsed_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Помилка при парсингу оголошення {url}: {e}")
            return None
            
    async def parse_listing_page(self, list_url: str, property_type: str = "unknown") -> List[Dict]:
        """Парсимо сторінку зі списком оголошень"""
        try:
            await self.page.goto(list_url, wait_until='domcontentloaded')
            await self.wait_for_page_load()
            
            # Отримуємо HTML контент для пошуку посилань
            html_content = await self.page.content()
            
            # Витягуємо посилання на оголошення
            listing_urls = self.extract_listing_urls(html_content)
            
            self.logger.info(f"Знайдено {len(listing_urls)} оголошень на сторінці {list_url}")
            
            results = []
            processed = 0
            skipped = 0
            
            for idx, url in enumerate(listing_urls[:20]):  # Збільшуємо до 20 оголошень
                
                # Перевіряємо чи існує вже в базі СПОЧАТКУ
                if self.check_listing_exists(url):
                    self.logger.info(f"⏭️ Пропускаємо (вже існує): {url}")
                    skipped += 1
                    continue
                
                self.logger.info(f"📄 Парсимо оголошення {processed + 1}: {url}")
                
                # Додаємо обробку помилок браузера з повторними спробами
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        listing_data = await self.extract_listing_data(url)
                        if listing_data:
                            listing_data['property_type'] = property_type
                            
                            # Зберігаємо в базу та відправляємо в Telegram
                            saved_id = await self.save_to_database(listing_data)
                            if saved_id:
                                results.append(listing_data)
                                processed += 1
                        break  # Успішно - виходимо з циклу повторів
                        
                    except Exception as e:
                        error_msg = str(e)
                        self.logger.error(f"❌ Помилка парсингу {url} (спроба {attempt + 1}/{max_retries}): {error_msg}")
                        
                        # Просто логуємо помилку без перезапуску браузера
                        
                        if attempt == max_retries - 1:
                            self.logger.error(f"💥 Не вдалося спарсити {url} після {max_retries} спроб")
                        else:
                            await asyncio.sleep(3)  # Пауза перед повтором
                    
                # Невелика пауза між запитами
                await asyncio.sleep(1)
            
            self.logger.info(f"✅ Оброблено: {processed}, пропущено: {skipped}")
            return results
            
        except Exception as e:
            self.logger.error(f"Помилка при парсингу сторінки списку {list_url}: {e}")
            return []
    async def safe_execute(self, func, *args, **kwargs):
        """Безпечне виконання функції з обробкою помилок"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                retry_count += 1
                self.logger.warning(f"⚠️ Помилка виконання {func.__name__}, спроба {retry_count}/{max_retries}: {e}")
                
                # Якщо помилка пов'язана з браузером, спробуємо перезапустити
                if any(keyword in str(e).lower() for keyword in ['connection', 'browser', 'playwright', 'timeout']):
                    self.logger.info("🔄 Перезапуск браузера...")
                    try:
                        await self.setup_browser()
                    except:
                        pass
                
                if retry_count < max_retries:
                    await asyncio.sleep(5 * retry_count)  # Експоненційна затримка
                else:
                    self.logger.error(f"❌ Остаточна помилка {func.__name__}: {e}")
                    return None
            
    async def parse_all_olx_urls(self, urls_data: List[Dict]) -> List[Dict]:
        """Парсимо всі OLX URL з файлу посилань"""
        all_results = []
        
        # Спочатку спробуємо ініціалізувати браузер
        browser_ready = await self.setup_browser()
        if not browser_ready:
            self.logger.warning("⚠️ Браузер недоступний, пропускаємо OLX парсинг")
            return all_results
        
        # Фільтруємо тільки OLX посилання
        olx_urls = [item for item in urls_data if item.get('site') == 'OLX']
        
        self.logger.info(f"Знайдено {len(olx_urls)} OLX посилань для парсингу")
        
        for url_data in olx_urls:
            url = url_data.get('url')
            property_type = url_data.get('type')
            
            self.logger.info(f"Парсимо категорію {property_type}: {url}")
            
            # Безпечне виконання парсингу
            results = await self.safe_execute(self.parse_listing_page, url, property_type)
            if results:
                all_results.extend(results)
                self.logger.info(f"Отримано {len(results)} оголошень з категорії {property_type}")
            else:
                self.logger.warning(f"⚠️ Не вдалося отримати результати з категорії {property_type}")
                
            # Затримка між категоріями
            await asyncio.sleep(3)
                
        # Закриваємо браузер після завершення
        await self.close_browser()
        return all_results
