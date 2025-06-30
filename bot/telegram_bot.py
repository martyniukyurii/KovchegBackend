import asyncio
import os
from aiogram import Bot, types
from aiogram.types import InputMediaPhoto
from datetime import datetime
import sys
from pathlib import Path
from dotenv import load_dotenv

# Завантажуємо змінні середовища
load_dotenv()

# Додаємо tools до Python path для логера
sys.path.append(str(Path(__file__).parent.parent / "tools"))
from logger import Logger

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
            
            # Отримуємо зображення
            images = listing_data.get('images', [])
            
            if images:
                # Відправляємо з фото
                if len(images) == 1:
                    # Одне фото
                    await self.bot.send_photo(
                        chat_id=channel_id,
                        photo=images[0],
                        caption=message_text,
                        parse_mode='HTML'
                    )
                else:
                    # Кілька фото (до 10)
                    media_group = []
                    for i, image_url in enumerate(images[:10]):
                        if i == 0:
                            # Перше фото з підписом
                            media_group.append(
                                InputMediaPhoto(media=image_url, caption=message_text, parse_mode='HTML')
                            )
                        else:
                            # Інші фото без підпису
                            media_group.append(InputMediaPhoto(media=image_url))
                    
                    await self.bot.send_media_group(
                        chat_id=channel_id,
                        media=media_group
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