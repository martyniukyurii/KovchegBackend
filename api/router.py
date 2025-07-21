from fastapi import APIRouter, FastAPI, Depends
from api.jwt_handler import JWTHandler
from fastapi import Request, HTTPException, status
from api.endpoints.auth import AuthEndpoints
from api.endpoints.admin_auth import AdminAuthEndpoints
from api.endpoints.telegram_auth import TelegramAuthEndpoints
from api.endpoints.properties import PropertiesEndpoints
from api.endpoints.users import UsersEndpoints
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
        self.users_handler = UsersEndpoints() # Changed from ClientsEndpoints to UsersEndpoints
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
        self.admins_router = APIRouter(prefix="/admins", tags=["Admins"]) # Змінено з admins на admins
        self.users_router = APIRouter(prefix="/users", tags=["Users"])
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

        def jwt_auth_dependency(request: Request):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен авторизації обов'язковий")
            token = auth_header.split(" ")[1]
            payload = JWTHandler().decode_token(token)
            if not payload.get("sub"):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невірний токен")
            return payload

        # Authentication routes (користувачі)
        self.auth_router.post("/register", summary="Реєстрація користувача")(self.auth_handler.register)
        self.auth_router.post("/verify-email", summary="Верифікація email")(self.auth_handler.verify_email)
        self.auth_router.post("/login", summary="Вхід користувача")(self.auth_handler.login)
        self.auth_router.post("/login/oauth2", summary="Вхід через OAuth2 (Google, Apple)")(self.auth_handler.login_oauth2)
        self.auth_router.get("/google-drive/url", summary="Отримати URL для OAuth авторизації Google Drive")(self.auth_handler.get_google_drive_auth_url)
        self.auth_router.post("/google-drive/callback", summary="Обробка callback від Google OAuth")(self.auth_handler.handle_google_drive_callback)
        self.auth_router.get("/google-drive/callback-web", summary="Web callback для Google OAuth")(self.auth_handler.handle_google_drive_callback_web)
        self.auth_router.post("/refresh", summary="Оновлення токена")(self.auth_handler.refresh_token)
        self.auth_router.post("/oauth2/urls", summary="Отримання OAuth2 URLs")(self.auth_handler.get_oauth2_urls)
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
        self.tg_auth_router.post("/widget/authenticate", summary="Автентифікація через Telegram Login Widget")(self.tg_auth_handler.authenticate_widget)

        # Properties routes (для гостей)
        self.properties_router.get("/top", summary="Отримати топові пропозиції")(self.properties_handler.get_top_offers)
        self.properties_router.get("/buy", summary="Пошук нерухомості для купівлі")(self.properties_handler.search_buy)
        self.properties_router.get("/rent", summary="Пошук нерухомості для оренди")(self.properties_handler.search_rent)
        self.properties_router.post("/sell", summary="Подати заявку на продаж нерухомості")(self.properties_handler.submit_sell_request)
        
        # Properties routes (з JWT токеном)
        self.properties_router.get("/my", summary="Мої об'єкти нерухомості")(self.properties_handler.get_my_properties)
        self.properties_router.post("/", summary="Створити об'єкт нерухомості")(self.properties_handler.create_property)
        self.properties_router.get("/favorites", summary="Отримати обрані об'єкти")(self.properties_handler.get_favorites)
        self.properties_router.post("/favorites/{property_id}", summary="Додати об'єкт до обраних")(self.properties_handler.add_to_favorites)
        self.properties_router.delete("/favorites/{property_id}", summary="Видалити об'єкт з обраних")(self.properties_handler.remove_from_favorites)
        self.properties_router.get("/{property_id}", summary="Отримати об'єкт нерухомості за ID")(self.properties_handler.get_property)
        self.properties_router.put("/{property_id}", summary="Оновити об'єкт нерухомості")(self.properties_handler.update_property)
        self.properties_router.delete("/{property_id}", summary="Видалити об'єкт нерухомості")(self.properties_handler.delete_property)

        # Admins routes (з JWT токеном)
        self.admins_router.get("/", summary="Отримати список адмінів", dependencies=[Depends(jwt_auth_dependency)])(self.admin_auth_handler.get_admins)
        self.admins_router.post("/apply", summary="Подати заявку на роботу адміном")(self.admin_auth_handler.apply_for_admin)
        self.admins_router.get("/{admin_id}", summary="Отримати інформацію про адміна", dependencies=[Depends(jwt_auth_dependency)])(self.admin_auth_handler.get_admin)
        
        # Training programs routes (з JWT токеном)
        self.admins_router.get("/training-programs", summary="Отримати програми підготовки адмінів", dependencies=[Depends(jwt_auth_dependency)])(self.admin_auth_handler.get_training_programs)
        self.admins_router.get("/training-programs/{program_id}", summary="Отримати програму підготовки за ID", dependencies=[Depends(jwt_auth_dependency)])(self.admin_auth_handler.get_training_program)
        self.admins_router.post("/training-programs", summary="Створити програму підготовки", dependencies=[Depends(jwt_auth_dependency)])(self.admin_auth_handler.create_training_program)
        self.admins_router.put("/training-programs/{program_id}", summary="Оновити програму підготовки", dependencies=[Depends(jwt_auth_dependency)])(self.admin_auth_handler.update_training_program)
        self.admins_router.delete("/training-programs/{program_id}", summary="Видалити програму підготовки", dependencies=[Depends(jwt_auth_dependency)])(self.admin_auth_handler.delete_training_program)
        self.admins_router.post("/", summary="Створити адміна", dependencies=[Depends(jwt_auth_dependency)])(self.admin_auth_handler.create_admin)
        self.admins_router.put("/{admin_id}", summary="Оновити інформацію про адміна", dependencies=[Depends(jwt_auth_dependency)])(self.admin_auth_handler.update_admin)
        self.admins_router.delete("/{admin_id}", summary="Видалити адміна", dependencies=[Depends(jwt_auth_dependency)])(self.admin_auth_handler.delete_admin)

        # Users routes (з JWT токеном)
        self.users_router.get("/", summary="Отримати список користувачів")(self.users_handler.get_users)
        self.users_router.post("/", summary="Створити користувача")(self.users_handler.create_user)
        self.users_router.get("/{user_id}", summary="Отримати користувача за ID")(self.users_handler.get_user)
        self.users_router.put("/{user_id}", summary="Оновити користувача")(self.users_handler.update_user)
        self.users_router.delete("/{user_id}", summary="Видалити користувача")(self.users_handler.delete_user)

        # Deals routes (з JWT токеном)
        self.deals_router.get("/", summary="Отримати список угод")(self.deals_handler.get_deals)
        self.deals_router.post("/", summary="Створити угоду")(self.deals_handler.create_deal)
        
        # Activity Journal routes (з JWT токеном) - ПЕРЕД /{deal_id}
        self.deals_router.get("/activity-codes", summary="Отримати коди для журналу активності")(self.deals_handler.get_activity_codes)
        self.deals_router.get("/activity-journal", summary="Отримати журнал активності")(self.deals_handler.get_activity_journal)
        self.deals_router.post("/activity-journal", summary="Додати запис до журналу активності")(self.deals_handler.add_activity_journal_entry)
        self.deals_router.get("/activity-journal/{entry_id}", summary="Отримати запис журналу за ID")(self.deals_handler.get_activity_journal_entry)
        self.deals_router.put("/activity-journal/{entry_id}", summary="Оновити запис журналу")(self.deals_handler.update_activity_journal_entry)
        self.deals_router.delete("/activity-journal/{entry_id}", summary="Видалити запис журналу")(self.deals_handler.delete_activity_journal_entry)
        
        self.deals_router.get("/{deal_id}", summary="Отримати угоду за ID")(self.deals_handler.get_deal)
        self.deals_router.put("/{deal_id}", summary="Оновити угоду")(self.deals_handler.update_deal)
        self.deals_router.delete("/{deal_id}", summary="Видалити угоду")(self.deals_handler.delete_deal)

        # Calendar routes (з JWT токеном)
        self.calendar_router.get("/events", summary="Отримати події календаря")(self.calendar_handler.get_events)
        self.calendar_router.post("/events", summary="Створити подію календаря")(self.calendar_handler.create_event)
        self.calendar_router.get("/events/{event_id}", summary="Отримати подію за ID")(self.calendar_handler.get_event)
        self.calendar_router.put("/events/{event_id}", summary="Оновити подію")(self.calendar_handler.update_event)
        self.calendar_router.delete("/events/{event_id}", summary="Видалити подію")(self.calendar_handler.delete_event)

        # Documents routes (з JWT токеном)
        self.documents_router.get("/", summary="Отримати список документів")(self.documents_handler.get_documents)
        self.documents_router.post("/", summary="Завантажити документ")(self.documents_handler.upload_document)
        
        # Document templates routes (МАЮТЬ БУТИ ПЕРЕД {document_id})
        self.documents_router.get("/templates", summary="Отримати шаблони документів")(self.documents_handler.get_document_templates)
        self.documents_router.post("/templates", summary="Створити шаблон документа")(self.documents_handler.create_document_template)
        self.documents_router.post("/templates/upload-docx", summary="Завантажити .docx шаблон з автопарсингом")(self.documents_handler.upload_document_template_from_file)
        self.documents_router.get("/templates/{template_id}", summary="Отримати шаблон за ID")(self.documents_handler.get_template)
        self.documents_router.put("/templates/{template_id}", summary="Оновити шаблон документа")(self.documents_handler.update_document_template)
        self.documents_router.delete("/templates/{template_id}", summary="Видалити шаблон документа")(self.documents_handler.delete_document_template)
        self.documents_router.post("/templates/{template_id}/generate", summary="Згенерувати документ з шаблона")(self.documents_handler.generate_document_from_template)
        self.documents_router.post("/templates/{template_id}/generate-docx", summary="Згенерувати .docx документ з шаблона")(self.documents_handler.generate_docx_from_template)
        
        self.documents_router.get("/{document_id}", summary="Отримати документ за ID")(self.documents_handler.get_document)
        self.documents_router.put("/{document_id}", summary="Оновити документ")(self.documents_handler.update_document)
        self.documents_router.delete("/{document_id}", summary="Видалити документ")(self.documents_handler.delete_document)

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
        self.analytics_router.get("/admins-performance", summary="Аналітика продуктивності адмінів")(self.analytics_handler.get_admins_performance)
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
        self.parsed_listings_router.get("/{listing_id}", summary="Отримати спарсене оголошення за ID")(self.parsed_listings_handler.get_parsed_listing)
        self.parsed_listings_router.post("/", summary="Створити спарсене оголошення")(self.parsed_listings_handler.create_parsed_listing)
        self.parsed_listings_router.post("/{listing_id}/convert", summary="Конвертувати в об'єкт нерухомості")(self.parsed_listings_handler.convert_to_property)
        self.parsed_listings_router.delete("/{listing_id}", summary="Видалити спарсене оголошення")(self.parsed_listings_handler.delete_parsed_listing)

        # Smart Search routes (публічні)
        self.smart_search_router.get("/", summary="Розумний пошук нерухомості")(self.smart_search_handler.smart_search)
        self.smart_search_router.post("/embeddings/create", summary="Створити векторні ембединги")(self.smart_search_handler.create_embeddings)

        # AI Assistant routes (з JWT токеном)
        self.ai_assistant_router.get("/property/{property_id}/matches", summary="AI аналіз: топ клієнтів для нерухомості")(self.ai_assistant_handler.get_property_client_matches)
        self.ai_assistant_router.get("/daily-tasks", summary="Отримання щоденних задач адміна")(self.ai_assistant_handler.get_daily_admin_tasks)
        self.ai_assistant_router.put("/admin/{admin_id}/tasks/{date}", summary="Оновлення щоденних задач адміна")(self.ai_assistant_handler.update_daily_tasks)
        self.ai_assistant_router.post("/admin/bulk-generate-tasks", summary="Масове генерування задач для всіх адмінів")(self.ai_assistant_handler.bulk_generate_daily_tasks)
        self.ai_assistant_router.delete("/admin/cleanup-expired-tasks", summary="Видалення застарілих задач (3+ місяці)")(self.ai_assistant_handler.cleanup_expired_tasks)
        
        # Фонові задачі (тільки для тестування)
        self.ai_assistant_router.post("/admin/test-generate-tasks", summary="Тестова генерація задач")(self.test_generate_tasks)
        self.ai_assistant_router.post("/admin/test-cleanup-tasks", summary="Тестове очищення задач")(self.test_cleanup_tasks)

        # Додаємо роутери в FastAPI додасть /kovcheg/)
        self.app.include_router(self.auth_router)
        self.app.include_router(self.admin_auth_router)
        self.app.include_router(self.tg_auth_router)
        self.app.include_router(self.properties_router)
        self.app.include_router(self.admins_router) # Змінено з admins_router на admins_router
        self.app.include_router(self.users_router)
        self.app.include_router(self.deals_router)
        self.app.include_router(self.calendar_router)
        self.app.include_router(self.documents_router)
        self.app.include_router(self.marketing_router)
        self.app.include_router(self.analytics_router)
        self.app.include_router(self.user_profile_router)
        self.app.include_router(self.parsed_listings_router)
        self.app.include_router(self.smart_search_router)
        self.app.include_router(self.ai_assistant_router)
        
    async def test_generate_tasks(self, request: Request):
        """Тестова генерація задач."""
        from api.background_tasks import background_manager
        result = await background_manager.manual_generate_tasks()
        return JSONResponse(content=result)
        
    async def test_cleanup_tasks(self, request: Request):
        """Тестове очищення задач."""
        from api.background_tasks import background_manager
        result = await background_manager.manual_cleanup_tasks()
        return JSONResponse(content=result)
        
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
