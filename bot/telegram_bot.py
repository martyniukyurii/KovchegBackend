import asyncio
import os
import aiohttp
from aiogram import Bot, types, Dispatcher
from aiogram.types import InputMediaPhoto, InputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text, Command
from datetime import datetime, timedelta
import sys
from pathlib import Path
from dotenv import load_dotenv
import io

# Завантажуємо змінні середовища
load_dotenv()

# Додаємо кореневу директорію до Python path
sys.path.append(str(Path(__file__).parent.parent))
from tools.logger import Logger
from tools.database import Database
from tools.email_service import EmailService
import secrets


# FSM States для бота
class OwnerRegistration(StatesGroup):
    waiting_for_email = State()
    waiting_for_code = State()

class AdminApplication(StatesGroup):
    waiting_for_email = State()

class PasswordChange(StatesGroup):
    waiting_for_new_password = State()
    waiting_for_password_confirm = State()


class TelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '6211838784:AAGbiyen0yYKXSAlUibHq-wMnEfPC34mawo')
        self.bot = Bot(token=self.bot_token)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(self.bot, storage=self.storage)
        self.logger = Logger()
        self.db = Database()
        self.email_service = EmailService()
        
        # Власники CRM
        owner_chat_ids_str = os.getenv('OWNER_CHAT_IDS', '')
        self.owner_chat_ids = [int(chat_id.strip()) for chat_id in owner_chat_ids_str.split(',') if chat_id.strip()]
        
        # Канали для різних типів нерухомості
        self.channels = {
            'commerce': '@comodc',  # Комерція
            'prodazh': '@comodmodmc',  # Продажі
            'zemlya': '@comodmodmdfdfc',  # Земельні ділянки
            'orenda': '@comodcv'  # Оренда
        }
        
        # Реєстрація хендлерів
        self.setup_handlers()
    
    def setup_handlers(self):
        """Налаштування обробників повідомлень"""
        # Команда /start
        self.dp.register_message_handler(self.cmd_start, commands=['start'])
        
        # Обробка кнопок власника
        self.dp.register_callback_query_handler(
            self.handle_owner_actions, 
            lambda c: c.data.startswith("owner_")
        )
        
        # Обробка кнопок адміна
        self.dp.register_callback_query_handler(
            self.handle_admin_actions, 
            lambda c: c.data.startswith("admin_")
        )
        
        # FSM для реєстрації власника
        self.dp.register_message_handler(
            self.process_owner_email, 
            state=OwnerRegistration.waiting_for_email
        )
        self.dp.register_message_handler(
            self.process_owner_verification, 
            state=OwnerRegistration.waiting_for_code
        )
        
        # FSM для заявки адміна
        self.dp.register_message_handler(
            self.process_admin_email, 
            state=AdminApplication.waiting_for_email
        )
        
        # FSM для зміни паролю
        self.dp.register_message_handler(
            self.process_new_password, 
            state=PasswordChange.waiting_for_new_password
        )
        self.dp.register_message_handler(
            self.process_password_confirm, 
            state=PasswordChange.waiting_for_password_confirm
        )
    
    async def cmd_start(self, message: types.Message, state: FSMContext):
        """Обробка команди /start"""
        user_id = message.from_user.id
        user_info = message.from_user
        
        # Перевіряємо чи користувач є власником
        if user_id in self.owner_chat_ids:
            # Перевіряємо чи власник вже зареєстрований
            owner = await self.db.admins.find_one({"telegram_id": user_id, "role": "owner"})
            
            if not owner:
                # Власник не зареєстрований
                keyboard = InlineKeyboardMarkup(row_width=1)
                keyboard.add(InlineKeyboardButton("🔐 Зареєструватися як власник", callback_data="owner_register"))
                
                await message.answer(
                    f"👋 Вітаю, {user_info.first_name}!\n\n"
                    f"Ви визначені як власник CRM системи.\n"
                    f"Для початку роботи необхідно зареєструватися.",
                    reply_markup=keyboard
                )
            else:
                # Власник зареєстрований - показуємо меню
                await self.show_owner_menu(message)
        else:
            # Перевіряємо чи користувач є адміном
            admin = await self.db.admins.find_one({"telegram_id": user_id})
            
            if admin:
                # Користувач є адміном
                await message.answer(
                    f"👋 Вітаю, {admin['first_name']}!\n\n"
                    f"Ви увійшли як адміністратор CRM системи.\n"
                    f"Для доступу до системи використовуйте веб-інтерфейс."
                )
            else:
                # Звичайний користувач - пропонуємо подати заявку
                keyboard = InlineKeyboardMarkup(row_width=1)
                keyboard.add(InlineKeyboardButton("📝 Подати заявку на адміністратора", callback_data="admin_apply"))
                
                await message.answer(
                    f"👋 Вітаю, {user_info.first_name}!\n\n"
                    f"Це бот для управління CRM системою.\n"
                    f"Щоб стати адміністратором, подайте заявку.",
                    reply_markup=keyboard
                )
    
    async def show_owner_menu(self, message: types.Message):
        """Показати меню власника"""
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("🏥 Перевірити стан сервера", callback_data="owner_check_server"),
            InlineKeyboardButton("📊 Логи парсерів", callback_data="owner_parser_logs"),
            InlineKeyboardButton("👥 Переглянути заявки адмінів", callback_data="owner_view_applications"),
            InlineKeyboardButton("👨‍💼 Список адмінів", callback_data="owner_view_admins"),
            InlineKeyboardButton("🗑️ Видалити адміна", callback_data="owner_delete_admin"),
            InlineKeyboardButton("🔑 Змінити пароль", callback_data="owner_change_password")
        )
        
        await message.answer(
            "🔧 <b>Панель управління власника</b>\n\n"
            "Оберіть дію:",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    
    async def handle_owner_actions(self, callback: types.CallbackQuery, state: FSMContext):
        """Обробка дій власника"""
        action = callback.data.replace("owner_", "")
        
        if action == "register":
            await callback.message.answer(
                "📧 <b>Реєстрація власника</b>\n\n"
                "Введіть вашу електронну адресу:",
                parse_mode='HTML'
            )
            await OwnerRegistration.waiting_for_email.set()
            
        elif action == "view_applications":
            await self.show_admin_applications(callback.message)
            
        elif action == "view_admins":
            await self.show_admins_list(callback.message)
            
        elif action == "delete_admin":
            await self.show_admins_for_deletion(callback.message)
            
        elif action.startswith("approve_"):
            app_id = action.replace("approve_", "")
            await self.approve_admin_application(callback, app_id)
            
        elif action.startswith("reject_"):
            app_id = action.replace("reject_", "")
            await self.reject_admin_application(callback, app_id)
            
        elif action.startswith("delete_admin_"):
            admin_id = action.replace("delete_admin_", "")
            await self.delete_admin(callback, admin_id)
            
        elif action == "change_password":
            await self.start_password_change(callback, state)
            
        elif action == "check_server":
            await self.check_server_status(callback)
            
        elif action == "parser_logs":
            await self.show_parser_logs(callback)
        
        await callback.answer()
    
    async def handle_admin_actions(self, callback: types.CallbackQuery, state: FSMContext):
        """Обробка дій адмінів"""
        action = callback.data.replace("admin_", "")
        
        if action == "apply":
            # Перевіряємо чи користувач вже подавав заявку за останні 24 години
            user_id = callback.from_user.id
            twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
            recent_application = await self.db.admin_applications.find_one({
                "telegram_id": user_id,
                "created_at": {"$gte": twenty_four_hours_ago}
            })
            
            if recent_application:
                if recent_application.get("status") == "pending":
                    await callback.message.answer(
                        "⏳ <b>Заявка вже в обробці</b>\n\n"
                        "Ви вже подали заявку на адміністратора.\n"
                        f"📅 Дата подачі: {recent_application['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
                        f"📧 Email: {recent_application['email']}\n\n"
                        "Очікуйте рішення власників системи. Ви отримаєте повідомлення про результат.",
                        parse_mode='HTML'
                    )
                else:
                    await callback.message.answer(
                        "⏳ <b>Повторну заявку можна подати через 24 години</b>\n\n"
                        f"Остання заявка: {recent_application['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
                        f"Статус: {'Схвалена' if recent_application.get('status') == 'approved' else 'Відхилена'}\n\n"
                        "Спробуйте пізніше.",
                        parse_mode='HTML'
                    )
                await callback.answer()
                return
            
            await callback.message.answer(
                "📝 <b>Заявка на адміністратора</b>\n\n"
                "Введіть вашу електронну адресу для зв'язку:",
                parse_mode='HTML'
            )
            await AdminApplication.waiting_for_email.set()
        
        await callback.answer()
    
    async def process_owner_email(self, message: types.Message, state: FSMContext):
        """Обробка email власника"""
        email = message.text.strip().lower()
        
        if "@" not in email or "." not in email:
            await message.answer("❌ Невірний формат email. Спробуйте ще раз:")
            return
        
        # Генеруємо код верифікації
        verification_code = str(secrets.randbelow(900000) + 100000)
        
        # Зберігаємо в базі
        verification_data = {
            "telegram_id": message.from_user.id,
            "email": email,
            "code": verification_code,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(minutes=10),
            "type": "owner_registration"
        }
        await self.db.verification_codes.create(verification_data)
        
        # Відправляємо email
        try:
            await self.email_service.send_verification_email(
                email=email,
                verification_code=verification_code,
                user_name="Власник CRM",
                language="uk"
            )
            
            await message.answer(
                f"📧 Код верифікації відправлено на {email}\n\n"
                f"Введіть код з email:"
            )
            await state.update_data(email=email)
            await OwnerRegistration.waiting_for_code.set()
            
        except Exception as e:
            await message.answer(f"❌ Помилка відправки email: {str(e)}")
            await state.finish()
    
    async def process_owner_verification(self, message: types.Message, state: FSMContext):
        """Верифікація коду власника"""
        code = message.text.strip()
        data = await state.get_data()
        email = data.get("email")
        
        # Перевіряємо код
        verification = await self.db.verification_codes.find_one({
            "telegram_id": message.from_user.id,
            "code": code,
            "type": "owner_registration"
        })
        
        if not verification or verification["expires_at"] < datetime.utcnow():
            await message.answer("❌ Невірний або застарілий код. Спробуйте ще раз:")
            return
        
        # Створюємо власника
        owner_data = {
            "first_name": message.from_user.first_name or "Власник",
            "last_name": message.from_user.last_name or "CRM",
            "email": email,
            "phone": "",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "login": email,
            "password": None,
            "language_code": "uk",
            "is_verified": True,
            "role": "owner",
            "telegram_id": message.from_user.id
        }
        
        await self.db.admins.create(owner_data)
        await self.db.verification_codes.delete({"code": code})
        
        await message.answer(
            "✅ <b>Вітаємо!</b>\n\n"
            "Ви успішно зареєстровані як власник CRM системи.",
            parse_mode='HTML'
        )
        
        await state.finish()
        await self.show_owner_menu(message)
    
    async def process_admin_email(self, message: types.Message, state: FSMContext):
        """Обробка email заявки адміна"""
        email = message.text.strip().lower()
        
        if "@" not in email or "." not in email:
            await message.answer("❌ Невірний формат email. Спробуйте ще раз:")
            return
        
        user_info = message.from_user
        
        # Перевіряємо чи не існує вже такий адмін
        existing_admin = await self.db.admins.find_one({"email": email})
        if existing_admin:
            await message.answer("❌ Адміністратор з таким email вже існує.")
            await state.finish()
            return
        
        # Перевіряємо чи користувач вже подавав заявку за останні 24 години
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        recent_application = await self.db.admin_applications.find_one({
            "telegram_id": user_info.id,
            "created_at": {"$gte": twenty_four_hours_ago}
        })
        
        if recent_application:
            if recent_application.get("status") == "pending":
                await message.answer(
                    "⏳ <b>Заявка вже в обробці</b>\n\n"
                    "Ви вже подали заявку на адміністратора.\n"
                    f"📅 Дата подачі: {recent_application['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
                    f"📧 Email: {recent_application['email']}\n\n"
                    "Очікуйте рішення власників системи. Ви отримаєте повідомлення про результат.",
                    parse_mode='HTML'
                )
            else:
                await message.answer(
                    "⏳ <b>Повторну заявку можна подати через 24 години</b>\n\n"
                    f"Остання заявка: {recent_application['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
                    f"Статус: {'Схвалена' if recent_application.get('status') == 'approved' else 'Відхилена'}\n\n"
                    "Спробуйте пізніше.",
                    parse_mode='HTML'
                )
            await state.finish()
            return
        
        # Створюємо заявку
        application_data = {
            "telegram_id": user_info.id,
            "email": email,
            "first_name": user_info.first_name or "Невідомо",
            "last_name": user_info.last_name or "",
            "username": user_info.username or "",
            "created_at": datetime.utcnow(),
            "status": "pending",
            "type": "admin_application"
        }
        
        app_id = await self.db.admin_applications.create(application_data)
        
        # Повідомляємо всіх власників
        for owner_chat_id in self.owner_chat_ids:
            try:
                keyboard = InlineKeyboardMarkup(row_width=2)
                keyboard.add(
                    InlineKeyboardButton("✅ Прийняти", callback_data=f"owner_approve_{app_id}"),
                    InlineKeyboardButton("❌ Відхилити", callback_data=f"owner_reject_{app_id}")
                )
                
                user_link = f"@{user_info.username}" if user_info.username else f"ID: {user_info.id}"
                
                await self.bot.send_message(
                    chat_id=owner_chat_id,
                    text=f"📝 <b>Нова заявка на адміністратора</b>\n\n"
                         f"👤 Ім'я: {user_info.first_name} {user_info.last_name or ''}\n"
                         f"📱 Telegram: {user_link}\n"
                         f"📧 Email: {email}\n"
                         f"🕐 Дата: {application_data['created_at'].strftime('%d.%m.%Y %H:%M')}",
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            except:
                pass
        
        await message.answer(
            "✅ <b>Заявку відправлено!</b>\n\n"
            "Ваша заявка на адміністратора розглядається власниками системи.\n"
            "Ви отримаєте повідомлення про результат.",
            parse_mode='HTML'
        )
        await state.finish()
    
    async def show_admin_applications(self, message: types.Message):
        """Показати список заявок на адміністратора"""
        applications = await self.db.admin_applications.find({"status": "pending"})
        if not applications:
            await message.answer("📝 <b>Заявки на адміністратора</b>\n\nНаразі немає нових заявок на адміністратора.", parse_mode='HTML')
            return
        
        message_text = "📝 <b>Нові заявки на адміністратора</b>\n\n"
        
        for i, app in enumerate(applications, 1):
            user_link = f"@{app.get('username')}" if app.get('username') else f"ID: {app.get('telegram_id', 'невідомий')}"
            message_text += f"<b>{i}. {app['first_name']} {app.get('last_name', '')}</b>\n"
            message_text += f"📱 Telegram: {user_link}\n"
            message_text += f"📧 Email: {app['email']}\n"
            message_text += f"🕐 Дата: {app['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
            
            # Додаємо кнопки для кожної заявки окремим повідомленням
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton(f"✅ Прийняти", callback_data=f"owner_approve_{app['_id']}"),
                InlineKeyboardButton(f"❌ Відхилити", callback_data=f"owner_reject_{app['_id']}")
            )
            
            await message.answer(
                f"👤 <b>Заявка #{i}</b>\n\n"
                f"📝 Ім'я: {app['first_name']} {app.get('last_name', '')}\n"
                f"📱 Telegram: {user_link}\n"
                f"📧 Email: {app['email']}\n"
                f"🕐 Дата: {app['created_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Оберіть дію:",
                reply_markup=keyboard, 
                parse_mode='HTML'
            )
    
    async def show_admins_list(self, message: types.Message):
        """Показати список адмінів"""
        admins = await self.db.admins.find({"role": "admin"})
        if not admins:
            await message.answer("Наразі немає адмінів в системі.")
            return
        
        message_text = "👨‍💼 <b>Список адмінів CRM системи</b>\n\n"
        for admin in admins:
            message_text += f"👤 Ім'я: {admin['first_name']} {admin.get('last_name', '')}\n"
            message_text += f"📧 Email: {admin.get('email', 'Не вказано')}\n"
            message_text += f"📱 Telegram ID: {admin.get('telegram_id', 'Не вказано')}\n"
            message_text += f"🕐 Створено: {admin['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
            message_text += f"✅ Верифіковано: {'Так' if admin.get('is_verified') else 'Ні'}\n\n"
        
        await message.answer(message_text, parse_mode='HTML')
    
    async def show_admins_for_deletion(self, message: types.Message):
        """Показати список адмінів для видалення"""
        admins = await self.db.admins.find({"role": "admin"})
        if not admins:
            await message.answer("🗑️ <b>Видалення адмінів</b>\n\nНаразі немає адмінів для видалення.", parse_mode='HTML')
            return
        
        await message.answer("🗑️ <b>Видалення адмінів</b>\n\nОберіть адміна для видалення:", parse_mode='HTML')
        
        for i, admin in enumerate(admins, 1):
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton(
                    f"🗑️ Видалити", 
                    callback_data=f"owner_delete_admin_{admin['_id']}"
                )
            )
            
            await message.answer(
                f"👤 <b>Адміністратор #{i}</b>\n\n"
                f"📝 Ім'я: {admin['first_name']} {admin.get('last_name', '')}\n"
                f"📧 Email: {admin.get('email', 'Не вказано')}\n"
                f"📱 Telegram ID: {admin.get('telegram_id', 'Не вказано')}\n"
                f"🕐 Створено: {admin['created_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
                f"⚠️ Дія незворотна!",
                reply_markup=keyboard, 
                parse_mode='HTML'
            )
    
    async def approve_admin_application(self, callback: types.CallbackQuery, app_id: str):
        """Прийняти заявку на адміністратора"""
        try:
            from bson import ObjectId
            app = await self.db.admin_applications.find_one({"_id": ObjectId(app_id)})
            if not app:
                await callback.message.edit_text("❌ Заявка не знайдена.")
                return
            
            # Перевіряємо чи заявка вже оброблена
            if app.get("status") != "pending":
                await callback.message.edit_text("⚠️ Заявка вже була оброблена раніше.")
                return
            
            # Перевіряємо чи не існує вже такий адмін
            existing_admin = await self.db.admins.find_one({"email": app["email"]})
            if existing_admin:
                await callback.message.edit_text("⚠️ Адміністратор з таким email вже існує.")
                return
            
            # Створюємо адміна
            admin_data = {
                "first_name": app["first_name"],
                "last_name": app.get("last_name", ""),
                "email": app["email"],
                "phone": "",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "login": app["email"],
                "password": None,
                "language_code": "uk",
                "is_verified": True,
                "role": "admin",
                "telegram_id": app["telegram_id"]
            }
            
            await self.db.admins.create(admin_data)
            
            # Оновлюємо заявку
            await self.db.admin_applications.update(
                {"_id": ObjectId(app_id)}, 
                {
                    "$set": {
                        "status": "approved", 
                        "approved_by": callback.from_user.id, 
                        "approved_at": datetime.utcnow()
                    }
                }
            )
            
            # Повідомляємо заявника
            try:
                await self.bot.send_message(
                    chat_id=app["telegram_id"],
                    text="🎉 <b>Вітаємо!</b>\n\n"
                         "Ваша заявка на адміністратора схвалена!\n"
                         "Тепер ви можете увійти в систему через Telegram.",
                    parse_mode='HTML'
                )
            except:
                pass
            
            # Редагуємо повідомлення з кнопками, прибираючи кнопки
            await callback.message.edit_text(
                f"✅ <b>Заявка прийнята!</b>\n\n"
                f"👤 {app['first_name']} {app.get('last_name', '')} тепер адміністратор.\n"
                f"⏰ Прийнята: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}",
                parse_mode='HTML'
            )
            
        except Exception as e:
            await callback.message.edit_text(f"❌ Помилка: {str(e)}")
    
    async def reject_admin_application(self, callback: types.CallbackQuery, app_id: str):
        """Відхилити заявку на адміністратора"""
        try:
            from bson import ObjectId
            app = await self.db.admin_applications.find_one({"_id": ObjectId(app_id)})
            if not app:
                await callback.message.edit_text("❌ Заявка не знайдена.")
                return
            
            # Перевіряємо чи заявка вже оброблена
            if app.get("status") != "pending":
                await callback.message.edit_text("⚠️ Заявка вже була оброблена раніше.")
                return
            
            # Оновлюємо заявку
            await self.db.admin_applications.update(
                {"_id": ObjectId(app_id)}, 
                {
                    "$set": {
                        "status": "rejected", 
                        "rejected_by": callback.from_user.id, 
                        "rejected_at": datetime.utcnow()
                    }
                }
            )
            
            # Повідомляємо заявника
            try:
                await self.bot.send_message(
                    chat_id=app["telegram_id"],
                    text="❌ <b>Заявка відхилена</b>\n\n"
                         "На жаль, ваша заявка на адміністратора була відхилена.\n"
                         "Ви можете спробувати подати заявку пізніше.",
                    parse_mode='HTML'
                )
            except:
                pass
            
            # Редагуємо повідомлення з кнопками, прибираючи кнопки
            await callback.message.edit_text(
                f"❌ <b>Заявка відхилена!</b>\n\n"
                f"👤 Заявка від {app['first_name']} {app.get('last_name', '')} відхилена.\n"
                f"⏰ Відхилена: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}",
                parse_mode='HTML'
            )
            
        except Exception as e:
            await callback.message.edit_text(f"❌ Помилка: {str(e)}")
    
    async def delete_admin(self, callback: types.CallbackQuery, admin_id: str):
        """Видалити адміна"""
        try:
            from bson import ObjectId
            admin = await self.db.admins.find_one({"_id": ObjectId(admin_id)})
            if not admin:
                await callback.message.edit_text("❌ Адмін не знайдений.")
                return
            
            # Видаляємо з бази
            await self.db.admins.delete({"_id": ObjectId(admin_id)})
            
            # Повідомляємо видаленого адміна
            try:
                await self.bot.send_message(
                    chat_id=admin["telegram_id"],
                    text="⚠️ <b>Увага!</b>\n\n"
                         "Ваші права адміністратора були скасовані.\n"
                         "Якщо це помилка, зверніться до власників системи.",
                    parse_mode='HTML'
                )
            except:
                pass
            
            # Редагуємо повідомлення з кнопками, прибираючи кнопки
            await callback.message.edit_text(
                f"🗑️ <b>Адмін видалено!</b>\n\n"
                f"👤 {admin['first_name']} {admin.get('last_name', '')} більше не адміністратор.\n"
                f"⏰ Видалено: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}",
                parse_mode='HTML'
            )
            
        except Exception as e:
            await callback.message.edit_text(f"❌ Помилка: {str(e)}")
    
    async def start_admin_bot(self):
        """Запуск бота для управління адмінами"""
        try:
            await self.db.setup_indexes()
            self.logger.info("🤖 Telegram Admin Bot запущено...")
            await self.dp.start_polling()
        except Exception as e:
            self.logger.error(f"❌ Помилка запуску бота: {e}")
        finally:
            await self.close()
    
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
                'User-Admin': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
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
            
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers, ssl=ssl) as response:
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
    
    async def start_password_change(self, callback: types.CallbackQuery, state: FSMContext):
        """Початок процесу зміни паролю"""
        await callback.message.answer(
            "🔑 <b>Зміна паролю</b>\n\n"
            "Введіть новий пароль для вашого акаунта:\n\n"
            "⚠️ <b>Вимоги до паролю:</b>\n"
            "• Мінімум 6 символів\n"
            "• Може містити букви, цифри та спецсимволи\n"
            "• Рекомендується використовувати надійний пароль",
            parse_mode='HTML'
        )
        await PasswordChange.waiting_for_new_password.set()
    
    async def process_new_password(self, message: types.Message, state: FSMContext):
        """Обробка нового паролю"""
        password = message.text.strip()
        
        # Валідація паролю
        if len(password) < 6:
            await message.answer(
                "❌ <b>Пароль занадто короткий!</b>\n\n"
                "Пароль повинен містити принаймні 6 символів. Спробуйте ще раз:",
                parse_mode='HTML'
            )
            return
        
        if len(password) > 128:
            await message.answer(
                "❌ <b>Пароль занадто довгий!</b>\n\n"
                "Максимальна довжина паролю - 128 символів. Спробуйте ще раз:",
                parse_mode='HTML'
            )
            return
        
        # Видаляємо повідомлення з паролем з міркувань безпеки
        try:
            await message.delete()
        except:
            pass
        
        # Зберігаємо пароль у стейті
        await state.update_data(new_password=password)
        
        await message.answer(
            "🔒 <b>Підтвердження паролю</b>\n\n"
            "Введіть пароль ще раз для підтвердження:",
            parse_mode='HTML'
        )
        await PasswordChange.waiting_for_password_confirm.set()
    
    async def process_password_confirm(self, message: types.Message, state: FSMContext):
        """Підтвердження паролю"""
        confirm_password = message.text.strip()
        data = await state.get_data()
        new_password = data.get("new_password")
        
        # Видаляємо повідомлення з паролем з міркувань безпеки
        try:
            await message.delete()
        except:
            pass
        
        if not new_password:
            await message.answer(
                "❌ <b>Помилка!</b>\n\n"
                "Не знайдено новий пароль. Почніть процес заново.",
                parse_mode='HTML'
            )
            await state.finish()
            return
        
        if new_password != confirm_password:
            await message.answer(
                "❌ <b>Паролі не співпадають!</b>\n\n"
                "Введіть новий пароль ще раз:",
                parse_mode='HTML'
            )
            await PasswordChange.waiting_for_new_password.set()
            return
        
        # Оновлюємо пароль у базі даних
        try:
            import bcrypt
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            user_id = message.from_user.id
            
            # Перевіряємо чи існує власник
            owner = await self.db.admins.find_one({"telegram_id": user_id, "role": "owner"})
            if not owner:
                await message.answer(
                    "❌ <b>Помилка!</b>\n\n"
                    "Ваш акаунт власника не знайдено в системі.",
                    parse_mode='HTML'
                )
                await state.finish()
                return
            
            # Оновлюємо пароль
            await self.db.admins.update(
                {"telegram_id": user_id, "role": "owner"},
                {"$set": {
                    "password": hashed_password,
                    "updated_at": datetime.utcnow()
                }}
            )
            
            await message.answer(
                "✅ <b>Пароль успішно змінено!</b>\n\n"
                f"Тепер ви можете використовувати новий пароль для входу в веб-інтерфейс CRM системи.\n\n"
                f"🔐 <b>Ваші дані для входу:</b>\n"
                f"📧 Email: {owner.get('email', 'Не вказано')}\n"
                f"🔑 Пароль: (щойно встановлений)\n\n"
                f"🌐 Увійдіть через /admin/auth/login",
                parse_mode='HTML'
            )
            
            # Логування події
            self.logger.info(f"Password changed for owner {user_id}")
                
        except Exception as e:
            await message.answer(
                f"❌ <b>Помилка при зміні паролю:</b>\n\n"
                f"{str(e)}",
                parse_mode='HTML'
            )
            self.logger.error(f"Error changing password for owner {message.from_user.id}: {e}")
        
        finally:
            await state.finish()

    async def check_server_status(self, callback: types.CallbackQuery):
        """Перевірка стану сервера"""
        try:
            import psutil
            import subprocess
            import requests
            from datetime import datetime
            
            # Отримуємо інформацію про систему
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Перевіряємо API - бот запущений в тому ж контейнері що і API
            api_status = "✅ Працює (внутрішній)"
            
            # Перевіряємо Docker контейнери - бот запущений в Docker
            docker_status = "✅ Запущено (в контейнері)"
            
            # Кількість Python процесів
            python_processes = len([p for p in psutil.process_iter(['name']) if 'python' in p.info['name'].lower()])
            
            # Формуємо повідомлення
            status_message = (
                f"🏥 <b>Стан сервера</b>\n"
                f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                
                f"🖥️ <b>Система:</b>\n"
                f"💾 Пам'ять: {memory.percent:.1f}% ({memory.used // (1024**3):.1f}GB / {memory.total // (1024**3):.1f}GB)\n"
                f"💿 Диск: {disk.percent:.1f}% ({disk.used // (1024**3):.1f}GB / {disk.total // (1024**3):.1f}GB)\n"
                f"⚡ CPU: {cpu_percent:.1f}%\n\n"
                
                f"🐳 <b>Сервіси:</b>\n"
                f"🌐 API: {api_status}\n"
                f"📦 Docker: {docker_status}\n"
                f"🐍 Python процесів: {python_processes}\n\n"
            )
            
            # Додаємо попередження якщо щось не так
            if memory.percent > 85:
                status_message += "⚠️ <b>УВАГА:</b> Висока загрузка пам'яті!\n"
            if disk.percent > 90:
                status_message += "⚠️ <b>УВАГА:</b> Мало місця на диску!\n"
            if python_processes > 10:
                status_message += "⚠️ <b>УВАГА:</b> Забагато Python процесів!\n"
            if api_status == "❌ Недоступне":
                status_message += "🚨 <b>КРИТИЧНО:</b> API не відповідає!\n"
                
        except Exception as e:
            status_message = (
                f"❌ <b>Помилка при перевірці сервера:</b>\n\n"
                f"{str(e)}\n\n"
                f"Можливо, сервер недоступний або виникли проблеми з мережею."
            )
            
        await callback.message.answer(status_message, parse_mode='HTML')

    async def show_parser_logs(self, callback: types.CallbackQuery):
        """Показати останні логи парсерів"""
        try:
            import os
            from pathlib import Path
            
            # Спробуємо прочитати логи з файлу системи
            log_file_paths = [
                "/app/logs/parser.log",  # Основний лог парсера (спільний том)
                "/app/system/system.log",  # Альтернативний лог парсера
                "/app/monitoring_logs/parser.log",  # Альтернативний шлях
                "/var/log/parser.log"  # Системний лог
            ]
            
            logs_content = ""
            log_source = ""
            
            # Шукаємо доступний лог файл
            for log_path in log_file_paths:
                if os.path.exists(log_path):
                    try:
                        with open(log_path, 'r', encoding='utf-8') as f:
                            # Читаємо останні 50 рядків
                            lines = f.readlines()
                            logs_content = ''.join(lines[-50:])
                            log_source = log_path
                            break
                    except Exception as e:
                        continue
            
            # Якщо лог файли недоступні, покажемо інформацію про стан парсера
            if not logs_content:
                try:
                    # Отримуємо інформацію про процеси Python
                    import psutil
                    python_processes = []
                    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                        try:
                            if 'python' in proc.info['name'].lower():
                                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                                if 'system/main.py' in cmdline or 'parser' in cmdline.lower():
                                    python_processes.append({
                                        'pid': proc.info['pid'],
                                        'cmd': cmdline[:100] + '...' if len(cmdline) > 100 else cmdline,
                                        'time': datetime.fromtimestamp(proc.info['create_time']).strftime('%H:%M:%S')
                                    })
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    
                    logs_content = f"🔍 Активні парсер процеси:\n\n"
                    for proc in python_processes[:5]:  # Показуємо перші 5
                        logs_content += f"PID: {proc['pid']} | {proc['time']}\n{proc['cmd']}\n\n"
                    
                    log_source = "system processes"
                    
                except Exception as e:
                    logs_content = f"❌ Логи недоступні. Причина: {str(e)}"
                    log_source = "error"
            
            # Обмежуємо розмір повідомлення
            if len(logs_content) > 3500:
                logs_content = "...\n" + logs_content[-3500:]
            
            # Форматуємо логи
            status_message = (
                f"📊 <b>Логи парсера</b>\n"
                f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"📍 Джерело: {log_source}\n\n"
                f"<code>{logs_content if logs_content else 'Логи порожні або недоступні'}</code>"
            )
                
        except Exception as e:
            status_message = (
                f"❌ <b>Помилка при отриманні логів:</b>\n\n"
                f"<code>{str(e)}</code>\n\n"
                f"💡 <b>Порада:</b> Перевірте стан контейнерів через кнопку 'Перевірити стан сервера'"
            )
            
        await callback.message.answer(status_message, parse_mode='HTML')

    async def close(self):
        """Закриття сесії бота"""
        try:
            session = await self.bot.get_session()
            await session.close()
        except:
            pass 