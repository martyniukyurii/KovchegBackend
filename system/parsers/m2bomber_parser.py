import asyncio
import re
import json
import requests
from datetime import datetime
from playwright.async_api import async_playwright
from openai import OpenAI
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Optional

# Завантажуємо змінні середовища
load_dotenv()

# Додаємо кореневу директорію до Python path
sys.path.append(str(Path(__file__).parent.parent.parent))
from tools.logger import Logger
from tools.database import SyncDatabase

class M2BomberParser:
    def __init__(self):
        self.browser = None
        self.context = None
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.exchange_rates = {}
        self.logger = Logger()
        self.db = SyncDatabase()
        
        # Імпортуємо TelegramBot динамічно
        from bot.telegram_bot import TelegramBot
        self.telegram_bot = TelegramBot()
        
        # Створюємо папку для індивідуальних результатів
        self.results_dir = Path(__file__).parent.parent.parent / "parsed_results" / "individual"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
    async def init_browser(self):
        """Ініціалізація браузера Playwright"""
        playwright = await async_playwright().start()
        
        # Використовуємо Firefox з додатковими налаштуваннями для серверного середовища
        self.browser = await playwright.firefox.launch(
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
        
    async def close_browser(self):
        """Закриття браузера та Telegram бота"""
        if self.browser:
            await self.browser.close()
        await self.telegram_bot.close()
            
    async def get_exchange_rates(self):
        """Отримання курсів валют з НБУ"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(
                'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json',
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                rates_data = response.json()
                
                for rate in rates_data:
                    if rate['cc'] == 'USD':
                        self.exchange_rates['USD'] = rate['rate']
                    elif rate['cc'] == 'EUR':
                        self.exchange_rates['EUR'] = rate['rate']
                        
                self.logger.info(f"✅ Отримано курси НБУ: USD={self.exchange_rates.get('USD')}, EUR={self.exchange_rates.get('EUR')}")
                return True
            else:
                self.logger.error(f"Помилка отримання курсів НБУ: статус {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"Помилка отримання курсів НБУ: {e}")
            self.exchange_rates = {'USD': 41.78, 'EUR': 48.99}
            return False
            
    def convert_currency(self, amount, from_currency):
        """Конвертація валют"""
        if not self.exchange_rates:
            self.exchange_rates = {'USD': 41.78, 'EUR': 48.99}
            
        if from_currency == 'UAH':
            return {
                'UAH': int(amount),
                'USD': int(amount / self.exchange_rates['USD']),
                'EUR': int(amount / self.exchange_rates['EUR'])
            }
        elif from_currency == 'USD':
            return {
                'UAH': int(amount * self.exchange_rates['USD']),
                'USD': int(amount),
                'EUR': int(amount * self.exchange_rates['USD'] / self.exchange_rates['EUR'])
            }
        elif from_currency == 'EUR':
            return {
                'UAH': int(amount * self.exchange_rates['EUR']),
                'USD': int(amount * self.exchange_rates['EUR'] / self.exchange_rates['USD']),
                'EUR': int(amount)
            }
        else:
            return {'UAH': int(amount), 'USD': int(amount), 'EUR': int(amount)}

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
            listing_data['source'] = 'M2BOMBER'
            listing_data['is_active'] = True
            
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

    def extract_listing_urls(self, html_content):
        """Витягування посилань на оголошення з регексу"""
        pattern = r'href=[\'"]([^\'"]*\/obj\/\d+\/view\/[^\'"]*)[\'"]'
        matches = re.findall(pattern, html_content)
        
        unique_urls = list(set(matches))
        
        full_urls = []
        for url in unique_urls:
            if url.startswith('/'):
                full_urls.append(f'https://ua.m2bomber.com{url}')
            else:
                full_urls.append(url)
                
        return full_urls

    async def extract_phone(self, page):
        """Витягування номера телефону з M2Bomber"""
        try:
            # Спочатку шукаємо прихований телефон
            phone_selectors = [
                '.fullcard-author-phone',
                'a[data-id][rel="nofollow"]'
            ]
            
            for selector in phone_selectors:
                try:
                    phone_element = await page.query_selector(selector)
                    if phone_element:
                        phone_text = await phone_element.text_content()
                        
                        # Якщо телефон прихований (xxx-xx-xx), намагаємося його розкрити
                        if 'xxx' in phone_text:
                            # Натискаємо на елемент для розкриття номеру
                            await phone_element.click()
                            await page.wait_for_timeout(3000)
                            
                            # Перевіряємо чи змінився текст
                            updated_text = await phone_element.text_content()
                            if updated_text and updated_text != phone_text and 'xxx' not in updated_text:
                                phone_text = updated_text
                        
                        # Витягуємо номер телефону
                        # Формат: (066) xxx-xx-xx або +380661234567
                        phone_match = re.search(r'\((\d{3})\)\s*(\d{3})-(\d{2})-(\d{2})', phone_text)
                        if phone_match:
                            return f"+380{phone_match.group(1)}{phone_match.group(2)}{phone_match.group(3)}{phone_match.group(4)}"
                        
                        # Формат: 0661234567 або +380661234567
                        phone_match = re.search(r'(\+?3?8?0?)(\d{2})(\d{3})(\d{2})(\d{2})', phone_text.replace('-', '').replace(' ', ''))
                        if phone_match and len(phone_match.group(0).replace('+', '').replace('380', '0')) == 10:
                            phone_digits = phone_match.group(2) + phone_match.group(3) + phone_match.group(4) + phone_match.group(5)
                            return f"+380{phone_digits}"
                            
                except Exception as e:
                    continue
            
            # Якщо не знайшли в основних селекторах, шукаємо в формах
            try:
                form_elements = await page.query_selector_all('form[action*="/phone/"]')
                for form in form_elements:
                    action = await form.get_attribute('action')
                    if action:
                        phone_match = re.search(r'/phone/(\d+)/', action)
                        if phone_match:
                            phone_digits = phone_match.group(1)
                            if len(phone_digits) == 10:
                                return f"+380{phone_digits}"
            except:
                pass
                    
            return None
            
        except Exception as e:
            self.logger.error(f"Помилка витягування телефону: {e}")
            return None

    async def get_location_from_openai(self, description, address_text=""):
        """Визначення локації через OpenAI API"""
        try:
            text_to_analyze = f"{address_text} {description}".lower()
            
            street_patterns = [
                r'вул\.?\s+([а-яёії\s\.\-]+?)[\s,\d]',
                r'вулиця\s+([а-яёії\s\.\-]+?)[\s,\d]',
                r'просп\.?\s+([а-яёії\s\.\-]+?)[\s,\d]',
                r'проспект\s+([а-яёії\s\.\-]+?)[\s,\d]',
                r'бул\.?\s+([а-яёії\s\.\-]+?)[\s,\d]',
                r'бульвар\s+([а-яёії\s\.\-]+?)[\s,\д]'
            ]
            
            for pattern in street_patterns:
                match = re.search(pattern, text_to_analyze)
                if match:
                    street = match.group(1).strip()
                    if len(street) > 3:
                        return f"Вулиця {street.title()}, Чернівці"
            
            prompt = f"""
            Проаналізуй цей текст і визнач адресу нерухомості в Чернівцях.
            
            Адреса: {address_text}
            Опис: {description[:500]}
            
            Поверни ТІЛЬКИ адресу в форматі: "Вулиця Назва, Чернівці" або "Район, Чернівці".
            Якщо конкретної вулиці немає, вкажи район (наприклад: "Центр, Чернівці").
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.1
            )
            
            location = response.choices[0].message.content.strip()
            
            if "чернівці" not in location.lower():
                location += ", Чернівці"
                
            return location
            
        except Exception as e:
            self.logger.error(f"Помилка визначення локації: {e}")
            return "Чернівці"

    async def extract_images(self, page):
        """Витягування зображень оголошення"""
        try:
            images = []
            
            image_selectors = [
                '.fullcard-big-slider img',
                '.fullcard-little-slider img',
                'img[data-lazy]',
                '.item-long-image-wrapper img',
                'a[data-fancybox="gallery"] img'
            ]
            
            await page.wait_for_timeout(2000)
            
            for selector in image_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        src = await element.get_attribute('data-lazy')
                        if not src:
                            src = await element.get_attribute('src')
                        if not src:
                            src = await element.get_attribute('data-src')
                            
                        if src and src.startswith('/storage/'):
                            full_url = f'https://ua.m2bomber.com{src}'
                            if full_url not in images:
                                images.append(full_url)
                        elif src and src.startswith('http'):
                            if src not in images:
                                images.append(src)
                                
                except Exception as e:
                    continue
            
            return images[:10]
            
        except Exception as e:
            self.logger.error(f"Помилка витягування зображень: {e}")
            return []

    async def extract_listing_data(self, page, url):
        """Витягування даних з окремого оголошення"""
        try:
            data = {'url': url}
            
            # Заголовок
            title_selectors = ['h1', '.card-title h1', '.fullcard-title h1']
            for selector in title_selectors:
                try:
                    title_element = await page.query_selector(selector)
                    if title_element:
                        title = await title_element.text_content()
                        if title and len(title.strip()) > 5:
                            data['title'] = title.strip()
                            break
                except:
                    continue
            
            # Ціна
            try:
                price_element = await page.query_selector('.price-full, #fullPriceValueHolder, #priceValueHolder')
                if price_element:
                    price_text = await price_element.text_content()
                    
                    price_match = re.search(r'([\d\s]+)\s*([₴$€])', price_text.replace(' ', ''))
                    if price_match:
                        price_value = int(price_match.group(1).replace(' ', ''))
                        currency_symbol = price_match.group(2)
                        
                        currency_map = {'₴': 'UAH', '$': 'USD', '€': 'EUR'}
                        currency = currency_map.get(currency_symbol, 'UAH')
                        
                        data['price'] = price_value
                        data['currency'] = currency
                        
                        converted = self.convert_currency(price_value, currency)
                        data['price_uah'] = converted['UAH']
                        data['price_usd'] = converted['USD']
                        data['price_eur'] = converted['EUR']
            except Exception as e:
                self.logger.error(f"Помилка витягування ціни: {e}")
            
            # Теги, площа та кімнати
            try:
                tags_elements = await page.query_selector_all('.fullcard-tags li')
                tags = []
                
                for element in tags_elements:
                    text = await element.text_content()
                    if text and text.strip():
                        clean_text = text.strip()
                        tags.append(clean_text)
                        
                        # Витягуємо площу з тегів
                        area_match = re.search(r'(\d+)\s*м²', clean_text)
                        if area_match and 'area' not in data:
                            data['area'] = float(area_match.group(1))
                        
                        # Витягуємо поверх з тегів  
                        floor_match = re.search(r'поверх\s*(\d+)', clean_text)
                        if floor_match and 'floor' not in data:
                            data['floor'] = int(floor_match.group(1))
                            
                        # Витягуємо кількість кімнат
                        rooms_match = re.search(r'(\d+)-кімн', clean_text)
                        if rooms_match and 'rooms' not in data:
                            data['rooms'] = int(rooms_match.group(1))
                
                if tags:
                    data['tags'] = tags
                    self.logger.info(f"🏷️ Знайдено {len(tags)} тегів: {', '.join(tags)}")
                        
            except Exception as e:
                self.logger.error(f"Помилка витягування тегів/площі/поверху: {e}")
            
            # Опис
            try:
                desc_selectors = ['.fullcard-desc', '.item-card-long-desc', '.fullcard-description']
                for selector in desc_selectors:
                    desc_element = await page.query_selector(selector)
                    if desc_element:
                        description = await desc_element.text_content()
                        if description and len(description.strip()) > 10:
                            data['description'] = description.strip()
                            break
            except Exception as e:
                self.logger.error(f"Помилка витягування опису: {e}")
            
            # Адреса
            try:
                address_selectors = ['.fullcard-address', '.item-card-long-address', 'address']
                for selector in address_selectors:
                    address_element = await page.query_selector(selector)
                    if address_element:
                        address = await address_element.text_content()
                        if address and len(address.strip()) > 5:
                            data['address'] = address.strip()
                            break
            except Exception as e:
                self.logger.error(f"Помилка витягування адреси: {e}")
            
            # Телефон
            phone = await self.extract_phone(page)
            if phone:
                data['phone'] = phone
            
            # Зображення
            images = await self.extract_images(page)
            if images:
                data['images'] = images
                self.logger.info(f"🖼️ Знайдено {len(images)} зображень")
            
            # Локація через OpenAI
            if data.get('description') or data.get('address'):
                location = await self.get_location_from_openai(
                    data.get('description', ''),
                    data.get('address', '')
                )
                data['location'] = location
            
            data['parsed_at'] = datetime.now().isoformat()
            
            return data
            
        except Exception as e:
            self.logger.error(f"Помилка витягування даних: {e}")
            return {'url': url, 'error': str(e)}

    async def parse_listing_page(self, url, property_type):
        """Парсинг сторінки зі списком оголошень"""
        try:
            page = await self.context.new_page()
            
            self.logger.info(f"🔍 Завантажуємо сторінку: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)
            
            html_content = await page.content()
            listing_urls = self.extract_listing_urls(html_content)
            
            self.logger.info(f"✅ Знайдено {len(listing_urls)} оголошень")
            
            parsed_listings = []
            
            # Перезапускаємо браузер кожні 10 оголошень для очистки пам'яті
            browser_restart_interval = 10
            
            for i, listing_url in enumerate(listing_urls[:20], 1):
                # Перезапускаємо браузер періодично для очистки пам'яті
                if i > 1 and (i - 1) % browser_restart_interval == 0:
                    self.logger.info(f"🔄 Профілактичний перезапуск браузера після {i-1} оголошень...")
                    try:
                        await self.close_browser()
                        await asyncio.sleep(3)
                        await self.init_browser()
                        self.logger.info("✅ Браузер перезапущено для очистки пам'яті")
                    except Exception as e:
                        self.logger.error(f"❌ Помилка профілактичного перезапуску: {e}")
                
                # Перевіряємо чи оголошення вже існує в базі СПОЧАТКУ
                if self.check_listing_exists(listing_url):
                    self.logger.info(f"⏭️ Пропускаємо (вже існує): {listing_url}")
                    continue
                
                self.logger.info(f"📄 Парсимо оголошення {i}/{len(listing_urls[:20])}: {listing_url}")
                
                # Додаємо обробку помилок браузера з повторними спробами
                max_retries = 3
                listing_page = None
                
                for attempt in range(max_retries):
                    try:
                        listing_page = await self.context.new_page()
                        await listing_page.goto(listing_url, wait_until='domcontentloaded', timeout=30000)
                        await listing_page.wait_for_timeout(2000)
                        
                        listing_data = await self.extract_listing_data(listing_page, listing_url)
                        listing_data['property_type'] = property_type
                        
                        # Зберігаємо в базу та відправляємо в Telegram
                        await self.save_to_database(listing_data)
                        
                        parsed_listings.append(listing_data)
                        
                        await listing_page.close()
                        listing_page = None
                        break  # Успішно - виходимо з циклу повторів
                        
                    except Exception as e:
                        error_msg = str(e)
                        self.logger.error(f"❌ Помилка парсингу {listing_url} (спроба {attempt + 1}/{max_retries}): {error_msg}")
                        
                        # Закриваємо сторінку якщо вона відкрита
                        if listing_page:
                            try:
                                await listing_page.close()
                            except:
                                pass
                            listing_page = None
                        
                        # Перевіряємо чи це помилка пам'яті або браузера
                        memory_errors = ["collected to prevent unbounded heap growth", "object has been collected"]
                        browser_errors = ["playwright", "connection", "_object"]
                        
                        is_memory_error = any(err in error_msg.lower() for err in memory_errors)
                        is_browser_error = any(err in error_msg.lower() for err in browser_errors)
                        
                        if is_memory_error or is_browser_error:
                            self.logger.warning("🔄 Перезапускаємо браузер через помилку пам'яті/браузера...")
                            try:
                                await self.close_browser()
                                await asyncio.sleep(3)
                                await self.init_browser()
                                self.logger.info("✅ Браузер перезапущено")
                            except Exception as browser_error:
                                self.logger.error(f"❌ Помилка перезапуску браузера: {browser_error}")
                        
                        if attempt == max_retries - 1:
                            self.logger.error(f"💥 Не вдалося спарсити {listing_url} після {max_retries} спроб")
                        else:
                            await asyncio.sleep(3)  # Пауза перед повтором
                
                await asyncio.sleep(1)
            
            await page.close()
            return parsed_listings
            
        except Exception as e:
            self.logger.error(f"Помилка парсингу сторінки {url}: {e}")
            return []

    async def parse_all_m2bomber_urls(self, urls_data):
        """Парсинг всіх M2Bomber URL"""
        try:
            await self.get_exchange_rates()
            await self.init_browser()
            
            all_parsed_data = []
            
            m2bomber_urls = [item for item in urls_data if item.get('site') == 'M2BOMBER']
            
            self.logger.info(f"🎯 Знайдено {len(m2bomber_urls)} M2Bomber URL для парсингу")
            
            for url_item in m2bomber_urls:
                url = url_item['url']
                property_type = url_item.get('type', 'unknown')
                
                self.logger.info(f"\n🚀 Парсимо M2Bomber: {property_type} - {url}")
                
                listings = await self.parse_listing_page(url, property_type)
                
                self.logger.info(f"✅ Отримано {len(listings)} оголошень з {url}")
                all_parsed_data.extend(listings)
                
                await asyncio.sleep(2)
            
            await self.close_browser()
            
            self.logger.info(f"\n🎉 Всього спарсено M2Bomber оголошень: {len(all_parsed_data)}")
            return all_parsed_data
            
        except Exception as e:
            self.logger.error(f"Критична помилка M2Bomber парсера: {e}")
            if self.browser:
                await self.close_browser()
            return [] 