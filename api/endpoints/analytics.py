from fastapi import Depends, HTTPException, status, Request, Query
from typing import Dict, Any, Optional, List
from api.response import Response
from api.exceptions.auth_exceptions import AuthException, AuthErrorCode
from tools.database import Database
from tools.event_logger import EventLogger
from datetime import datetime, timedelta
from api.jwt_handler import JWTHandler


class AnalyticsEndpoints:
    def __init__(self):
        self.db = Database()
        self.jwt_handler = JWTHandler()

    async def get_dashboard_stats(self, request: Request) -> Dict[str, Any]:
        """
        Отримати статистику для дашборда (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Підрахунок основних метрик
            total_properties = await self.db.properties.count({"status": "active"})
            total_clients = await self.db.users.count_documents({"user_type": "client", "client_status": "active"})
            total_deals = await self.db.deals.count({})
            total_agents = await self.db.agents.count({"status": "active"})
            
            # Метрики за останній місяць
            last_month = datetime.utcnow() - timedelta(days=30)
            new_properties_last_month = await self.db.properties.count({
                "created_at": {"$gte": last_month},
                "status": "active"
            })
            new_clients_last_month = await self.db.users.count_documents({
                "user_type": "client",
                "created_at": {"$gte": last_month}
            })
            deals_last_month = await self.db.deals.count({
                "created_at": {"$gte": last_month}
            })
            
            # Активні угоди
            active_deals = await self.db.deals.count({
                "status": {"$in": ["active", "negotiation", "pending"]}
            })
            
            # Загальна вартість угод
            deals_pipeline = await self.db.deals.aggregate([
                {"$match": {"status": {"$in": ["active", "negotiation", "pending"]}}},
                {"$group": {"_id": None, "total_value": {"$sum": "$price"}}}
            ])
            total_deals_value = deals_pipeline[0]["total_value"] if deals_pipeline else 0
            
            stats = {
                "properties": {
                    "total": total_properties,
                    "new_last_month": new_properties_last_month
                },
                "clients": {
                    "total": total_clients,
                    "new_last_month": new_clients_last_month
                },
                "deals": {
                    "total": total_deals,
                    "active": active_deals,
                    "new_last_month": deals_last_month,
                    "total_value": total_deals_value
                },
                "agents": {
                    "total": total_agents
                }
            }
            
            return Response.success({"stats": stats})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні статистики дашборда: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_sales_report(
        self,
        request: Request,
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None)
    ) -> Dict[str, Any]:
        """
        Отримати звіт з продажів (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Формування фільтрів дат
            date_filter = {}
            if start_date and end_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    date_filter = {"created_at": {"$gte": start_dt, "$lte": end_dt}}
                except ValueError:
                    return Response.error("Невірний формат дати", status_code=status.HTTP_400_BAD_REQUEST)
            else:
                # За замовчуванням - останні 30 днів
                start_dt = datetime.utcnow() - timedelta(days=30)
                date_filter = {"created_at": {"$gte": start_dt}}
            
            # Звіт з продажів
            sales_data = await self.db.deals.aggregate([
                {"$match": {**date_filter, "status": "completed"}},
                {"$group": {
                    "_id": {
                        "year": {"$year": "$created_at"},
                        "month": {"$month": "$created_at"},
                        "day": {"$dayOfMonth": "$created_at"}
                    },
                    "total_sales": {"$sum": "$price"},
                    "deals_count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ])
            
            # Звіт за агентами
            agents_report = await self.db.deals.aggregate([
                {"$match": {**date_filter, "status": "completed"}},
                {"$group": {
                    "_id": "$agent_id",
                    "total_sales": {"$sum": "$price"},
                    "deals_count": {"$sum": 1}
                }},
                {"$sort": {"total_sales": -1}}
            ])
            
            # Звіт за типами нерухомості
            property_types_report = await self.db.deals.aggregate([
                {"$match": {**date_filter, "status": "completed"}},
                {"$lookup": {
                    "from": "properties",
                    "localField": "property_id",
                    "foreignField": "_id",
                    "as": "property"
                }},
                {"$unwind": "$property"},
                {"$group": {
                    "_id": "$property.property_type",
                    "total_sales": {"$sum": "$price"},
                    "deals_count": {"$sum": 1}
                }},
                {"$sort": {"total_sales": -1}}
            ])
            
            report = {
                "sales_timeline": sales_data,
                "agents_performance": agents_report,
                "property_types_performance": property_types_report,
                "period": {
                    "start_date": start_date,
                    "end_date": end_date
                }
            }
            
            return Response.success({"report": report})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при формуванні звіту з продажів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_properties_analytics(
        self,
        request: Request,
        property_type: Optional[str] = Query(None),
        city: Optional[str] = Query(None)
    ) -> Dict[str, Any]:
        """
        Отримати аналітику нерухомості (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Формування фільтрів
            filters = {"status": "active"}
            if property_type:
                filters["property_type"] = property_type
            if city:
                filters["location.city"] = {"$regex": city, "$options": "i"}
            
            # Середня ціна за м²
            avg_price_per_sqm = await self.db.properties.aggregate([
                {"$match": filters},
                {"$group": {
                    "_id": None,
                    "avg_price_per_sqm": {"$avg": {"$divide": ["$price", "$area"]}}
                }}
            ])
            
            # Розподіл за типами нерухомості
            property_types_distribution = await self.db.properties.aggregate([
                {"$match": filters},
                {"$group": {
                    "_id": "$property_type",
                    "count": {"$sum": 1},
                    "avg_price": {"$avg": "$price"}
                }},
                {"$sort": {"count": -1}}
            ])
            
            # Розподіл за ціновими категоріями
            price_ranges = [
                {"range": "0-50k", "min": 0, "max": 50000},
                {"range": "50k-100k", "min": 50000, "max": 100000},
                {"range": "100k-200k", "min": 100000, "max": 200000},
                {"range": "200k+", "min": 200000, "max": float('inf')}
            ]
            
            price_distribution = []
            for price_range in price_ranges:
                count = await self.db.properties.count({
                    **filters,
                    "price": {"$gte": price_range["min"], "$lt": price_range["max"]}
                })
                price_distribution.append({
                    "range": price_range["range"],
                    "count": count
                })
            
            # Популярні міста
            cities_stats = await self.db.properties.aggregate([
                {"$match": filters},
                {"$group": {
                    "_id": "$location.city",
                    "count": {"$sum": 1},
                    "avg_price": {"$avg": "$price"}
                }},
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ])
            
            analytics = {
                "avg_price_per_sqm": avg_price_per_sqm[0]["avg_price_per_sqm"] if avg_price_per_sqm else 0,
                "property_types_distribution": property_types_distribution,
                "price_distribution": price_distribution,
                "cities_stats": cities_stats
            }
            
            return Response.success({"analytics": analytics})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні аналітики нерухомості: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_marketing_analytics(
        self,
        request: Request,
        campaign_id: Optional[str] = Query(None)
    ) -> Dict[str, Any]:
        """
        Отримати маркетингову аналітику (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Формування фільтрів
            filters = {}
            if campaign_id:
                filters["campaign_id"] = campaign_id
            
            # Загальна статистика лідів
            total_leads = await self.db.leads.count(filters)
            converted_leads = await self.db.leads.count({**filters, "status": "converted"})
            conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0
            
            # Ліди за джерелами
            leads_by_source = await self.db.leads.aggregate([
                {"$match": filters},
                {"$group": {
                    "_id": "$source",
                    "count": {"$sum": 1},
                    "converted": {"$sum": {"$cond": [{"$eq": ["$status", "converted"]}, 1, 0]}}
                }},
                {"$sort": {"count": -1}}
            ])
            
            # Ефективність кампаній
            campaigns_performance = await self.db.marketing_campaigns.aggregate([
                {"$lookup": {
                    "from": "leads",
                    "localField": "_id",
                    "foreignField": "campaign_id",
                    "as": "leads"
                }},
                {"$project": {
                    "name": 1,
                    "budget": 1,
                    "leads_count": {"$size": "$leads"},
                    "converted_leads": {
                        "$size": {
                            "$filter": {
                                "input": "$leads",
                                "cond": {"$eq": ["$$this.status", "converted"]}
                            }
                        }
                    }
                }},
                {"$addFields": {
                    "conversion_rate": {
                        "$cond": [
                            {"$eq": ["$leads_count", 0]},
                            0,
                            {"$multiply": [{"$divide": ["$converted_leads", "$leads_count"]}, 100]}
                        ]
                    },
                    "cost_per_lead": {
                        "$cond": [
                            {"$eq": ["$leads_count", 0]},
                            0,
                            {"$divide": ["$budget", "$leads_count"]}
                        ]
                    }
                }},
                {"$sort": {"conversion_rate": -1}}
            ])
            
            analytics = {
                "overview": {
                    "total_leads": total_leads,
                    "converted_leads": converted_leads,
                    "conversion_rate": round(conversion_rate, 2)
                },
                "leads_by_source": leads_by_source,
                "campaigns_performance": campaigns_performance
            }
            
            return Response.success({"analytics": analytics})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні маркетингової аналітики: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def get_agents_performance(
        self,
        request: Request,
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None)
    ) -> Dict[str, Any]:
        """
        Отримати аналітику продуктивності агентів (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Формування фільтрів дат
            date_filter = {}
            if start_date and end_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    date_filter = {"created_at": {"$gte": start_dt, "$lte": end_dt}}
                except ValueError:
                    return Response.error("Невірний формат дати", status_code=status.HTTP_400_BAD_REQUEST)
            
            # Продуктивність агентів
            agents_performance = await self.db.deals.aggregate([
                {"$match": {**date_filter}},
                {"$group": {
                    "_id": "$agent_id",
                    "total_deals": {"$sum": 1},
                    "completed_deals": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                    "total_value": {"$sum": "$price"},
                    "avg_deal_value": {"$avg": "$price"}
                }},
                {"$lookup": {
                    "from": "agents",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "agent"
                }},
                {"$unwind": {"path": "$agent", "preserveNullAndEmptyArrays": True}},
                {"$project": {
                    "agent_name": {"$concat": ["$agent.first_name", " ", "$agent.last_name"]},
                    "total_deals": 1,
                    "completed_deals": 1,
                    "total_value": 1,
                    "avg_deal_value": 1,
                    "success_rate": {
                        "$cond": [
                            {"$eq": ["$total_deals", 0]},
                            0,
                            {"$multiply": [{"$divide": ["$completed_deals", "$total_deals"]}, 100]}
                        ]
                    }
                }},
                {"$sort": {"total_value": -1}}
            ])
            
            # Топ агенти за кількістю угод
            top_agents_by_deals = await self.db.deals.aggregate([
                {"$match": {**date_filter, "status": "completed"}},
                {"$group": {
                    "_id": "$agent_id",
                    "deals_count": {"$sum": 1}
                }},
                {"$lookup": {
                    "from": "agents",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "agent"
                }},
                {"$unwind": {"path": "$agent", "preserveNullAndEmptyArrays": True}},
                {"$project": {
                    "agent_name": {"$concat": ["$agent.first_name", " ", "$agent.last_name"]},
                    "deals_count": 1
                }},
                {"$sort": {"deals_count": -1}},
                {"$limit": 10}
            ])
            
            analytics = {
                "agents_performance": agents_performance,
                "top_agents_by_deals": top_agents_by_deals,
                "period": {
                    "start_date": start_date,
                    "end_date": end_date
                }
            }
            
            return Response.success({"analytics": analytics})
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при отриманні аналітики агентів: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def export_report(
        self,
        request: Request,
        report_type: str = Query(...),
        format_type: str = Query("json")
    ) -> Dict[str, Any]:
        """
        Експортувати звіт (потребує авторизації).
        """
        try:
            # Отримання користувача з токена
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response.error("Токен авторизації обов'язковий", status_code=status.HTTP_401_UNAUTHORIZED)
            
            token = auth_header.split(" ")[1]
            payload = self.jwt_handler.decode_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                return Response.error("Невірний токен", status_code=status.HTTP_401_UNAUTHORIZED)
            
            # Підтримувані типи звітів
            supported_reports = ["sales", "properties", "marketing", "agents"]
            if report_type not in supported_reports:
                return Response.error(
                    f"Непідтримуваний тип звіту. Доступні: {', '.join(supported_reports)}",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Підтримувані формати
            supported_formats = ["json", "csv", "excel"]
            if format_type not in supported_formats:
                return Response.error(
                    f"Непідтримуваний формат. Доступні: {', '.join(supported_formats)}",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # TODO: Реалізувати експорт у різні формати
            # Поки що повертаємо інформацію про те, що експорт ініційовано
            
            # Логування події
            event_logger = EventLogger({"_id": user_id})
            await event_logger.log_custom_event(
                event_type="report_exported",
                description=f"Експортовано звіт: {report_type} у форматі {format_type}",
                metadata={"report_type": report_type, "format": format_type}
            )
            
            return Response.success({
                "message": f"Експорт звіту '{report_type}' у форматі '{format_type}' ініційовано",
                "report_type": report_type,
                "format": format_type,
                "status": "initiated"
            })
            
        except Exception as e:
            return Response.error(
                message=f"Помилка при експорті звіту: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 