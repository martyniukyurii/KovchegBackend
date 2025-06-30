from datetime import datetime
from typing import Dict, Optional, List, Any
from tools.logger import Logger
from tools.database import Database

logger = Logger()


class EventLogger:
    def __init__(self, user: Optional[Dict] = None):
        self.db = Database()
        self.user = user  # Словник з даними користувача (наприклад, {"_id": "user123"})

    async def _log_event(
            self,
            event_type: str,
            description: str,
            metadata: Optional[Dict] = None
    ) -> bool:
        """Зберігає подію в колекції `logs`."""
        try:
            event_data = {
                "timestamp": datetime.utcnow(),
                "event_type": event_type,
                "description": description,
                "user_id": self.user["_id"] if self.user else None,
                "metadata": metadata or {}
            }
            await self.db.logs.create(event_data)
            return True
        except Exception as e:
            logger.error(f"Помилка логування події: {str(e)}")
            return False

    # Журнал активності
    async def log_activity(
            self,
            event_type: str,
            title: str,
            description: str,
            related_to: Optional[Dict] = None,
            participants: Optional[Dict] = None,
            financial_details: Optional[Dict] = None,
            follow_up_required: bool = False,
            follow_up_date: Optional[datetime] = None,
            location: Optional[str] = None,
            duration: Optional[int] = None,
            attachments: Optional[List] = None,
            result: Optional[str] = None,
            status: Optional[str] = None,
            notes: Optional[str] = None
    ) -> Optional[str]:
        """Додає запис до журналу активності."""
        try:
            activity_data = {
                "event_type": {event_type: True},
                "title": title,
                "description": description,
                "timestamp": datetime.utcnow(),
                "created_by": self.user["_id"] if self.user else None,
                "status": status,
                "result": result
            }

            if related_to:
                activity_data["related_to"] = related_to

            if participants:
                activity_data["participants"] = participants

            if financial_details:
                activity_data["financial_details"] = financial_details

            if follow_up_required:
                activity_data["follow_up_required"] = follow_up_required
                if follow_up_date:
                    activity_data["follow_up_date"] = follow_up_date

            if location:
                activity_data["location"] = location

            if duration:
                activity_data["duration"] = duration

            if attachments:
                activity_data["attachments"] = attachments

            if notes:
                activity_data["notes"] = notes

            return await self.db.activity_journal.create(activity_data)
        except Exception as e:
            logger.error(f"Помилка додавання запису до журналу активності: {str(e)}")
            return None

    # Логування дзвінків
    async def log_call(
            self,
            title: str,
            description: str,
            client_id: Optional[str] = None,
            agent_id: Optional[str] = None,
            property_id: Optional[str] = None,
            duration: Optional[int] = None,
            result: Optional[str] = None,
            follow_up_required: bool = False,
            follow_up_date: Optional[datetime] = None,
            notes: Optional[str] = None
    ) -> Optional[str]:
        """Логує дзвінок у журнал активності."""
        participants = {}
        if agent_id:
            participants["agents"] = [agent_id]
        if client_id:
            participants["clients"] = [client_id]

        related_to = {}
        if client_id:
            related_to["type"] = {"client": True}
            related_to["id"] = client_id
        elif property_id:
            related_to["type"] = {"property": True}
            related_to["id"] = property_id

        return await self.log_activity(
            event_type="call",
            title=title,
            description=description,
            related_to=related_to,
            participants=participants,
            duration=duration,
            result=result,
            follow_up_required=follow_up_required,
            follow_up_date=follow_up_date,
            notes=notes
        )

    # Логування зустрічей
    async def log_meeting(
            self,
            title: str,
            description: str,
            location: str,
            client_id: Optional[str] = None,
            agent_id: Optional[str] = None,
            property_id: Optional[str] = None,
            duration: Optional[int] = None,
            result: Optional[str] = None,
            follow_up_required: bool = False,
            follow_up_date: Optional[datetime] = None,
            notes: Optional[str] = None
    ) -> Optional[str]:
        """Логує зустріч у журнал активності."""
        participants = {}
        if agent_id:
            participants["agents"] = [agent_id]
        if client_id:
            participants["clients"] = [client_id]

        related_to = {}
        if client_id:
            related_to["type"] = {"client": True}
            related_to["id"] = client_id
        elif property_id:
            related_to["type"] = {"property": True}
            related_to["id"] = property_id

        return await self.log_activity(
            event_type="meeting",
            title=title,
            description=description,
            location=location,
            related_to=related_to,
            participants=participants,
            duration=duration,
            result=result,
            follow_up_required=follow_up_required,
            follow_up_date=follow_up_date,
            notes=notes
        )

    # Логування платежів
    async def log_payment(
            self,
            title: str,
            description: str,
            amount: float,
            currency: str = "UAH",
            payment_type: str = "advance",
            payment_status: str = "completed",
            payment_purpose: str = "",
            client_id: Optional[str] = None,
            agent_id: Optional[str] = None,
            property_id: Optional[str] = None,
            deal_id: Optional[str] = None,
            notes: Optional[str] = None
    ) -> Optional[str]:
        """Логує платіж у журнал активності."""
        participants = {}
        if agent_id:
            participants["agents"] = [agent_id]
        if client_id:
            participants["clients"] = [client_id]

        related_to = {}
        if deal_id:
            related_to["type"] = {"deal": True}
            related_to["id"] = deal_id
        elif property_id:
            related_to["type"] = {"property": True}
            related_to["id"] = property_id
        elif client_id:
            related_to["type"] = {"client": True}
            related_to["id"] = client_id

        financial_details = {
            "amount": amount,
            "currency": currency,
            "payment_type": payment_type,
            "payment_status": payment_status,
            "payment_purpose": payment_purpose
        }

        return await self.log_activity(
            event_type="payment",
            title=title,
            description=description,
            related_to=related_to,
            participants=participants,
            financial_details=financial_details,
            notes=notes
        )

    # Логування розсилок
    async def log_email(
            self,
            title: str,
            description: str,
            recipients: List[str],
            client_ids: Optional[List[str]] = None,
            agent_id: Optional[str] = None,
            result: Optional[str] = None,
            notes: Optional[str] = None
    ) -> Optional[str]:
        """Логує електронний лист у журнал активності."""
        participants = {}
        if agent_id:
            participants["agents"] = [agent_id]
        if client_ids:
            participants["clients"] = client_ids

        metadata = {"recipients": recipients}

        return await self.log_activity(
            event_type="email",
            title=title,
            description=description,
            participants=participants,
            result=result,
            notes=notes,
            metadata=metadata
        )

    # Логування парсингу
    async def log_parsing(
            self,
            source: str,
            count: int,
            success: bool = True,
            error_message: Optional[str] = None
    ) -> bool:
        """Логує результати парсингу оголошень."""
        return await self._log_event(
            event_type="parsing",
            description=f"Парсинг з {source}: {count} оголошень {'успішно' if success else 'з помилкою'}",
            metadata={
                "source": source,
                "count": count,
                "success": success,
                "error_message": error_message
            }
        )

    # Автентифікація
    async def log_login_success(self) -> bool:
        return await self._log_event(
            event_type="login_success",
            description="Користувач успішно увійшов у систему"
        )

    async def log_login_failed(self, reason: str) -> bool:
        return await self._log_event(
            event_type="login_failed",
            description=f"Невдала спроба входу: {reason}",
            metadata={"reason": reason}
        )

    async def log_logout(self) -> bool:
        return await self._log_event(
            event_type="logout",
            description="Користувач вийшов із системи"
        )

    # Телеграм-операції
    async def log_telegram_login_success(self) -> bool:
        return await self._log_event(
            event_type="telegram_login_success",
            description="Користувач увійшов через Telegram"
        )

    async def log_telegram_login_failed(self) -> bool:
        return await self._log_event(
            event_type="telegram_login_failed",
            description="Невдала спроба входу через Telegram"
        )

    # Інші події
    async def log_password_change_request(self) -> bool:
        return await self._log_event(
            event_type="password_change_request",
            description="Користувач запросив зміну пароля"
        )

    async def log_custom_event(
            self,
            event_type: str,
            description: str,
            metadata: Optional[Dict] = None
    ) -> bool:
        """Запис будь-якої кастомної події."""
        return await self._log_event(event_type, description, metadata)