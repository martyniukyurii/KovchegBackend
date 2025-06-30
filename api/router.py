from fastapi import APIRouter, FastAPI
from api.endpoints.auth import AuthEndpoints
from api.endpoints.admin_auth import AdminAuthEndpoints
from api.endpoints.telegram_auth import TelegramAuthEndpoints
from api.endpoints.properties import PropertiesEndpoints
from api.endpoints.agents import AgentsEndpoints
from api.endpoints.clients import ClientsEndpoints
from api.endpoints.deals import DealsEndpoints
from api.endpoints.calendar import CalendarEndpoints
from api.endpoints.documents import DocumentsEndpoints
from api.endpoints.marketing import MarketingEndpoints
from api.endpoints.analytics import AnalyticsEndpoints
from api.endpoints.user_profile import UserProfileEndpoints
from api.endpoints.parsed_listings import ParsedListingsEndpoints
from api.endpoints.smart_search import SmartSearchEndpoints
from api.endpoints.ai_assistant import AIAssistantEndpoints
from fastapi.responses import JSONResponse


class Router:
    def __init__(self, app: FastAPI):
        self.app = app

    async def initialize(self):
        """Ініціалізує всі ендпоінти"""
        # Ініціалізація обробників
        self.auth_handler = AuthEndpoints()
        self.admin_auth_handler = AdminAuthEndpoints()
        self.tg_auth_handler = TelegramAuthEndpoints()
        self.properties_handler = PropertiesEndpoints()
        self.agents_handler = AgentsEndpoints()
        self.clients_handler = ClientsEndpoints()
        self.deals_handler = DealsEndpoints()
        self.calendar_handler = CalendarEndpoints()
        self.documents_handler = DocumentsEndpoints()
        self.marketing_handler = MarketingEndpoints()
        self.analytics_handler = AnalyticsEndpoints()
        self.user_profile_handler = UserProfileEndpoints()
        self.parsed_listings_handler = ParsedListingsEndpoints()
        self.smart_search_handler = SmartSearchEndpoints()
        self.ai_assistant_handler = AIAssistantEndpoints()

        # Створення роутерів
        self.auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
        self.admin_auth_router = APIRouter(prefix="/admin/auth", tags=["Admin Authentication"])
        self.tg_auth_router = APIRouter(prefix="/telegram", tags=["Telegram Auth"])
        self.properties_router = APIRouter(prefix="/properties", tags=["Properties"])
        self.agents_router = APIRouter(prefix="/agents", tags=["Agents"])
        self.clients_router = APIRouter(prefix="/clients", tags=["Clients"])
        self.deals_router = APIRouter(prefix="/deals", tags=["Deals"])
        self.calendar_router = APIRouter(prefix="/calendar", tags=["Calendar"])
        self.documents_router = APIRouter(prefix="/documents", tags=["Documents"])
        self.marketing_router = APIRouter(prefix="/marketing", tags=["Marketing"])
        self.analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])
        self.user_profile_router = APIRouter(prefix="/profile", tags=["User Profile"])
        self.parsed_listings_router = APIRouter(prefix="/parsed-listings", tags=["Parsed Listings"])
        self.smart_search_router = APIRouter(prefix="/search", tags=["Smart Search"])
        self.ai_assistant_router = APIRouter(prefix="/ai", tags=["AI Assistant"])

        # Налаштування маршрутів
        await self.setup_routes()

    async def setup_routes(self):
        """Реєстрація маршрутів у FastAPI"""

        # Authentication routes (користувачі)
        self.auth_router.post("/register", summary="Реєстрація користувача")(self.auth_handler.register)
        self.auth_router.post("/verify-email", summary="Верифікація email")(self.auth_handler.verify_email)
        self.auth_router.post("/login", summary="Вхід користувача")(self.auth_handler.login)
        self.auth_router.post("/login/oauth2", summary="Вхід через OAuth2 (Gmail, Apple)")(self.auth_handler.login_oauth2)
        self.auth_router.post("/reset-password", summary="Запит на відновлення паролю")(self.auth_handler.request_password_reset)
        self.auth_router.post("/reset-password/confirm", summary="Підтвердження відновлення паролю")(self.auth_handler.confirm_password_reset)
        self.auth_router.post("/logout", summary="Вихід з системи")(self.auth_handler.logout)

        # Authentication routes (адміністратори)
        self.admin_auth_router.post("/login", summary="Вхід адміністратора")(self.admin_auth_handler.login)
        self.admin_auth_router.post("/verify-email", summary="Верифікація email адміністратора")(self.admin_auth_handler.verify_email)
        self.admin_auth_router.post("/reset-password", summary="Запит на відновлення паролю адміністратора")(self.admin_auth_handler.request_password_reset)
        self.admin_auth_router.post("/reset-password/confirm", summary="Підтвердження відновлення паролю адміністратора")(self.admin_auth_handler.confirm_password_reset)
        self.admin_auth_router.post("/logout", summary="Вихід адміністратора з системи")(self.admin_auth_handler.logout)

        # Telegram Auth routes
        self.tg_auth_router.post("/authenticate", summary="Автентифікація через Telegram")(self.tg_auth_handler.authenticate)
        self.tg_auth_router.post("/verify-code", summary="Підтвердження коду з Telegram")(self.tg_auth_handler.verify_telegram_code)

        # Properties routes (для гостей)
        self.properties_router.get("/top", summary="Отримати топові пропозиції")(self.properties_handler.get_top_offers)
        self.properties_router.get("/buy", summary="Пошук нерухомості для купівлі")(self.properties_handler.search_buy)
        self.properties_router.get("/rent", summary="Пошук нерухомості для оренди")(self.properties_handler.search_rent)
        self.properties_router.post("/sell", summary="Подати заявку на продаж нерухомості")(self.properties_handler.submit_sell_request)
        
        # Properties routes (з JWT токеном)
        self.properties_router.get("/my", summary="Мої об'єкти нерухомості")(self.properties_handler.get_my_properties)
        self.properties_router.post("/", summary="Створити об'єкт нерухомості")(self.properties_handler.create_property)
        self.properties_router.get("/{property_id}", summary="Отримати об'єкт нерухомості за ID")(self.properties_handler.get_property)
        self.properties_router.put("/{property_id}", summary="Оновити об'єкт нерухомості")(self.properties_handler.update_property)
        self.properties_router.delete("/{property_id}", summary="Видалити об'єкт нерухомості")(self.properties_handler.delete_property)
        self.properties_router.post("/favorites/{property_id}", summary="Додати об'єкт до обраних")(self.properties_handler.add_to_favorites)
        self.properties_router.delete("/favorites/{property_id}", summary="Видалити об'єкт з обраних")(self.properties_handler.remove_from_favorites)
        self.properties_router.get("/favorites", summary="Отримати обрані об'єкти")(self.properties_handler.get_favorites)
        self.properties_router.get("/search-history", summary="Отримати історію пошуку")(self.properties_handler.get_search_history)

        # Agents routes (публічні)
        self.agents_router.get("/", summary="Отримати список агентів")(self.agents_handler.get_agents)
        self.agents_router.get("/{agent_id}", summary="Отримати інформацію про агента")(self.agents_handler.get_agent)
        self.agents_router.post("/apply", summary="Подати заявку на роботу агентом")(self.agents_handler.apply_for_agent)
        
        # Agents routes (з JWT токеном)
        self.agents_router.post("/", summary="Створити агента")(self.agents_handler.create_agent)
        self.agents_router.put("/{agent_id}", summary="Оновити інформацію про агента")(self.agents_handler.update_agent)
        self.agents_router.delete("/{agent_id}", summary="Видалити агента")(self.agents_handler.delete_agent)
        
        # Training programs routes
        self.agents_router.get("/training-programs", summary="Отримати програми підготовки агентів")(self.agents_handler.get_training_programs)
        self.agents_router.get("/training-programs/{program_id}", summary="Отримати програму підготовки за ID")(self.agents_handler.get_training_program)
        
        # Clients routes (з JWT токеном)
        self.clients_router.get("/", summary="Отримати список клієнтів")(self.clients_handler.get_clients)
        self.clients_router.post("/", summary="Створити клієнта")(self.clients_handler.create_client)
        self.clients_router.get("/{client_id}", summary="Отримати клієнта за ID")(self.clients_handler.get_client)
        self.clients_router.put("/{client_id}", summary="Оновити клієнта")(self.clients_handler.update_client)
        self.clients_router.delete("/{client_id}", summary="Видалити клієнта")(self.clients_handler.delete_client)

        # Deals routes (з JWT токеном)
        self.deals_router.get("/", summary="Отримати список угод")(self.deals_handler.get_deals)
        self.deals_router.post("/", summary="Створити угоду")(self.deals_handler.create_deal)
        self.deals_router.get("/{deal_id}", summary="Отримати угоду за ID")(self.deals_handler.get_deal)
        self.deals_router.put("/{deal_id}", summary="Оновити угоду")(self.deals_handler.update_deal)
        self.deals_router.delete("/{deal_id}", summary="Видалити угоду")(self.deals_handler.delete_deal)
        
        # Activity Journal routes (з JWT токеном)
        self.deals_router.get("/activity-journal", summary="Отримати журнал активності")(self.deals_handler.get_activity_journal)
        self.deals_router.post("/activity-journal", summary="Додати запис до журналу активності")(self.deals_handler.add_activity_journal_entry)
        self.deals_router.get("/activity-journal/{entry_id}", summary="Отримати запис журналу за ID")(self.deals_handler.get_activity_journal_entry)
        self.deals_router.put("/activity-journal/{entry_id}", summary="Оновити запис журналу")(self.deals_handler.update_activity_journal_entry)
        self.deals_router.delete("/activity-journal/{entry_id}", summary="Видалити запис журналу")(self.deals_handler.delete_activity_journal_entry)

        # Calendar routes (з JWT токеном)
        self.calendar_router.get("/events", summary="Отримати події календаря")(self.calendar_handler.get_events)
        self.calendar_router.post("/events", summary="Створити подію календаря")(self.calendar_handler.create_event)
        self.calendar_router.get("/events/{event_id}", summary="Отримати подію за ID")(self.calendar_handler.get_event)
        self.calendar_router.put("/events/{event_id}", summary="Оновити подію")(self.calendar_handler.update_event)
        self.calendar_router.delete("/events/{event_id}", summary="Видалити подію")(self.calendar_handler.delete_event)

        # Documents routes (з JWT токеном)
        self.documents_router.get("/", summary="Отримати список документів")(self.documents_handler.get_documents)
        self.documents_router.post("/", summary="Завантажити документ")(self.documents_handler.upload_document)
        self.documents_router.get("/{document_id}", summary="Отримати документ за ID")(self.documents_handler.get_document)
        self.documents_router.put("/{document_id}", summary="Оновити документ")(self.documents_handler.update_document)
        self.documents_router.delete("/{document_id}", summary="Видалити документ")(self.documents_handler.delete_document)
        
        # Document templates routes
        self.documents_router.get("/templates", summary="Отримати шаблони документів")(self.documents_handler.get_document_templates)
        self.documents_router.post("/templates", summary="Створити шаблон документа")(self.documents_handler.create_document_template)
        self.documents_router.post("/templates/{template_id}/generate", summary="Згенерувати документ з шаблона")(self.documents_handler.generate_document_from_template)

        # Marketing routes (з JWT токеном)
        self.marketing_router.get("/campaigns", summary="Отримати маркетингові кампанії")(self.marketing_handler.get_campaigns)
        self.marketing_router.post("/campaigns", summary="Створити маркетингову кампанію")(self.marketing_handler.create_campaign)
        self.marketing_router.get("/campaigns/{campaign_id}", summary="Отримати кампанію за ID")(self.marketing_handler.get_campaign)
        self.marketing_router.put("/campaigns/{campaign_id}", summary="Оновити кампанію")(self.marketing_handler.update_campaign)
        self.marketing_router.delete("/campaigns/{campaign_id}", summary="Видалити кампанію")(self.marketing_handler.delete_campaign)
        
        # Leads routes (з JWT токеном)
        self.marketing_router.get("/leads", summary="Отримати ліди")(self.marketing_handler.get_leads)
        self.marketing_router.post("/leads", summary="Створити лід")(self.marketing_handler.create_lead)
        self.marketing_router.get("/leads/{lead_id}", summary="Отримати лід за ID")(self.marketing_handler.get_lead)
        self.marketing_router.put("/leads/{lead_id}", summary="Оновити лід")(self.marketing_handler.update_lead)
        self.marketing_router.delete("/leads/{lead_id}", summary="Видалити лід")(self.marketing_handler.delete_lead)

        # Analytics routes (з JWT токеном)
        self.analytics_router.get("/dashboard", summary="Статистика дашборда")(self.analytics_handler.get_dashboard_stats)
        self.analytics_router.get("/sales-report", summary="Звіт з продажів")(self.analytics_handler.get_sales_report)
        self.analytics_router.get("/properties", summary="Аналітика нерухомості")(self.analytics_handler.get_properties_analytics)
        self.analytics_router.get("/marketing", summary="Маркетингова аналітика")(self.analytics_handler.get_marketing_analytics)
        self.analytics_router.get("/agents-performance", summary="Аналітика продуктивності агентів")(self.analytics_handler.get_agents_performance)
        self.analytics_router.get("/export-report", summary="Експортувати звіт")(self.analytics_handler.export_report)

        # User Profile routes (з JWT токеном)
        self.user_profile_router.get("/", summary="Отримати профіль користувача")(self.user_profile_handler.get_profile)
        self.user_profile_router.put("/", summary="Оновити профіль користувача")(self.user_profile_handler.update_profile)
        self.user_profile_router.post("/change-password", summary="Змінити пароль")(self.user_profile_handler.change_password)
        self.user_profile_router.delete("/", summary="Видалити акаунт")(self.user_profile_handler.delete_account)
        
        # Communications routes (з JWT токеном)
        self.user_profile_router.get("/communications", summary="Отримати комунікації")(self.user_profile_handler.get_communications)
        self.user_profile_router.post("/communications", summary="Надіслати комунікацію")(self.user_profile_handler.send_communication)
        self.user_profile_router.put("/communications/{communication_id}/read", summary="Позначити комунікацію як прочитану")(self.user_profile_handler.mark_communication_as_read)
        
        # Notifications routes (з JWT токеном)
        self.user_profile_router.get("/notifications", summary="Отримати сповіщення")(self.user_profile_handler.get_notifications)
        self.user_profile_router.put("/notifications/{notification_id}/read", summary="Позначити сповіщення як прочитане")(self.user_profile_handler.mark_notification_as_read)
        self.user_profile_router.put("/notifications/read-all", summary="Позначити всі сповіщення як прочитані")(self.user_profile_handler.mark_all_notifications_as_read)

        # Parsed Listings routes (з JWT токеном)
        self.parsed_listings_router.get("/", summary="Отримати спарсені оголошення")(self.parsed_listings_handler.get_parsed_listings)
        self.parsed_listings_router.get("/stats", summary="Отримати статистику по спарсеним оголошенням")(self.parsed_listings_handler.get_parsed_listings_stats)
        self.parsed_listings_router.get("/{listing_id}", summary="Отримати спарсене оголошення за ID")(self.parsed_listings_handler.get_parsed_listing)
        self.parsed_listings_router.post("/", summary="Створити спарсене оголошення")(self.parsed_listings_handler.create_parsed_listing)
        self.parsed_listings_router.put("/{listing_id}/status", summary="Оновити статус спарсеного оголошення")(self.parsed_listings_handler.update_parsed_listing_status)
        self.parsed_listings_router.post("/{listing_id}/convert", summary="Конвертувати в об'єкт нерухомості")(self.parsed_listings_handler.convert_to_property)
        self.parsed_listings_router.delete("/{listing_id}", summary="Видалити спарсене оголошення")(self.parsed_listings_handler.delete_parsed_listing)
        self.parsed_listings_router.get("/sources", summary="Отримати джерела парсингу")(self.parsed_listings_handler.get_parsing_sources)
        self.parsed_listings_router.post("/tasks", summary="Запустити задачу парсингу")(self.parsed_listings_handler.start_parsing_task)
        self.parsed_listings_router.get("/tasks/{task_id}", summary="Отримати статус задачі парсингу")(self.parsed_listings_handler.get_parsing_task_status)

        # Smart Search routes (публічні)
        self.smart_search_router.get("/", summary="Розумний пошук нерухомості")(self.smart_search_handler.smart_search)
        self.smart_search_router.post("/embeddings/create", summary="Створити векторні ембединги")(self.smart_search_handler.create_embeddings)
        self.smart_search_router.put("/embeddings/{collection}/{record_id}", summary="Оновити ембединг для запису")(self.smart_search_handler.update_embedding_for_record)

        # AI Assistant routes (з JWT токеном)
        self.ai_assistant_router.get("/property/{property_id}/matches", summary="AI аналіз: топ клієнтів для нерухомості")(self.ai_assistant_handler.get_property_client_matches)
        self.ai_assistant_router.get("/daily-tasks", summary="Отримання щоденних задач агента")(self.ai_assistant_handler.get_daily_agent_tasks)
        self.ai_assistant_router.put("/agent/{agent_id}/tasks/{date}", summary="Оновлення щоденних задач агента")(self.ai_assistant_handler.update_daily_tasks)
        self.ai_assistant_router.post("/admin/bulk-generate-tasks", summary="Масове генерування задач для всіх агентів")(self.ai_assistant_handler.bulk_generate_daily_tasks)
        self.ai_assistant_router.delete("/admin/cleanup-expired-tasks", summary="Видалення застарілих задач (3+ місяці)")(self.ai_assistant_handler.cleanup_expired_tasks)

        # Додаємо роутери в FastAPI додаток
        self.app.include_router(self.auth_router)
        self.app.include_router(self.admin_auth_router)
        self.app.include_router(self.tg_auth_router)
        self.app.include_router(self.properties_router)
        self.app.include_router(self.agents_router)
        self.app.include_router(self.clients_router)
        self.app.include_router(self.deals_router)
        self.app.include_router(self.calendar_router)
        self.app.include_router(self.documents_router)
        self.app.include_router(self.marketing_router)
        self.app.include_router(self.analytics_router)
        self.app.include_router(self.user_profile_router)
        self.app.include_router(self.parsed_listings_router)
        self.app.include_router(self.smart_search_router)
        self.app.include_router(self.ai_assistant_router)
        
    async def handle_options_login(self):
        """Обробник OPTIONS запитів для /auth/login"""
        return JSONResponse(
            content={},
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Max-Age": "600",
            }
        )
