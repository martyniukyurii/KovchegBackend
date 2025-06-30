import asyncio
import os
import aiohttp
from aiogram import Bot, types
from aiogram.types import InputMediaPhoto, InputFile
from datetime import datetime
import sys
from pathlib import Path
from dotenv import load_dotenv
import io

# Завантажуємо змінні середовища
load_dotenv()

# Додаємо кореневу директорію до Python path
sys.path.append(str(Path(__file__).parent.parent))
from tools.logger import Logger

class TelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '6211838784:AAGbiyen0yYKXSAlUibHq-wMnEfPC34mawo')
        self.bot = Bot(token=self.bot_token)
        self.logger = Logger()
        
        # Канали для різних типів нерухомості
        self.channels = {
            'commerce': '@comodc',  # Комерція
            'prodazh': '@comodmodmc',  # Продажі
            'zemlya': '@comodmodmdfdfc',  # Земельні ділянки
            'orenda': '@comodcv'  # Оренда
        }
    
    def format_price(self, listing_data):
        """Форматування ціни"""
        price = listing_data.get('price')
        currency = listing_data.get('currency', 'UAH')
        
        if not price:
            return "Ціна не вказана"
        
        if currency == 'UAH':
            return f"💰 {price:,} грн".replace(',', ' ')
        elif currency == 'USD':
            return f"💰 ${price:,}".replace(',', ' ')
        elif currency == 'EUR':
            return f"💰 €{price:,}".replace(',', ' ')
        else:
            return f"💰 {price:,} {currency}".replace(',', ' ')
    
    def format_listing_message(self, listing_data):
        """Форматування повідомлення для Telegram"""
        title = listing_data.get('title', 'Без назви')
        price = self.format_price(listing_data)
        phone = listing_data.get('phone', 'Не вказано')
        location = listing_data.get('location', listing_data.get('address', 'Не вказано'))
        area = listing_data.get('area')
        floor = listing_data.get('floor')
        tags = listing_data.get('tags', [])
        url = listing_data.get('url', '')
        
        # Основна інформація
        message = f"🏠 <b>{title}</b>\n\n"
        message += f"{price}\n"
        
        if phone and phone != 'Не вказано':
            message += f"📞 {phone}\n"
        
        if location and location != 'Не вказано':
            message += f"📍 {location}\n"
        
        # Додаткова інформація
        details = []
        if area:
            details.append(f"📐 {area} м²")
        if floor:
            details.append(f"🏢 {floor} поверх")
        
        if details:
            message += f"\n{' • '.join(details)}\n"
        
        # Теги (перші 3-4)
        if tags:
            relevant_tags = [tag for tag in tags[:4] if not any(x in tag.lower() for x in ['підняти', 'топ', 'приватна особа'])]
            if relevant_tags:
                message += f"\n🏷️ {' • '.join(relevant_tags)}\n"
        
        # Посилання
        if url:
            message += f"\n🔗 <a href='{url}'>Переглянути оголошення</a>"
        
        message += f"\n\n⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        return message
    
    def is_valid_image_url(self, url):
        """Перевіряємо чи є URL зображення валідним"""
        if not url or not isinstance(url, str):
            return False
        
        # Перевіряємо чи починається з http/https
        if not url.startswith(('http://', 'https://')):
            return False
            
        url_lower = url.lower()
        
        # Перевіряємо чи закінчується на відоме розширення зображення
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
        if any(ext in url_lower for ext in image_extensions):
            return True
        
        # Перевіряємо відомі домени зображень та їх специфічні шляхи
        if 'olxcdn.com' in url_lower and ('/image' in url_lower or '/files/' in url_lower):
            return True
            
        if 'm2bomber.com' in url_lower and ('/storage/' in url_lower or '/images/' in url_lower):
            return True
            
        if 'apollo-ireland.akamaized.net' in url_lower:
            return True
            
        return False

    async def download_image(self, url):
        """Завантажуємо зображення для Telegram"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'uk-UA,uk;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Додаємо Referer для OLX
            if 'olx' in url.lower():
                headers['Referer'] = 'https://www.olx.ua/'
            elif 'm2bomber' in url.lower():
                headers['Referer'] = 'https://ua.m2bomber.com/'
            
            # Відключаємо SSL перевірку для проблемних сайтів
            ssl = False if any(domain in url.lower() for domain in ['m2bomber.com', 'olxcdn.com']) else None
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10, ssl=ssl) as response:
                    if response.status == 200:
                        content = await response.read()
                        # Перевіряємо чи це дійсно зображення
                        content_type = response.headers.get('content-type', '').lower()
                        if content_type.startswith('image/'):
                            return io.BytesIO(content)
            return None
        except Exception as e:
            self.logger.warning(f"⚠️ Не вдалося завантажити зображення {url}: {e}")
            return None

    async def send_to_channel(self, listing_data):
        """Відправка оголошення до відповідного каналу"""
        try:
            property_type = listing_data.get('property_type', 'unknown')
            
            # Визначаємо канал
            channel_id = self.channels.get(property_type)
            if not channel_id:
                self.logger.warning(f"⚠️ Невідомий тип нерухомості: {property_type}")
                return False
            
            # Форматуємо повідомлення
            message_text = self.format_listing_message(listing_data)
            
            # Отримуємо та фільтруємо зображення
            images = listing_data.get('images', [])
            valid_images = [img for img in images if self.is_valid_image_url(img)][:10]  # Максимум 10 зображень
            
            if valid_images:
                try:
                    # Завантажуємо зображення
                    downloaded_images = []
                    for i, image_url in enumerate(valid_images[:3]):  # Максимум 3 зображення для швидкості
                        image_data = await self.download_image(image_url)
                        if image_data:
                            downloaded_images.append(image_data)
                    
                    if downloaded_images:
                        # Відправляємо з завантаженими фото
                        if len(downloaded_images) == 1:
                            # Одне фото
                            await self.bot.send_photo(
                                chat_id=channel_id,
                                photo=InputFile(downloaded_images[0]),
                                caption=message_text,
                                parse_mode='HTML'
                            )
                        else:
                            # Кілька фото
                            media_group = []
                            for i, image_data in enumerate(downloaded_images):
                                if i == 0:
                                    # Перше фото з підписом
                                    media_group.append(
                                        InputMediaPhoto(media=InputFile(image_data), caption=message_text, parse_mode='HTML')
                                    )
                                else:
                                    # Інші фото без підпису
                                    media_group.append(InputMediaPhoto(media=InputFile(image_data)))
                            
                            await self.bot.send_media_group(
                                chat_id=channel_id,
                                media=media_group
                            )
                    else:
                        # Якщо не вдалося завантажити жодне зображення
                        raise Exception("Не вдалося завантажити зображення")
                        
                except Exception as photo_error:
                    # Якщо помилка з фото, відправляємо без них
                    self.logger.warning(f"⚠️ Помилка відправки фото: {photo_error}. Відправляємо без зображень.")
                    await self.bot.send_message(
                        chat_id=channel_id,
                        text=message_text,
                        parse_mode='HTML',
                        disable_web_page_preview=False
                    )
            else:
                # Відправляємо без фото
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=message_text,
                    parse_mode='HTML',
                    disable_web_page_preview=False
                )
            
            self.logger.info(f"📤 Відправлено в канал {channel_id}: {listing_data.get('title', 'Без назви')}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Помилка відправки в Telegram: {e}")
            return False
    
    async def close(self):
        """Закриття сесії бота"""
        try:
            session = await self.bot.get_session()
            await session.close()
        except:
            pass 