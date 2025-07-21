"""
Системні коди та структури для журналу активності (activity_journal).

Цей модуль містить всі типи подій та їх metadata схеми для уніфікованого використання.
"""

from enum import Enum
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Типи подій для журналу активності."""
    
    # Комунікація з клієнтами
    CLIENT_CONTACT = "client_contact"
    CLIENT_CALL = "client_call"
    CLIENT_EMAIL = "client_email"
    CLIENT_MEETING = "client_meeting"
    CLIENT_SMS = "client_sms"
    
    # Показ нерухомості
    PROPERTY_VIEWING = "property_viewing"
    PROPERTY_VIRTUAL_TOUR = "property_virtual_tour"
    PROPERTY_PHOTOS_SENT = "property_photos_sent"
    
    # Фінансові операції
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_SENT = "payment_sent"
    COMMISSION_CALCULATED = "commission_calculated"
    DEPOSIT_RECEIVED = "deposit_received"
    
    # Документообіг
    DOCUMENT_SIGNED = "document_signed"
    DOCUMENT_SENT = "document_sent"
    DOCUMENT_RECEIVED = "document_received"
    CONTRACT_CREATED = "contract_created"
    
    # Процес угоди
    DEAL_STATUS_CHANGED = "deal_status_changed"
    DEAL_PRICE_NEGOTIATED = "deal_price_negotiated"
    DEAL_COMPLETED = "deal_completed"
    DEAL_CANCELLED = "deal_cancelled"
    
    # Маркетинг та реклама
    AD_CREATED = "ad_created"
    AD_UPDATED = "ad_updated"
    SOCIAL_MEDIA_POST = "social_media_post"
    WEBSITE_LISTING = "website_listing"
    
    # Системні події
    TASK_COMPLETED = "task_completed"
    REMINDER_SET = "reminder_set"
    NOTE_ADDED = "note_added"
    
    # Інше
    OTHER = "other"


class ContactMethod(str, Enum):
    """Способи контакту."""
    PHONE = "phone"
    EMAIL = "email"
    TELEGRAM = "telegram"
    VIBER = "viber"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    IN_PERSON = "in_person"
    VIDEO_CALL = "video_call"


class ClientMood(str, Enum):
    """Настрій клієнта."""
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class ClientInterest(str, Enum):
    """Рівень зацікавленості клієнта."""
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


class PaymentMethod(str, Enum):
    """Способи оплати."""
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    CARD = "card"
    CRYPTO = "crypto"
    OTHER = "other"


class DocumentType(str, Enum):
    """Типи документів."""
    CONTRACT = "contract"
    PASSPORT = "passport"
    ID_CARD = "id_card"
    CERTIFICATE = "certificate"
    PHOTO = "photo"
    PLAN = "plan"
    OTHER = "other"


# METADATA SCHEMAS ДЛЯ КОЖНОГО ТИПУ ПОДІЇ

class ClientContactMetadata(BaseModel):
    """Metadata для контакту з клієнтом."""
    contact_method: ContactMethod
    duration_minutes: Optional[int] = None
    client_mood: Optional[ClientMood] = None
    client_interest: Optional[ClientInterest] = None
    topics_discussed: Optional[List[str]] = None
    next_action_planned: Optional[str] = None
    follow_up_date: Optional[datetime] = None


class PropertyViewingMetadata(BaseModel):
    """Metadata для огляду нерухомості."""
    property_id: str
    viewing_date: datetime
    duration_minutes: Optional[int] = None
    attendees_count: Optional[int] = None
    client_reaction: Optional[ClientInterest] = None
    questions_asked: Optional[List[str]] = None
    concerns_raised: Optional[List[str]] = None
    next_steps: Optional[str] = None


class PaymentMetadata(BaseModel):
    """Metadata для платежів."""
    amount: float
    currency: str = "UAH"
    payment_method: PaymentMethod
    payment_purpose: Optional[str] = None
    invoice_number: Optional[str] = None
    bank_details: Optional[str] = None
    transaction_id: Optional[str] = None


class DocumentMetadata(BaseModel):
    """Metadata для документів."""
    document_type: DocumentType
    document_name: str
    file_size: Optional[int] = None
    file_format: Optional[str] = None
    signed_by: Optional[List[str]] = None
    valid_until: Optional[datetime] = None
    document_url: Optional[str] = None


class DealStatusMetadata(BaseModel):
    """Metadata для зміни статусу угоди."""
    old_status: str
    new_status: str
    reason: Optional[str] = None
    responsible_person: Optional[str] = None
    expected_completion_date: Optional[datetime] = None


class MarketingMetadata(BaseModel):
    """Metadata для маркетингових активностей."""
    platform: str  # facebook, instagram, olx, ria, etc.
    ad_type: Optional[str] = None
    budget: Optional[float] = None
    target_audience: Optional[str] = None
    reach: Optional[int] = None
    engagement: Optional[int] = None
    clicks: Optional[int] = None


class TaskMetadata(BaseModel):
    """Metadata для завдань."""
    task_type: str
    priority: Optional[str] = None  # high, medium, low
    deadline: Optional[datetime] = None
    assigned_to: Optional[str] = None
    completion_time_minutes: Optional[int] = None


class ActivityMetadataFactory:
    """Фабрика для створення правильних metadata об'єктів."""
    
    METADATA_SCHEMAS = {
        EventType.CLIENT_CONTACT: ClientContactMetadata,
        EventType.CLIENT_CALL: ClientContactMetadata,
        EventType.CLIENT_EMAIL: ClientContactMetadata,
        EventType.CLIENT_MEETING: ClientContactMetadata,
        EventType.CLIENT_SMS: ClientContactMetadata,
        
        EventType.PROPERTY_VIEWING: PropertyViewingMetadata,
        EventType.PROPERTY_VIRTUAL_TOUR: PropertyViewingMetadata,
        
        EventType.PAYMENT_RECEIVED: PaymentMetadata,
        EventType.PAYMENT_SENT: PaymentMetadata,
        EventType.DEPOSIT_RECEIVED: PaymentMetadata,
        
        EventType.DOCUMENT_SIGNED: DocumentMetadata,
        EventType.DOCUMENT_SENT: DocumentMetadata,
        EventType.DOCUMENT_RECEIVED: DocumentMetadata,
        EventType.CONTRACT_CREATED: DocumentMetadata,
        
        EventType.DEAL_STATUS_CHANGED: DealStatusMetadata,
        
        EventType.AD_CREATED: MarketingMetadata,
        EventType.AD_UPDATED: MarketingMetadata,
        EventType.SOCIAL_MEDIA_POST: MarketingMetadata,
        
        EventType.TASK_COMPLETED: TaskMetadata,
    }
    
    @classmethod
    def create_metadata(cls, event_type: EventType, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Створює валідний metadata об'єкт для заданого типу події.
        
        Args:
            event_type: Тип події
            data: Дані для metadata
            
        Returns:
            Dict з валідними metadata
        """
        schema_class = cls.METADATA_SCHEMAS.get(event_type)
        if schema_class:
            try:
                metadata_obj = schema_class(**data)
                return metadata_obj.model_dump(exclude_none=True)
            except Exception as e:
                # Якщо валідація не пройшла, повертаємо оригінальні дані
                return data
        return data
    
    @classmethod
    def get_available_codes(cls) -> Dict[str, Any]:
        """
        Повертає всі доступні коди для фронтенду.
        
        Returns:
            Dict з усіма кодами та їх описами
        """
        return {
            "event_types": {
                "client_communication": [
                    {"code": EventType.CLIENT_CONTACT, "name": "Контакт з клієнтом", "description": "Загальний контакт з клієнтом"},
                    {"code": EventType.CLIENT_CALL, "name": "Телефонний дзвінок", "description": "Розмова з клієнтом по телефону"},
                    {"code": EventType.CLIENT_EMAIL, "name": "Email листування", "description": "Відправка або отримання email"},
                    {"code": EventType.CLIENT_MEETING, "name": "Зустріч", "description": "Особиста зустріч з клієнтом"},
                    {"code": EventType.CLIENT_SMS, "name": "SMS повідомлення", "description": "Відправка SMS клієнту"},
                ],
                "property_activities": [
                    {"code": EventType.PROPERTY_VIEWING, "name": "Огляд нерухомості", "description": "Показ об'єкта клієнту"},
                    {"code": EventType.PROPERTY_VIRTUAL_TOUR, "name": "Віртуальний тур", "description": "Онлайн показ об'єкта"},
                    {"code": EventType.PROPERTY_PHOTOS_SENT, "name": "Відправка фото", "description": "Надсилання фотографій об'єкта"},
                ],
                "financial_operations": [
                    {"code": EventType.PAYMENT_RECEIVED, "name": "Отримання платежу", "description": "Надходження коштів"},
                    {"code": EventType.PAYMENT_SENT, "name": "Відправка платежу", "description": "Переказ коштів"},
                    {"code": EventType.DEPOSIT_RECEIVED, "name": "Отримання завдатку", "description": "Надходження завдатку або авансу"},
                ],
                "document_workflow": [
                    {"code": EventType.DOCUMENT_SIGNED, "name": "Підписання документа", "description": "Підписання договору або іншого документа"},
                    {"code": EventType.DOCUMENT_SENT, "name": "Відправка документа", "description": "Надсилання документа клієнту"},
                    {"code": EventType.CONTRACT_CREATED, "name": "Створення договору", "description": "Підготовка контракту"},
                ],
                "deal_management": [
                    {"code": EventType.DEAL_STATUS_CHANGED, "name": "Зміна статусу угоди", "description": "Оновлення статусу угоди"},
                    {"code": EventType.DEAL_COMPLETED, "name": "Завершення угоди", "description": "Успішне закриття угоди"},
                    {"code": EventType.DEAL_CANCELLED, "name": "Скасування угоди", "description": "Відміна угоди"},
                ],
                "marketing": [
                    {"code": EventType.AD_CREATED, "name": "Створення реклами", "description": "Розміщення оголошення"},
                    {"code": EventType.SOCIAL_MEDIA_POST, "name": "Пост в соцмережах", "description": "Публікація в соціальних мережах"},
                ],
                "system": [
                    {"code": EventType.TASK_COMPLETED, "name": "Виконання завдання", "description": "Завершення поставленого завдання"},
                    {"code": EventType.NOTE_ADDED, "name": "Додавання нотатки", "description": "Створення нотатки або коментаря"},
                ]
            },
            "contact_methods": [item.value for item in ContactMethod],
            "client_moods": [item.value for item in ClientMood],
            "client_interests": [item.value for item in ClientInterest],
            "payment_methods": [item.value for item in PaymentMethod],
            "document_types": [item.value for item in DocumentType],
        }


# Функції-помічники для зручності використання

def create_client_contact_entry(
    description: str,
    contact_method: str,
    duration_minutes: Optional[int] = None,
    client_mood: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Швидке створення запису про контакт з клієнтом."""
    metadata = ActivityMetadataFactory.create_metadata(
        EventType.CLIENT_CONTACT,
        {
            "contact_method": contact_method,
            "duration_minutes": duration_minutes,
            "client_mood": client_mood,
            **kwargs
        }
    )
    
    return {
        "event_type": EventType.CLIENT_CONTACT,
        "description": description,
        "metadata": metadata
    }


def create_payment_entry(
    description: str,
    amount: float,
    payment_method: str,
    currency: str = "UAH",
    **kwargs
) -> Dict[str, Any]:
    """Швидке створення запису про платіж."""
    metadata = ActivityMetadataFactory.create_metadata(
        EventType.PAYMENT_RECEIVED,
        {
            "amount": amount,
            "currency": currency,
            "payment_method": payment_method,
            **kwargs
        }
    )
    
    return {
        "event_type": EventType.PAYMENT_RECEIVED,
        "description": description,
        "metadata": metadata
    }


def create_property_viewing_entry(
    description: str,
    property_id: str,
    viewing_date: datetime,
    client_reaction: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Швидке створення запису про огляд нерухомості."""
    metadata = ActivityMetadataFactory.create_metadata(
        EventType.PROPERTY_VIEWING,
        {
            "property_id": property_id,
            "viewing_date": viewing_date.isoformat() if isinstance(viewing_date, datetime) else viewing_date,
            "client_reaction": client_reaction,
            **kwargs
        }
    )
    
    return {
        "event_type": EventType.PROPERTY_VIEWING,
        "description": description,
        "metadata": metadata
    } 