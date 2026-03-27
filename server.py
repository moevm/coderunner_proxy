import os
import json
import asyncio
import time
import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import re
import ast
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI()

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
PORT = 3000
NODES_FILE = os.path.join(os.getcwd(), 'nodes.json')
MAX_CONCURRENT_RUNS = int(os.getenv('MAX_CONCURRENT_RUNS', '10'))
JOBE_BASE_PATH = '/jobe/index.php/restapi'
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://mongodb:27017')

# MongoDB Setup
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client.proxy_db
logs_collection = db.logs

# Semaphore for queueing
class CountedSemaphore(asyncio.Semaphore):
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


run_semaphore = CountedSemaphore(MAX_CONCURRENT_RUNS)
active_runs = 0
current_server_index = 0
scheduling_algorithm = "smart_power"  # Default: smart_power, round_robin, weighted_round_robin, least_active
node_active_counts = {}  # Track active runs per node URL
node_status_cache = {}  # Хранит {url: last_known_status_bool}


# --- НОВЫЙ БЛОК: Middleware для логирования ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()

    # Захват тела запроса
    request_body = b""
    if request.method in ["POST", "PUT"]:
        request_body = await request.body()

        async def receive():
            return {"type": "http.request", "body": request_body}

        request._receive = receive

    # Выполнение запроса
    response = await call_next(request)

    process_time = time.perf_counter() - start_time

    # Логируем только API и Jobe запросы
    path = request.url.path
    if path.startswith(("/api", "/jobe")) and path != "/api/health":
        log_entry = {
            "timestamp": datetime.datetime.utcnow(),
            "method": request.method,
            "path": path,
            "status_code": response.status_code,
            "process_time_ms": round(process_time * 1000, 2),
            "load_stats": {
                "active_runs": active_runs,
                "waiting_in_queue": run_semaphore.waiting
            },
            "target_server": getattr(request.state, "target_server", "none")
        }

        # Попытка распарсить payload
        try:
            if request_body:
                log_entry["request_payload"] = json.loads(request_body)
        except:
            if request_body:
                log_entry["request_payload"] = str(request_body)[:500]

        # Фоновое сохранение
        asyncio.create_task(save_to_mongo(log_entry))

    return response


# --- КОНЕЦ БЛОКА ---

async def save_to_mongo(log_entry):
    try:
        await logs_collection.insert_one(log_entry)
    except Exception as e:
        print(f"[Mongo Error] {e}")

class JobeNode:
    def __init__(self, url: str, name: str, languages: List[str], power: str):
        self.url = url
        self.name = name
        self.languages = languages
        self.power = power


def get_jobe_nodes() -> List[Dict[str, Any]]:
    try:
        if os.path.exists(NODES_FILE):
            with open(NODES_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if config.get('nodes') and isinstance(config['nodes'], list):
                    return config['nodes']
    except Exception as e:
        print(f'[Proxy] Error reading nodes.json: {e}')

    # Fallback
    urls = os.getenv('JOBE_SERVERS', 'http://jobe1:80,http://jobe2:80').split(',')
    return [
        {
            'url': url,
            'name': url.split('//')[1] if '//' in url else url,
            'languages': ['python3', 'c', 'cpp'],
            'power': 'Medium'
        } for url in urls
    ]


def analyze_complexity(code: str) -> str:
    # Список библиотек, которые мы считаем "тяжелыми" (Data Science, ML, Сети)
    HEAVY_LIBRARIES = {
        'numpy', 'pandas', 'scipy', 'sklearn', 'torch', 'tensorflow',
        'matplotlib', 'cv2', 'PIL', 'nltk', 'spacy', 'requests',
        'httpx', 'sqlalchemy', 'keras', 'statsmodels'
    }

    try:
        # --- AST АНАЛИЗ (Для Python) ---
        tree = ast.parse(code)

        lines = len(code.splitlines())
        nodes_count = len(list(ast.walk(tree)))

        controls = 0
        heavy_imports = 0

        for node in ast.walk(tree):
            # 1. Считаем циклы и условия
            if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)):
                controls += 1

            # 2. Анализируем импорты
            # Обработка 'import numpy'
            if isinstance(node, ast.Import):
                for alias in node.names:
                    base_module = alias.name.split('.')[0]
                    if base_module in HEAVY_LIBRARIES:
                        heavy_imports += 1
                        print(f"[Proxy] Found heavy import: {base_module}")

            # Обработка 'from pandas import DataFrame'
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    base_module = node.module.split('.')[0]
                    if base_module in HEAVY_LIBRARIES:
                        heavy_imports += 1
                        print(f"[Proxy] Found heavy import: {base_module}")

        # Формула расчета: импорты дают самый большой вес
        # Каждый тяжелый импорт добавляет 5 баллов (сразу выводит в Medium/High)
        score = (lines / 20) + controls + (nodes_count / 50) + (heavy_imports * 7)

        print(f'[Proxy] AST analysis score: {score:.2f} (Imports: {heavy_imports}, Controls: {controls})')

        if score > 10: return 'High'
        if score > 3: return 'Medium'
        return 'Low'

    except Exception as e:
        # --- REGEX АНАЛИЗ (Фолбэк для других языков или синтаксических ошибок) ---
        lines = len(code.splitlines())

        # Считаем управляющие конструкции
        controls = len(re.findall(r'\b(if|for|while|switch|catch|elif|else if)\b', code))

        # Считаем импорты тяжелых библиотек через регулярки
        heavy_pattern = r'^\s*(?:import|from)\s+(' + '|'.join(HEAVY_LIBRARIES) + r')\b'
        heavy_imports = len(re.findall(heavy_pattern, code, re.MULTILINE))

        # Специфические тяжелые функции
        heavy_funcs = len(re.findall(r'\b(dot|read_csv|fit|predict|train|evaluate|compile|recursive)\b', code))

        score = (lines / 20) + controls + (heavy_imports * 7) + (heavy_funcs * 2)
        print(f'[Proxy] Regex analysis score: {score:.2f} (Imports: {heavy_imports}, Lines: {lines})')

        if score > 10: return 'High'
        if score > 3: return 'Medium'
        return 'Low'


def get_power_weight(power: str) -> int:
    p = power.lower()
    if p == 'high': return 3
    if p == 'medium': return 2
    return 1


async def get_next_server(req_path: str, body: Optional[Dict[str, Any]]) -> str:
    global current_server_index, scheduling_algorithm
    nodes = get_jobe_nodes()
    if not nodes: return 'http://jobe1:80'

    # Initialize active counts for new nodes
    for n in nodes:
        if n['url'] not in node_active_counts:
            node_active_counts[n['url']] = 0

    online_nodes = [n for n in nodes if node_status_cache.get(n['url'], True)]

    filtered_nodes = online_nodes if online_nodes else nodes

    print(online_nodes, filtered_nodes)

    # 1. Фильтрация по языку (всегда выполняется)
    if req_path.endswith('/runs') and body and 'run_spec' in body:
        lang = body['run_spec'].get('language_id')
        lang_nodes = [n for n in filtered_nodes if lang in n.get('languages', [])]
        if lang_nodes:
            filtered_nodes = lang_nodes

    # 2. Применение алгоритмов планирования
    if scheduling_algorithm == "least_active":
        # Sort by active count, then by weight as a tie-breaker
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

    else:  # smart_power (Default)
        # Filter by complexity if it's a run request
        if req_path.endswith('/runs') and body and 'run_spec' in body:
            code = body['run_spec'].get('sourcecode', '')
            if code:
                target_power = analyze_complexity(code)
                power_nodes = [n for n in filtered_nodes if n.get('power', '').lower() == target_power.lower()]
                if power_nodes:
                    filtered_nodes = power_nodes

        # Then use weighted round-robin on the filtered set
        weighted_urls = []
        for n in filtered_nodes:
            weight = get_power_weight(n.get('power', 'Medium'))
            weighted_urls.extend([n['url']] * weight)

        if current_server_index >= len(weighted_urls):
            current_server_index = 0

        server_url = weighted_urls[current_server_index]
        current_server_index = (current_server_index + 1) % len(weighted_urls)
        return server_url


async def check_node_health(url: str, name: str) -> bool:
    """Проверяет доступность узла и логирует изменения состояния."""
    async with httpx.AsyncClient() as client:
        try:
            # Легкий запрос для проверки жизни
            response = await client.get(f"{url}{JOBE_BASE_PATH}/languages", timeout=2.0)
            current_status = (response.status_code == 200)
        except Exception:
            current_status = False

    # Логирование только при ИЗМЕНЕНИИ состояния
    previous_status = node_status_cache.get(url, True)  # По умолчанию считаем, что всё ок

    if current_status != previous_status:
        node_status_cache[url] = current_status

        # Формируем запись для MongoDB
        log_entry = {
            "timestamp": datetime.datetime.utcnow(),
            "type": "node_status_change",
            "node_name": name,
            "node_url": url,
            "is_online": current_status,
            "message": f"Server {name} is now {'ONLINE' if current_status else 'OFFLINE'}"
        }

        # Отправляем в базу
        asyncio.create_task(save_to_mongo(log_entry))
        print(f"[Proxy] {log_entry['message']}")

    return current_status

@app.get("/api/health")
async def health():
    nodes = get_jobe_nodes()
    # Add active counts to node info
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
    global scheduling_algorithm, current_server_index
    data = await request.json()
    algo = data.get("algorithm")
    valid_algos = ["smart_power", "round_robin", "weighted_round_robin", "least_active"]

    if algo in valid_algos:
        scheduling_algorithm = algo
        current_server_index = 0  # Reset index when changing algo
        return {"status": "success", "algorithm": scheduling_algorithm}
    else:
        raise HTTPException(status_code=400, detail=f"Invalid algorithm. Must be one of: {', '.join(valid_algos)}")


@app.api_route("/jobe/index.php/restapi/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_jobe(request: Request, path: str):
    global active_runs
    endpoint = f"/{path}"
    is_run_request = endpoint == "/runs" and request.method == "POST"

    body = None
    if request.method in ["POST", "PUT"]:
        try:
            body = await request.json()
        except:
            pass

    # Если это не запрос на выполнение кода, обрабатываем один раз без повторов
    if not is_run_request:
        target_server = await get_next_server(endpoint, body)
        request.state.target_server = target_server
        return await forward_request(request, endpoint, body, target_server)

    # Логика повторов для запросов /runs
    max_retries = 5  # Можно настроить количество попыток
    attempt = 0

    async with run_semaphore:
        while attempt < max_retries:
            attempt += 1
            # Выбираем сервер внутри цикла, чтобы при повторе получить новый узел
            target_server = await get_next_server(endpoint, body)
            request.state.target_server = target_server

            active_runs += 1
            node_active_counts[target_server] = node_active_counts.get(target_server, 0) + 1

            try:
                response = await forward_request(request, endpoint, body, target_server)

                # Если сервер вернул 500, бросаем исключение для перехода в блок except и повтора
                if response.status_code == 500:
                    print(f"[Proxy] Retry {attempt}: Node {target_server} returned 500. Retrying...")
                    raise HTTPException(status_code=500)

                # Если всё хорошо (не 500), возвращаем результат в Moodle
                return response

            except Exception as e:
                # Если это последняя попытка, возвращаем ошибку
                if attempt >= max_retries:
                    print(f"[Proxy] All {max_retries} attempts failed.")
                    return JSONResponse(content={"error": "All backend nodes failed after retries"}, status_code=500)

                # Небольшая пауза перед повтором, чтобы дать узлам восстановиться
                await asyncio.sleep(2)
            finally:
                # Всегда уменьшаем счетчики перед следующим циклом или выходом
                active_runs -= 1
                node_active_counts[target_server] = max(0, node_active_counts.get(target_server, 0) - 1)
        return None


async def forward_request(request: Request, endpoint: str, body: Any, target_server: str):
    url = f"{target_server}{JOBE_BASE_PATH}{endpoint}"

    headers = {k: v for k, v in request.headers.items() if k.lower() in ['content-type', 'x-api-key']}

    async with httpx.AsyncClient() as client:
        try:
            if endpoint == "/languages" and request.method == "GET":
                # Special handling for languages union
                nodes = get_jobe_nodes()
                all_langs = set()
                for n in nodes:
                    for l in n.get('languages', []):
                        all_langs.add(l)

                # Fetch one to get format
                resp = await client.request(
                    method=request.method,
                    url=url,
                    headers=headers,
                    timeout=5.0
                )
                formatted = [[l, "unknown"] for l in all_langs]
                return JSONResponse(content=formatted)

            resp = await client.request(
                method=request.method,
                url=url,
                content=await request.body(),
                headers=headers,
                timeout=30.0
            )
            return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
        except Exception as e:
            print(f"[Proxy] Error forwarding: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)


# Serve static files
if os.path.exists('dist'):
    # Mount assets directory specifically for efficiency
    if os.path.exists('dist/assets'):
        app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")


    # Catch-all for SPA fallback
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("jobe/"):
            raise HTTPException(status_code=404)

        # Check if file exists in dist
        file_path = os.path.join("dist", full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        # Fallback to index.html
        return FileResponse("dist/index.html")
else:
    @app.get("/")
    async def root_fallback():
        return {"message": "Frontend not built. Run 'npm run build' to generate the dist directory."}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
