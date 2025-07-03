from fastapi import status, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional


class Response:
    @staticmethod
    def success(
            data: Optional[Dict[str, Any]] = None,
            message: str = "Operation successful",
            status_code: int = status.HTTP_200_OK
    ) -> JSONResponse:
        """
        Стандартна успішна відповідь сервера.

        :param data: Дані, які повертаються клієнту.
        :param message: Повідомлення про успішне виконання.
        :param status_code: HTTP статус-код (за замовчуванням 200).
        :return: JSONResponse із стандартизованою відповіддю.
        """
        content = {
            "status": "success",
            "message": message,
            "data": data,
            "status_code": status_code
        }
        return JSONResponse(content=content, status_code=status_code)

    @staticmethod
    def error(
            message: str = "An error occurred",
            status_code: int = status.HTTP_400_BAD_REQUEST,
            details: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """
        Стандартна відповідь сервера з помилкою.

        :param message: Повідомлення про помилку.
        :param status_code: HTTP статус-код (за замовчуванням 400).
        :param details: Додаткові деталі помилки.
        :return: JSONResponse із стандартизованою відповіддю.
        """
        content = {
            "status": "error",
            "message": message,
            "details": details,
            "status_code": status_code
        }
        return JSONResponse(content=content, status_code=status_code)