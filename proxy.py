from flask import Flask, request, jsonify, Response
import requests
import json
import logging
from datetime import datetime
from config import Config

# Настройка логирования
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = Flask(__name__)


class JobeProxy:
    """Прокси для Jobe сервера"""

    def __init__(self, jobe_server_url):
        self.jobe_server_url = jobe_server_url.rstrip('/')
        logger.info(f"Jobe Proxy настроен на сервер: {self.jobe_server_url}")

    def forward_request(self, endpoint, method='POST', data=None):
        """Перенаправление запроса в Jobe сервер"""

        # URL для Jobe
        jobe_url = f"{self.jobe_server_url}/jobe/index.php/restapi/{endpoint}"

        logger.info(f"Перенаправление запроса на {jobe_url}")
        logger.debug(f"Метод: {method}, Данные: {data}")

        try:
            if method.upper() == 'POST':
                response = requests.post(
                    jobe_url,
                    headers=Config.JOBE_HEADERS,
                    json=data,
                    timeout=30
                )
            else:  # GET
                response = requests.get(
                    jobe_url,
                    headers=Config.JOBE_HEADERS,
                    timeout=10
                )

            logger.info(f"Ответ от Jobe: {response.status_code}")
            logger.debug(f"Ответ от Jobe: {response.text[:500]}")

            # Ответ без изменений
            return Response(
                response.content,
                status=response.status_code,
                content_type=response.headers.get('content-type', 'application/json')
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка подключения к Jobe: {e}")
            return self._error_response(f"Jobe server error: {str(e)}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return self._error_response(f"Internal error: {str(e)}")

    def _error_response(self, error_message):
        """создание ответа об ошибке"""
        error_data = {
            "error": True,
            "message": error_message,
            "timestamp": datetime.now().isoformat()
        }
        return jsonify(error_data), 500


# Инициализация прокси
jobe_proxy = JobeProxy(Config.JOBE_SERVER)


@app.route('/')
def index():
    """Главная страница - информация о прокси"""
    return jsonify({
        "service": "jobe-proxy",
        "version": "1.0.0",
        "jobe_server": Config.JOBE_SERVER,
        "endpoints": {
            "health": "/health",
            "languages": "/jobe/index.php/restapi/languages",
            "runs": "/jobe/index.php/restapi/runs"
        },
        "timestamp": datetime.now().isoformat()
    })


@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Проверяем соединение с Jobe
        response = requests.get(
            f"{Config.JOBE_SERVER}/jobe/index.php/restapi/languages",
            headers=Config.JOBE_HEADERS,
            timeout=5
        )

        jobe_status = "connected" if response.status_code == 200 else "disconnected"

        return jsonify({
            "status": "healthy",
            "jobe": jobe_status,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/jobe/index.php/restapi/<path:endpoint>', methods=['GET', 'POST'])
def proxy_request(endpoint):
    """
    Прокси-эндпоинт для всех запросов к Jobe.
    """

    # Логирование входящих запросов
    logger.info(f"Входящий запрос: {request.method} {endpoint}")
    logger.debug(f"Headers: {dict(request.headers)}")

    if request.method == 'POST':
        try:
            # Получение JSON данных
            if request.is_json:
                data = request.get_json()
            else:
                # Если не JSON, обработка raw
                data = request.get_data(as_text=True)
                if data:
                    try:
                        data = json.loads(data)
                    except:
                        data = {"raw_data": data}
                # Иначе, ничего
                else:
                    data = {}

            logger.debug(f"Получены данные: {json.dumps(data)[:500]}...")

        except Exception as e:
            logger.warning(f"Ошибка чтения JSON: {e}")
            data = {}

    else:  # GET запрос
        data = None

    # Перенаправление запроса в Jobe
    return jobe_proxy.forward_request(endpoint, request.method, data)


@app.route('/test', methods=['GET'])
def test_connection():
    """Тестовый эндпоинт для проверки работы"""
    # Тест для проверки связи с Jobe
    test_data = {
        "run_spec": {
            "language_id": "python3",
            "sourcecode": "print('Hello from Jobe Proxy')",
            "sourcefilename": "test.py"
        }
    }

    response = jobe_proxy.forward_request('runs', 'POST', test_data)

    if response.status_code == 200:
        try:
            result = json.loads(response.get_data(as_text=True))
            return jsonify({
                "test": "success",
                "jobe_response": result,
                "proxy_status": "working",
                "timestamp": datetime.now().isoformat()
            })
        except:
            return jsonify({
                "test": "success",
                "raw_response": response.get_data(as_text=True)[:500],
                "proxy_status": "working",
                "timestamp": datetime.now().isoformat()
            })
    else:
        return jsonify({
            "test": "failed",
            "status_code": response.status_code,
            "response": response.get_data(as_text=True)[:500],
            "timestamp": datetime.now().isoformat()
        })


if __name__ == '__main__':

    logger.info("=" * 60)
    logger.info(f"- Запуск Jobe Proxy на {Config.HOST}:{Config.PORT}")
    logger.info(f"- Целевой Jobe сервер: {Config.JOBE_SERVER}")
    logger.info("=" * 60)

    # Проверка соединения с Jobe при запуске
    try:
        response = requests.get(
            f"{Config.JOBE_SERVER}/jobe/index.php/restapi/languages",
            headers=Config.JOBE_HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            languages = response.json()
            logger.info(f"=== Jobe сервер доступен. Поддерживаемые языки: {', '.join(languages)} ===")
        else:
            logger.warning(f"+++ Jobe сервер ответил с кодом {response.status_code}")
    except Exception as e:
        logger.error(f"!!! Не удалось подключиться к Jobe серверу: {e} !!!")
        logger.error("Проверьте настройки JOBE_SERVER в конфигурации")

    app.run(host=Config.HOST, port=Config.PORT, debug=False)
