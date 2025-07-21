from enum import Enum
from fastapi import HTTPException, status

class AuthErrorCode(Enum):
    # Загальні помилки
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_GENERATION_ERROR = "TOKEN_GENERATION_ERROR"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    
    # Помилки користувача
    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_ALREADY_EXISTS = "USER_ALREADY_EXISTS"
    USER_NOT_VERIFIED = "USER_NOT_VERIFIED"
    USER_ALREADY_VERIFIED = "USER_ALREADY_VERIFIED"
    EMAIL_ALREADY_REGISTERED = "EMAIL_ALREADY_REGISTERED"
    EMAIL_NOT_FOUND = "EMAIL_NOT_FOUND"
    
    # Помилки верифікації
    INVALID_VERIFICATION_CODE = "INVALID_VERIFICATION_CODE"
    VERIFICATION_CODE_EXPIRED = "VERIFICATION_CODE_EXPIRED"
    
    # Помилки паролю
    INVALID_PASSWORD_RESET_CODE = "INVALID_PASSWORD_RESET_CODE"
    PASSWORD_RESET_CODE_EXPIRED = "PASSWORD_RESET_CODE_EXPIRED"
    WEAK_PASSWORD = "WEAK_PASSWORD"
    
    # Помилки адміністратора
    ADMIN_NOT_FOUND = "ADMIN_NOT_FOUND"
    ADMIN_ALREADY_EXISTS = "ADMIN_ALREADY_EXISTS"
    ADMIN_NOT_VERIFIED = "ADMIN_NOT_VERIFIED"
    
    # Помилки об'єктів нерухомості
    PROPERTY_NOT_FOUND = "PROPERTY_NOT_FOUND"
    PROPERTY_ALREADY_EXISTS = "PROPERTY_ALREADY_EXISTS"
    
    # Помилки клієнтів
    CLIENT_NOT_FOUND = "CLIENT_NOT_FOUND"
    CLIENT_ALREADY_EXISTS = "CLIENT_ALREADY_EXISTS"
    
    # Помилки угод
    DEAL_NOT_FOUND = "DEAL_NOT_FOUND"
    DEAL_ALREADY_EXISTS = "DEAL_ALREADY_EXISTS"
    
    # Помилки календаря
    EVENT_NOT_FOUND = "EVENT_NOT_FOUND"
    EVENT_CONFLICT = "EVENT_CONFLICT"
    
    # Помилки документів
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    DOCUMENT_UPLOAD_FAILED = "DOCUMENT_UPLOAD_FAILED"
    TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
    
    # Помилки маркетингу
    CAMPAIGN_NOT_FOUND = "CAMPAIGN_NOT_FOUND"
    LEAD_NOT_FOUND = "LEAD_NOT_FOUND"
    
    # Помилки комунікацій
    COMMUNICATION_NOT_FOUND = "COMMUNICATION_NOT_FOUND"
    NOTIFICATION_NOT_FOUND = "NOTIFICATION_NOT_FOUND"
    
    # Помилки журналу активності
    ACTIVITY_JOURNAL_ENTRY_NOT_FOUND = "ACTIVITY_JOURNAL_ENTRY_NOT_FOUND"
    
    # Помилки програм підготовки
    TRAINING_PROGRAM_NOT_FOUND = "TRAINING_PROGRAM_NOT_FOUND"
    
    # Помилки спарсених оголошень
    PARSED_LISTING_NOT_FOUND = "PARSED_LISTING_NOT_FOUND"
    PARSING_TASK_NOT_FOUND = "PARSING_TASK_NOT_FOUND"

class AuthException(HTTPException):
    """Клас для винятків авторизації."""
    
    def __init__(self, error_code: AuthErrorCode, status_code: int = None):
        """
        Ініціалізація винятку авторизації.
        
        :param error_code: Код помилки авторизації.
        :param status_code: Код статусу HTTP для відповіді.
        """
        self.error_code = error_code
        
        error_messages = {
            # Загальні помилки
            AuthErrorCode.INVALID_CREDENTIALS: {
                "detail": "Невірні облікові дані",
                "status_code": status.HTTP_401_UNAUTHORIZED
            },
            AuthErrorCode.INVALID_TOKEN: {
                "detail": "Невірний токен",
                "status_code": status.HTTP_401_UNAUTHORIZED
            },
            AuthErrorCode.TOKEN_EXPIRED: {
                "detail": "Термін дії токена закінчився",
                "status_code": status.HTTP_401_UNAUTHORIZED
            },
            AuthErrorCode.TOKEN_GENERATION_ERROR: {
                "detail": "Помилка генерації токена",
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR
            },
            AuthErrorCode.INSUFFICIENT_PERMISSIONS: {
                "detail": "Недостатньо прав доступу",
                "status_code": status.HTTP_403_FORBIDDEN
            },
            
            # Помилки користувача
            AuthErrorCode.USER_NOT_FOUND: {
                "detail": "Користувача не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            AuthErrorCode.USER_ALREADY_EXISTS: {
                "detail": "Користувач з таким email вже існує",
                "status_code": status.HTTP_409_CONFLICT
            },
            AuthErrorCode.USER_NOT_VERIFIED: {
                "detail": "Акаунт користувача не верифіковано",
                "status_code": status.HTTP_403_FORBIDDEN
            },
            AuthErrorCode.USER_ALREADY_VERIFIED: {
                "detail": "Акаунт користувача вже верифіковано",
                "status_code": status.HTTP_409_CONFLICT
            },
            AuthErrorCode.EMAIL_ALREADY_REGISTERED: {
                "detail": "Email вже зареєстровано в системі",
                "status_code": status.HTTP_409_CONFLICT
            },
            AuthErrorCode.EMAIL_NOT_FOUND: {
                "detail": "Email не знайдено в системі",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            
            # Помилки верифікації
            AuthErrorCode.INVALID_VERIFICATION_CODE: {
                "detail": "Невірний код верифікації або термін його дії закінчився",
                "status_code": status.HTTP_400_BAD_REQUEST
            },
            AuthErrorCode.VERIFICATION_CODE_EXPIRED: {
                "detail": "Термін дії коду верифікації закінчився",
                "status_code": status.HTTP_400_BAD_REQUEST
            },
            
            # Помилки паролю
            AuthErrorCode.INVALID_PASSWORD_RESET_CODE: {
                "detail": "Невірний код відновлення пароля або термін його дії закінчився",
                "status_code": status.HTTP_400_BAD_REQUEST
            },
            AuthErrorCode.PASSWORD_RESET_CODE_EXPIRED: {
                "detail": "Термін дії коду відновлення пароля закінчився",
                "status_code": status.HTTP_400_BAD_REQUEST
            },
            AuthErrorCode.WEAK_PASSWORD: {
                "detail": "Пароль занадто слабкий. Використовуйте мінімум 8 символів, включаючи цифри та букви",
                "status_code": status.HTTP_400_BAD_REQUEST
            },
            
            # Помилки адміністратора
            AuthErrorCode.ADMIN_NOT_FOUND: {
                "detail": "Адміна не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            AuthErrorCode.ADMIN_ALREADY_EXISTS: {
                "detail": "Адмін з такими даними вже існує",
                "status_code": status.HTTP_409_CONFLICT
            },
            AuthErrorCode.ADMIN_NOT_VERIFIED: {
                "detail": "Акаунт адміністратора не верифіковано",
                "status_code": status.HTTP_403_FORBIDDEN
            },
            
            # Помилки об'єктів нерухомості
            AuthErrorCode.PROPERTY_NOT_FOUND: {
                "detail": "Об'єкт нерухомості не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            AuthErrorCode.PROPERTY_ALREADY_EXISTS: {
                "detail": "Об'єкт нерухомості з такими параметрами вже існує",
                "status_code": status.HTTP_409_CONFLICT
            },
            
            # Помилки клієнтів
            AuthErrorCode.CLIENT_NOT_FOUND: {
                "detail": "Клієнта не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            AuthErrorCode.CLIENT_ALREADY_EXISTS: {
                "detail": "Клієнт з таким номером телефону вже існує",
                "status_code": status.HTTP_409_CONFLICT
            },
            
            # Помилки угод
            AuthErrorCode.DEAL_NOT_FOUND: {
                "detail": "Угоду не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            AuthErrorCode.DEAL_ALREADY_EXISTS: {
                "detail": "Угода з такими параметрами вже існує",
                "status_code": status.HTTP_409_CONFLICT
            },
            
            # Помилки календаря
            AuthErrorCode.EVENT_NOT_FOUND: {
                "detail": "Подію не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            AuthErrorCode.EVENT_CONFLICT: {
                "detail": "Конфлікт у розкладі - час зайнятий",
                "status_code": status.HTTP_409_CONFLICT
            },
            
            # Помилки документів
            AuthErrorCode.DOCUMENT_NOT_FOUND: {
                "detail": "Документ не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            AuthErrorCode.DOCUMENT_UPLOAD_FAILED: {
                "detail": "Помилка завантаження документа",
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR
            },
            AuthErrorCode.TEMPLATE_NOT_FOUND: {
                "detail": "Шаблон документа не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            
            # Помилки маркетингу
            AuthErrorCode.CAMPAIGN_NOT_FOUND: {
                "detail": "Маркетингову кампанію не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            AuthErrorCode.LEAD_NOT_FOUND: {
                "detail": "Лід не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            
            # Помилки комунікацій
            AuthErrorCode.COMMUNICATION_NOT_FOUND: {
                "detail": "Комунікацію не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            AuthErrorCode.NOTIFICATION_NOT_FOUND: {
                "detail": "Сповіщення не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            
            # Помилки журналу активності
            AuthErrorCode.ACTIVITY_JOURNAL_ENTRY_NOT_FOUND: {
                "detail": "Запис журналу активності не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            
            # Помилки програм підготовки
            AuthErrorCode.TRAINING_PROGRAM_NOT_FOUND: {
                "detail": "Програму підготовки не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            
            # Помилки спарсених оголошень
            AuthErrorCode.PARSED_LISTING_NOT_FOUND: {
                "detail": "Спарсене оголошення не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            },
            AuthErrorCode.PARSING_TASK_NOT_FOUND: {
                "detail": "Задачу парсингу не знайдено",
                "status_code": status.HTTP_404_NOT_FOUND
            }
        }
        
        error_info = error_messages.get(error_code)
        if not error_info:
            error_info = {
                "detail": "Невідома помилка",
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR
            }
        
        self.status_code = status_code or error_info["status_code"]
        
        super().__init__(
            status_code=self.status_code,
            detail={
                "detail": error_info["detail"],
                "code": error_code.value
            }
        ) 