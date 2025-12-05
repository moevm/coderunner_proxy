import os


class Config:
    # Jobe сервер
    JOBE_SERVER = os.getenv("JOBE_SERVER", "http://jobe:80")

    # Настройки прокси-сервера
    HOST = "0.0.0.0"
    PORT = int(os.getenv("PROXY_PORT", "5000"))

    # Логирование
    LOG_LEVEL = "INFO"

    # Headers для запросов к Jobe
    JOBE_HEADERS = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }


config = Config()
