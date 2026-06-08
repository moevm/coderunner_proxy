import os
import psutil
import json
import asyncio
import time
import datetime
import re
import io
import csv
from typing import List, Dict, Any, Optional
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from tree_sitter_languages import get_parser

app = FastAPI()  # Экземпляр приложения FastAPI

# Настройка CORS для разработки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.getenv('PROXY_PORT', '3000'))  # Порт, на котором запускается прокси-сервер
NODES_FILE = os.path.join(os.getcwd(), 'nodes.json')  # Путь к конфигурационному файлу со списком Jobe-узлов
METRICS_FILE = os.path.join(os.getcwd(), '/app/proxy_metrics.json')  # Путь к файлу сохранения локальных метрик
MAX_CONCURRENT_RUNS = int(os.getenv('MAX_CONCURRENT_RUNS', '10'))  # Лимит одновременно выполняемых запросов кода
JOBE_BASE_PATH = '/jobe/index.php/restapi'  # Базовый URL-путь для обращения к REST API Jobe
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://mongodb:27017')  # Строка подключения к базе данных MongoDB
LOGS_MAX_SIZE_MB = int(os.getenv('LOGS_MAX_SIZE_MB', '512'))  # Максимальный размер логов в мегабайтах
LOGS_MAX_SIZE_BYTES = LOGS_MAX_SIZE_MB * 1024 * 1024  # Максимальный размер логов в байтах для циклической коллекции
DEFAULT_ALGORITHM = os.getenv('DEFAULT_SCHEDULING_ALGORITHM',
                              'smart_power')  # Алгоритм распределения нагрузки по умолчанию
IF_STATS = bool(int(os.getenv('IF_STATS', '0')))  # Флаг включения или выключения сбора системных метрик

DEFAULT_HEAVY_LIBS = (
    "numpy,pandas,scipy,sklearn,torch,tensorflow,matplotlib,"
    "cv2,PIL,nltk,spacy,requests,httpx,sqlalchemy,keras,statsmodels"
)  # Перечень ресурсоемких библиотек по умолчанию

HEAVY_LIBRARIES = {
    lib.strip()
    for lib in os.getenv('HEAVY_LIBRARIES', DEFAULT_HEAVY_LIBS).split(',')
    if lib.strip()
}  # Очищенное множество ресурсоемких библиотек для проверки сложности кода

CONTROL_NODES = {
    'if_statement', 'for_statement', 'for_in_statement', 'while_statement',
    'try_statement', 'catch_clause', 'except_clause', 'with_statement',
    'switch_statement', 'do_statement', 'conditional_expression'
}  # Типы управляющих синтаксических узлов для анализа в Tree-sitter

IMPORT_NODES = {
    'import_statement', 'import_from_statement', 'import_declaration',
    'include_directive', 'using_directive', 'require_expression', 'package_clause'
}  # Типы синтаксических узлов импорта библиотек для анализа в Tree-sitter

process = psutil.Process(os.getpid())  # Объект текущего системного процесса для сбора метрик
client_session: Optional[httpx.AsyncClient] = None  # Единая глобальная сессия HTTPX клиента
scheduling_algorithm = DEFAULT_ALGORITHM  # Активный в данный момент алгоритм распределения нагрузки
mongo_client = AsyncIOMotorClient(MONGO_URI)  # Клиент асинхронного подключения к СУБД MongoDB
db = mongo_client.proxy_db  # Объект базы данных прокси-сервера
logs_collection = db.logs  # Коллекция документов логирования в MongoDB

active_runs = 0  # Счетчик текущих активных запросов на выполнение кода
current_server_index = 0  # Индекс текущего узла для алгоритмов циклического перебора
node_active_counts = {}  # Количество активных параллельных задач для каждого URL-адреса узла
node_status_cache = {}  # Последние известные статусы доступности узлов (онлайн/оффлайн)


class CountedSemaphore(asyncio.Semaphore):
    """Расширяет стандартный семафор функцией подсчета запросов в очереди"""

    def __init__(self, value=1):
        super().__init__(value)
        self._waiting = 0

    async def acquire(self):
        self._waiting += 1
        try:
            await super().acquire()
        finally:
            self._waiting -= 1

    @property
    def waiting(self):
        return self._waiting


run_semaphore = CountedSemaphore(MAX_CONCURRENT_RUNS)  # Семафор для ограничения одновременных запусков кода.


@app.on_event("startup")
async def startup_event():
    """Инициализирует подключение к базе данных и глобальную HTTPX сессию при старте"""
    global client_session
    await init_db()
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    client_session = httpx.AsyncClient(timeout=30.0, limits=limits)
    print("[Proxy] Global HTTPX Client initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Закрывает сессию HTTPX клиента при завершении работы приложения"""
    global client_session
    if client_session:
        await client_session.aclose()
        print("[Proxy] Global HTTPX Client closed")


async def init_db():
    """Инициализирует и создает циклическую коллекцию ограниченного размера для хранения логов"""
    global logs_collection
    existing = await db.list_collection_names()
    if "logs" not in existing:
        await db.create_collection("logs", capped=True, size=LOGS_MAX_SIZE_BYTES)
    logs_collection = db.logs



def save_metrics_to_json(stats: Dict[str, Any]):
    """Записывает переданные системные метрики производительности в локальный JSON-файл"""
    try:
        data = []
        if os.path.exists(METRICS_FILE) and os.path.getsize(METRICS_FILE) > 0:
            with open(METRICS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

        data.append(stats)
        data = data[-1000:]

        with open(METRICS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        print(f"[Metrics Error] {e}")


async def save_to_mongo(log_entry: Dict[str, Any]):
    """Сохраняет сформированный лог в базу данных MongoDB"""
    try:
        if logs_collection is not None:
            await logs_collection.insert_one(log_entry)
    except Exception as e:
        print(f"[Mongo Error] {e}")


def get_jobe_nodes() -> List[Dict[str, Any]]:
    """Возвращает список конфигураций всех Jobe-узлов из файла настроек или переменных среды"""
    try:
        if os.path.exists(NODES_FILE):
            with open(NODES_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if config.get('nodes') and isinstance(config['nodes'], list):
                    return config['nodes']
    except Exception as e:
        print(f'[Proxy] Error reading nodes.json: {e}')

    urls = os.getenv('JOBE_SERVERS', 'http://jobe1:80,http://jobe2:80').split(',')
    return [
        {
            'url': url,
            'name': url.split('//')[1] if '//' in url else url,
            'languages': ['python3', 'c', 'cpp'],
            'power': 'Medium'
        } for url in urls
    ]


def analyze_complexity(code: str, language: str = 'python') -> str:
    """Анализирует синтаксическую сложность переданного кода с помощью Tree-sitter"""
    try:
        code_bytes = code.encode('utf-8')
        parser = get_parser(language)
        tree = parser.parse(code_bytes)
        lines = len(code.splitlines())

        nodes = []
        stack = [tree.root_node] if tree.root_node else []
        while stack:
            current_node = stack.pop()
            nodes.append(current_node)
            stack.extend(current_node.children)

        nodes_count = len(nodes)
        controls = 0
        heavy_imports = 0

        for node in nodes:
            if node.type in CONTROL_NODES:
                controls += 1

            if node.type in IMPORT_NODES or 'import' in node.type:
                node_text = code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')
                for lib in HEAVY_LIBRARIES:
                    if re.search(r'\b' + re.escape(lib) + r'\b', node_text):
                        heavy_imports += 1
                        break

        score = (lines / 20) + controls + (nodes_count / 50) + (heavy_imports * 7)
        print(f'[Proxy] Tree-sitter score: {score:.2f} ({language.upper()})')

        if score > 10: return 'High'
        if score > 4: return 'Medium'
        return 'Low'

    except Exception as e:
        print(f"[Proxy] Tree-sitter failed: {e}. Falling back to basic line analysis.")
        lines = len(code.splitlines())
        if lines > 200: return 'High'
        if lines > 50: return 'Medium'
        return 'Low'


def get_power_weight(power: str) -> int:
    """Преобразует текстовое описание вычислительной мощности узла в целочисленный вес"""
    p = power.lower()
    if p == 'high': return 3
    if p == 'medium': return 2
    return 1



async def check_node_health(url: str, name: str) -> bool:
    """Проверяет текущую доступность Jobe-узла по HTTP и логирует изменения его статуса"""
    try:
        resp = await client_session.get(f"{url}/jobe/index.php/restapi/languages")
        current_status = resp.status_code == 200
    except:
        current_status = False

    previous_status = node_status_cache.get(url, True)
    moscow_tz = datetime.timezone(datetime.timedelta(hours=3))
    now_moscow = datetime.datetime.now(moscow_tz)

    if current_status != previous_status:
        node_status_cache[url] = current_status
        log_entry = {
            "timestamp": now_moscow.isoformat(),
            "type": "node_status_change",
            "node_name": name,
            "node_url": url,
            "is_online": current_status,
            "method": "SYSTEM",
            "path": f"Server {name} is now {'ONLINE' if current_status else 'OFFLINE'}",
            "status_code": 200 if current_status else 500,
            "message": f"Server {name} is now {'ONLINE' if current_status else 'OFFLINE'}"
        }
        asyncio.create_task(save_to_mongo(log_entry))
        print(f"[Proxy] {log_entry['message']}")

    return current_status


async def get_next_server(req_path: str, body: Optional[Dict[str, Any]]) -> str:
    """Выбирает оптимальный целевой сервер на основе активного алгоритма балансировки"""
    global current_server_index, scheduling_algorithm
    nodes = get_jobe_nodes()
    if not nodes: return 'http://jobe1:80'

    for n in nodes:
        if n['url'] not in node_active_counts:
            node_active_counts[n['url']] = 0

    online_nodes = [n for n in nodes if node_status_cache.get(n['url'], True)]
    filtered_nodes = online_nodes if online_nodes else nodes

    if req_path.endswith('/runs') and body and 'run_spec' in body:
        lang = body['run_spec'].get('language_id')
        lang_nodes = [n for n in filtered_nodes if lang in n.get('languages', [])]
        if lang_nodes:
            filtered_nodes = lang_nodes

    if scheduling_algorithm == "least_active":
        sorted_nodes = sorted(filtered_nodes, key=lambda n: (node_active_counts.get(n['url'], 0),
                                                             -get_power_weight(n.get('power', 'Medium'))))
        return sorted_nodes[0]['url']

    elif scheduling_algorithm == "round_robin":
        if current_server_index >= len(filtered_nodes):
            current_server_index = 0
        server_url = filtered_nodes[current_server_index]['url']
        current_server_index = (current_server_index + 1) % len(filtered_nodes)
        return server_url

    elif scheduling_algorithm == "weighted_round_robin":
        weighted_urls = []
        for n in filtered_nodes:
            weight = get_power_weight(n.get('power', 'Medium'))
            weighted_urls.extend([n['url']] * weight)

        if current_server_index >= len(weighted_urls):
            current_server_index = 0
        server_url = weighted_urls[current_server_index]
        current_server_index = (current_server_index + 1) % len(weighted_urls)
        return server_url

    else:  # smart_power
        if req_path.endswith('/runs') and body and 'run_spec' in body:
            code = body['run_spec'].get('sourcecode', '')
            lang_id = body['run_spec'].get('language_id', 'python3')

            lang_map = {'python3': 'python', 'nodejs': 'javascript'}
            ts_lang = lang_map.get(lang_id, lang_id)

            if code:
                target_power = analyze_complexity(code, ts_lang)
                power_nodes = [n for n in filtered_nodes if n.get('power', '').lower() == target_power.lower()]
                if power_nodes:
                    filtered_nodes = power_nodes

        weighted_urls = []
        for n in filtered_nodes:
            weight = get_power_weight(n.get('power', 'Medium'))
            weighted_urls.extend([n['url']] * weight)

        if current_server_index >= len(weighted_urls):
            current_server_index = 0

        server_url = weighted_urls[current_server_index]
        current_server_index = (current_server_index + 1) % len(weighted_urls)
        return server_url



async def forward_request(request: Request, endpoint: str, body: Any, target_server: str):
    """Перенаправляет входящий запрос на конкретный целевой сервер Jobe"""
    global client_session
    url = f"{target_server}{JOBE_BASE_PATH}{endpoint}"
    headers = {k: v for k, v in request.headers.items() if k.lower() in ['content-type', 'x-api-key']}

    try:
        if endpoint == "/languages" and request.method == "GET":
            nodes = get_jobe_nodes()
            all_langs = set()
            for n in nodes:
                for l in n.get('languages', []):
                    all_langs.add(l)

            await client_session.request(method="GET", url=url, headers=headers, timeout=5.0)
            formatted = [[l, "unknown"] for l in all_langs]
            return JSONResponse(content=formatted)

        resp = await client_session.request(
            method=request.method,
            url=url,
            content=await request.body(),
            headers=headers,
            timeout=30.0
        )
        return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
    except Exception as e:
        print(f"[Proxy] Error forwarding to {url}: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)



@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Перехватывает HTTP-запросы для выполнения аналитики, замера времени и журналирования"""
    path = request.url.path
    if path == "/api/logs":
        return await call_next(request)

    start_time = time.perf_counter()

    request_body = b""
    if request.method in ["POST", "PUT"]:
        request_body = await request.body()

        async def receive():
            return {"type": "http.request", "body": request_body}

        request._receive = receive

    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    process_time_ms = round(process_time * 1000, 2)
    response.headers["X-Process-Time"] = str(process_time_ms)

    if path.startswith(("/api", "/jobe")) and path not in ["/api/health", "/api/config/algorithm"]:
        moscow_tz = datetime.timezone(datetime.timedelta(hours=3))

        if IF_STATS:
            stats = {
                "timestamp": datetime.datetime.now(moscow_tz).isoformat(),
                "cpu_usage_percent": process.cpu_percent(),
                "memory_rss_mb": round(process.memory_info().rss / 1024 / 1024, 2),
                "memory_vms_mb": round(process.memory_info().vms / 1024 / 1024, 2)
            }
            save_metrics_to_json(stats)

        jobe_result = None

        if "restapi/runs" in path and response.status_code == 200:
            try:
                response_body = b""
                async for chunk in response.body_iterator:
                    response_body += chunk

                response = Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )

                res_json = json.loads(response_body.decode('utf-8'))
                outcome = res_json.get("outcome", 0)
                stdout = res_json.get("stdout", "").strip()
                stderr = res_json.get("stderr", "").strip()
                cmpinfo = res_json.get("cmpinfo", "").strip()

                if outcome == 15:
                    jobe_result = stdout if stdout else "Success (no stdout)"
                elif outcome == 11:
                    jobe_result = f"Compile Error: {cmpinfo}"
                elif outcome == 12:
                    jobe_result = f"Runtime Error: {stderr}"
                elif outcome == 13:
                    jobe_result = "Time Limit Exceeded"
                else:
                    jobe_result = f"Error (Outcome {outcome}): {stderr or cmpinfo or 'Unknown error'}"
            except Exception as e:
                jobe_result = f"Failed to parse Jobe response: {str(e)}"

        log_entry = {
            "timestamp": datetime.datetime.now(moscow_tz).isoformat(),
            "method": request.method,
            "path": path,
            "status_code": response.status_code,
            "process_time_ms": process_time_ms,
            "target_server": getattr(request.state, "target_server", "none"),
            "message": jobe_result,
        }
        asyncio.create_task(save_to_mongo(log_entry))

    return response


# --- Эндпоинты API ---

@app.get("/api/logs")
async def get_logs(limit: int = 50):
    """Возвращает список последних логов работы прокси-сервера из базы данных"""
    try:
        cursor = logs_collection.find().sort("$natural", -1).limit(limit)
        logs = await cursor.to_list(length=limit)
        for log in logs:
            log["_id"] = str(log["_id"])
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs/export")
async def export_logs_csv():
    """Формирует и отдает для скачивания файл формата CSV, содержащий все логи из БД"""
    if logs_collection is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    fields = [
        "timestamp", "method", "path", "status_code",
        "process_time_ms", "target_server", "type",
        "node_name", "node_url", "is_online", "message"
    ]

    async def csv_generator():
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        cursor = logs_collection.find().sort("$natural", 1)
        async for log in cursor:
            log.pop("_id", None)
            writer.writerow(log)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    timestamp_str = int(time.time())
    return StreamingResponse(
        csv_generator(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=coderunner_proxy_logs_{timestamp_str}.csv",
            "Cache-Control": "no-cache"
        }
    )


@app.get("/api/health")
async def health():
    """Возвращает агрегированную информацию о здоровье прокси, очередях и статусах узлов"""
    nodes = get_jobe_nodes()
    nodes_with_stats = []

    health_tasks = [check_node_health(n['url'], n['name']) for n in nodes]
    health_results = await asyncio.gather(*health_tasks)

    for i, n in enumerate(nodes):
        node_copy = n.copy()
        node_copy['active_runs'] = node_active_counts.get(n['url'], 0)
        node_copy['is_online'] = health_results[i]
        nodes_with_stats.append(node_copy)

    return {
        "status": "ok",
        "proxy_port": PORT,
        "nodes": nodes_with_stats,
        "algorithm": scheduling_algorithm,
        "queue": {
            "active": active_runs,
            "limit": MAX_CONCURRENT_RUNS,
            "pending": run_semaphore.waiting
        }
    }


@app.post("/api/config/algorithm")
async def set_algorithm(request: Request):
    """Изменяет текущий активный алгоритм распределения нагрузки между узлами"""
    global scheduling_algorithm, current_server_index
    data = await request.json()
    algo = data.get("algorithm")
    valid_algos = ["smart_power", "round_robin", "weighted_round_robin", "least_active"]

    if algo in valid_algos:
        scheduling_algorithm = algo
        current_server_index = 0
        return {"status": "success", "algorithm": scheduling_algorithm}
    else:
        raise HTTPException(status_code=400, detail=f"Invalid algorithm. Must be one of: {', '.join(valid_algos)}")


@app.api_route("/jobe/index.php/restapi/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_jobe(request: Request, path: str):
    """Маршрутизирует запросы к API Jobe, обрабатывая повторные попытки при сбоях"""
    global active_runs
    endpoint = f"/{path}"
    is_run_request = endpoint == "/runs" and request.method == "POST"

    body = None
    if request.method in ["POST", "PUT"]:
        try:
            body = await request.json()
        except:
            pass

    if not is_run_request:
        target_server = await get_next_server(endpoint, body)
        request.state.target_server = target_server
        return await forward_request(request, endpoint, body, target_server)

    max_retries = 5
    attempt = 0

    async with run_semaphore:
        while attempt < max_retries:
            attempt += 1
            target_server = await get_next_server(endpoint, body)
            request.state.target_server = target_server

            active_runs += 1
            node_active_counts[target_server] = node_active_counts.get(target_server, 0) + 1

            try:
                response = await forward_request(request, endpoint, body, target_server)
                if response.status_code == 500:
                    print(f"[Proxy] Retry {attempt}: Node {target_server} returned 500. Retrying...")
                    raise HTTPException(status_code=500)
                return response
            except Exception:
                if attempt >= max_retries:
                    print(f"[Proxy] All {max_retries} attempts failed.")
                    return JSONResponse(content={"error": "All backend nodes failed after retries"}, status_code=500)
                await asyncio.sleep(2)
            finally:
                active_runs -= 1
                node_active_counts[target_server] = max(0, node_active_counts.get(target_server, 0) - 1)
        return None


if os.path.exists('dist'):
    if os.path.exists('dist/assets'):
        app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")


    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Отдает файлы статики фронтенда или перенаправляет запросы на index.html для SPA"""
        if full_path.startswith("api/") or full_path.startswith("jobe/"):
            raise HTTPException(status_code=404)

        file_path = os.path.join("dist", full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        return FileResponse("dist/index.html")
else:
    @app.get("/")
    async def root_fallback():
        """Возвращает предупреждение в формате JSON, если папка с фронтендом не собрана"""
        return {"message": "Frontend not built. Run 'npm run build' to generate the dist directory."}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
