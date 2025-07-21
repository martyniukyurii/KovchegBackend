import logging
import colorlog
import os
from pathlib import Path


class Logger:
    def __init__(self):
        # Використовуємо root logger замість __name__
        self.logger = logging.getLogger()
        
        # Створюємо handler з кольоровим форматуванням для консолі
        console_handler = colorlog.StreamHandler()
        console_handler.setFormatter(
            colorlog.ColoredFormatter(
                '%(log_color)s%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
                log_colors={
                    'DEBUG': 'cyan',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red,bg_white',
                }
            )
        )
        
        # Додаємо файловий handler для логів
        try:
            log_dir = Path("/app/logs")
            log_dir.mkdir(exist_ok=True)
            
            file_handler = logging.FileHandler(
                log_dir / "parser.log", 
                encoding='utf-8'
            )
            file_handler.setFormatter(
                logging.Formatter(
                    '%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
            )
            
            # Налаштовуємо ротацію логів
            from logging.handlers import RotatingFileHandler
            rotating_handler = RotatingFileHandler(
                log_dir / "parser.log",
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            rotating_handler.setFormatter(
                logging.Formatter(
                    '%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
            )
            
            self.logger.handlers = []  # Очищаємо попередні handlers
            self.logger.addHandler(console_handler)
            self.logger.addHandler(rotating_handler)
            
        except Exception as e:
            # Якщо не вдалося створити файловий handler, використовуємо тільки консольний
            self.logger.handlers = []
            self.logger.addHandler(console_handler)
            print(f"Warning: Could not create file logger: {e}")
        
        self.logger.setLevel(logging.INFO)

    def debug(self, message):
        self.logger.debug(message, stacklevel=2)

    def info(self, message):
        self.logger.info(message, stacklevel=2)

    def warning(self, message):
        self.logger.warning(message, stacklevel=2)

    def error(self, message):
        self.logger.error(message, stacklevel=2)


