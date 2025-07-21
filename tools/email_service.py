import os
import resend
from typing import Dict, Any, Optional
from tools.logger import Logger

logger = Logger()

class EmailService:
    def __init__(self):
        self.resend_api_key = os.getenv('RESEND_API_KEY')
        if not self.resend_api_key:
            logger.warning("RESEND_API_KEY не встановлено в змінних середовища")
        else:
            resend.api_key = self.resend_api_key
        
        # Підтримувані мови
        self.supported_languages = ["uk", "ru", "en"]
        
        # Переклади для email
        self.translations = {
            "uk": {
                "verification_subject": "Підтвердження реєстрації - Ваш Ковчег",
                "verification_title": "Ласкаво просимо до Ваш Ковчег!",
                "verification_greeting": "Привіт",
                "verification_thanks": "Дякуємо за реєстрацію в системі Ваш Ковчег. Для завершення реєстрації, будь ласка, підтвердіть свою електронну адресу.",
                "verification_code_label": "Ваш код верифікації:",
                "verification_instructions": "Введіть цей код в додатку для підтвердження вашої електронної адреси.",
                "verification_expires": "Код дійсний протягом 24 годин.",
                "signature": "З повагою,<br>Команда Ваш Ковчег",
                
                "reset_subject": "Відновлення паролю - Ваш Ковчег",
                "reset_title": "Відновлення паролю",
                "reset_greeting": "Привіт",
                "reset_message": "Ви запросили відновлення паролю для вашого акаунту в системі Ваш Ковчег.",
                "reset_code_label": "Ваш код відновлення паролю:",
                "reset_instructions": "Введіть цей код в додатку разом з новим паролем.",
                "reset_warning": "⚠️ Увага:",
                "reset_warning_text": "Код дійсний лише 1 годину. Якщо ви не запросили відновлення паролю, проігноруйте цей лист.",
                
                "welcome_subject": "Ласкаво просимо до Ваш Ковчег!",
                "welcome_title": "Вітаємо",
                "welcome_message": "Ваш акаунт успішно створено та верифіковано!",
                "welcome_features": "Тепер ви можете користуватися всіма можливостями платформи Ваш Ковчег:",
                "feature_search": "🏠 Пошук нерухомості",
                "feature_admins": "💼 Робота з адмінами",
                "feature_analytics": "📊 Аналітика ринку",
                "feature_ai": "🤖 AI-асистент",
                "welcome_wishes": "Бажаємо вам успішних угод!"
            },
            "ru": {
                "verification_subject": "Подтверждение регистрации - Ваш Ковчег",
                "verification_title": "Добро пожаловать в Ваш Ковчег!",
                "verification_greeting": "Привет",
                "verification_thanks": "Спасибо за регистрацию в системе Ваш Ковчег. Для завершения регистрации, пожалуйста, подтвердите свой электронный адрес.",
                "verification_code_label": "Ваш код верификации:",
                "verification_instructions": "Введите этот код в приложении для подтверждения вашего электронного адреса.",
                "verification_expires": "Код действителен в течение 24 часов.",
                "signature": "С уважением,<br>Команда Ваш Ковчег",
                
                "reset_subject": "Восстановление пароля - Ваш Ковчег",
                "reset_title": "Восстановление пароля",
                "reset_greeting": "Привет",
                "reset_message": "Вы запросили восстановление пароля для вашего аккаунта в системе Ваш Ковчег.",
                "reset_code_label": "Ваш код восстановления пароля:",
                "reset_instructions": "Введите этот код в приложении вместе с новым паролем.",
                "reset_warning": "⚠️ Внимание:",
                "reset_warning_text": "Код действителен только 1 час. Если вы не запрашивали восстановление пароля, проигнорируйте это письмо.",
                
                "welcome_subject": "Добро пожаловать в Ваш Ковчег!",
                "welcome_title": "Поздравляем",
                "welcome_message": "Ваш аккаунт успешно создан и верифицирован!",
                "welcome_features": "Теперь вы можете пользоваться всеми возможностями платформы Ваш Ковчег:",
                "feature_search": "🏠 Поиск недвижимости",
                "feature_admins": "💼 Работа с адмінами",
                "feature_analytics": "📊 Аналитика рынка",
                "feature_ai": "🤖 AI-ассистент",
                "welcome_wishes": "Желаем вам успешных сделок!"
            },
            "en": {
                "verification_subject": "Registration Confirmation - Ваш Ковчег",
                "verification_title": "Welcome to Ваш Ковчег!",
                "verification_greeting": "Hello",
                "verification_thanks": "Thank you for registering with Ваш Ковчег. To complete your registration, please verify your email address.",
                "verification_code_label": "Your verification code:",
                "verification_instructions": "Enter this code in the app to confirm your email address.",
                "verification_expires": "Code is valid for 24 hours.",
                "signature": "Best regards,<br>Ваш Ковчег Team",
                
                "reset_subject": "Password Reset - Ваш Ковчег",
                "reset_title": "Password Reset",
                "reset_greeting": "Hello",
                "reset_message": "You requested a password reset for your Ваш Ковчег account.",
                "reset_code_label": "Your password reset code:",
                "reset_instructions": "Enter this code in the app along with your new password.",
                "reset_warning": "⚠️ Warning:",
                "reset_warning_text": "Code is valid for only 1 hour. If you did not request a password reset, please ignore this email.",
                
                "welcome_subject": "Welcome to Ваш Ковчег!",
                "welcome_title": "Congratulations",
                "welcome_message": "Your account has been successfully created and verified!",
                "welcome_features": "Now you can use all the features of the Ваш Ковчег platform:",
                "feature_search": "🏠 Property Search",
                "feature_admins": "💼 Work with Admins",
                "feature_analytics": "📊 Market Analytics",
                "feature_ai": "🤖 AI Assistant",
                "welcome_wishes": "We wish you successful deals!"
            }
        }
    
    def _get_language(self, language: str) -> str:
        """Валідація та повернення підтримуваної мови"""
        if language and language in self.supported_languages:
            return language
        return "uk"  # За замовчуванням українська
    
    async def send_verification_email(self, email: str, verification_code: str, user_name: str = "", language: str = "uk") -> bool:
        """Відправка email з кодом верифікації"""
        try:
            if not self.resend_api_key:
                logger.error("Resend API key не налаштовано")
                return False
            
            lang = self._get_language(language)
            t = self.translations[lang]
            
            subject = t["verification_subject"]
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{t["verification_title"]}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; background-color: #f9f9f9; }}
                    .code {{ background-color: #e8f5e8; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 18px; text-align: center; margin: 20px 0; }}
                    .footer {{ text-align: center; padding: 20px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>{t["verification_title"]}</h1>
                    </div>
                    <div class="content">
                        <p>{t["verification_greeting"]}{f", {user_name}" if user_name else ""}!</p>
                        <p>{t["verification_thanks"]}</p>
                        <p>{t["verification_code_label"]}</p>
                        <div class="code">{verification_code}</div>
                        <p>{t["verification_instructions"]}</p>
                        <p>{t["verification_expires"]}</p>
                    </div>
                    <div class="footer">
                        <p>{t["signature"]}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            params = {
                "from": "Ваш Ковчег <noreply@mediamood.today>",
                "to": [email],
                "subject": subject,
                "html": html_content
            }
            
            email_response = resend.Emails.send(params)
            logger.info(f"Email верифікації відправлено на {email} ({lang}): {email_response}")
            return True
            
        except Exception as e:
            logger.error(f"Помилка відправки email верифікації: {str(e)}")
            return False
    
    async def send_password_reset_email(self, email: str, reset_code: str, user_name: str = "", language: str = "uk") -> bool:
        """Відправка email з кодом відновлення паролю"""
        try:
            if not self.resend_api_key:
                logger.error("Resend API key не налаштовано")
                return False
            
            lang = self._get_language(language)
            t = self.translations[lang]
            
            subject = t["reset_subject"]
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{t["reset_title"]}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #ff9800; color: white; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; background-color: #f9f9f9; }}
                    .code {{ background-color: #fff3e0; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 18px; text-align: center; margin: 20px 0; }}
                    .footer {{ text-align: center; padding: 20px; color: #666; }}
                    .warning {{ background-color: #ffebee; padding: 10px; border-radius: 5px; margin: 10px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>{t["reset_title"]}</h1>
                    </div>
                    <div class="content">
                        <p>{t["reset_greeting"]}{f", {user_name}" if user_name else ""}!</p>
                        <p>{t["reset_message"]}</p>
                        <p>{t["reset_code_label"]}</p>
                        <div class="code">{reset_code}</div>
                        <p>{t["reset_instructions"]}</p>
                        <div class="warning">
                            <strong>{t["reset_warning"]}</strong> {t["reset_warning_text"]}
                        </div>
                    </div>
                    <div class="footer">
                        <p>{t["signature"]}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            params = {
                "from": "Ваш Ковчег <noreply@mediamood.today>",
                "to": [email],
                "subject": subject,
                "html": html_content
            }
            
            email_response = resend.Emails.send(params)
            logger.info(f"Email відновлення паролю відправлено на {email} ({lang}): {email_response}")
            return True
            
        except Exception as e:
            logger.error(f"Помилка відправки email відновлення паролю: {str(e)}")
            return False
    
    async def send_welcome_email(self, email: str, user_name: str, language: str = "uk") -> bool:
        """Відправка привітального email після верифікації"""
        try:
            if not self.resend_api_key:
                logger.error("Resend API key не налаштовано")
                return False
            
            lang = self._get_language(language)
            t = self.translations[lang]
            
            subject = t["welcome_subject"]
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{t["welcome_title"]}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
                    .content {{ padding: 20px; background-color: #f9f9f9; }}
                    .footer {{ text-align: center; padding: 20px; color: #666; }}
                    .feature {{ background-color: #e8f5e8; padding: 10px; margin: 10px 0; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>{t["welcome_title"]}, {user_name}!</h1>
                    </div>
                    <div class="content">
                        <p>{t["welcome_message"]}</p>
                        <p>{t["welcome_features"]}</p>
                        <div class="feature">{t["feature_search"]}</div>
                        <div class="feature">{t["feature_admins"]}</div>
                        <div class="feature">{t["feature_analytics"]}</div>
                        <div class="feature">{t["feature_ai"]}</div>
                        <p>{t["welcome_wishes"]}</p>
                    </div>
                    <div class="footer">
                        <p>{t["signature"]}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            params = {
                "from": "Ваш Ковчег <noreply@mediamood.today>",
                "to": [email],
                "subject": subject,
                "html": html_content
            }
            
            email_response = resend.Emails.send(params)
            logger.info(f"Привітальний email відправлено на {email} ({lang}): {email_response}")
            return True
            
        except Exception as e:
            logger.error(f"Помилка відправки привітального email: {str(e)}")
            return False 