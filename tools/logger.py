import logging
import colorlog


class Logger:
    def __init__(self):
        # Використовуємо root logger замість __name__
        self.logger = logging.getLogger()
        
        # Створюємо handler з кольоровим форматуванням
        handler = colorlog.StreamHandler()
        handler.setFormatter(
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
        
        self.logger.handlers = []  # Очищаємо попередні handlers
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def debug(self, message):
        self.logger.debug(message, stacklevel=2)

    def info(self, message):
        self.logger.info(message, stacklevel=2)

    def warning(self, message):
        self.logger.warning(message, stacklevel=2)

    def error(self, message):
        self.logger.error(message, stacklevel=2)


