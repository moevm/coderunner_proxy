import asyncio
import json
import httpx
import time
import random
import sys
import ast
import os

# URL прокси, задать в соответствии с env (по умолчанию 3000)
PROXY_URL = 'http://localhost:3000/jobe/index.php/restapi/runs'

# Имя файла для хранения узлов
nodes_file = 'nodes.json'

HEAVY_LIBRARIES = {
    'numpy', 'pandas', 'scipy', 'sklearn', 'torch', 'tensorflow',
    'matplotlib', 'cv2', 'PIL', 'nltk', 'spacy', 'requests',
    'httpx', 'sqlalchemy', 'keras', 'statsmodels'
}

def analyze_complexity(code: str) -> str:
    try:
        tree = ast.parse(code)
        lines = len(code.splitlines())
        nodes_count = len(list(ast.walk(tree)))
        controls = 0
        heavy_imports = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)):
                controls += 1
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                heavy_imports += 1

        score = (lines / 20) + controls + (nodes_count / 50) + (heavy_imports * 7)
        if score > 10: return 'High'
        if score > 4: return 'Medium'
        return 'Low'
    except Exception:
        return 'Low'

class SchedulerEmulator:
    def __init__(self, algorithm="smart_power"):
        self.algorithm = algorithm
        self.index = 0
        # Виртуальные узлы
        try:
            if os.path.exists(nodes_file):
                with open(nodes_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.nodes = data.get('nodes', [])
                print(f"--- Loaded {len(self.nodes)} nodes from {nodes_file} ---")
            else:
                print(f"--- Warning: {nodes_file} not found. Using default nodes. ---")
                self.nodes = [
                    {'url': 'http://jobe-low:80', 'name': 'Jobe-Low', 'power': 'Low'}
                ]
        except Exception as e:
            print(f"--- Error loading nodes: {e}. Using empty list. ---")
            self.nodes = []
        # Счетчик активных задач на каждом узле (для least_active)
        self.node_active_counts = {n['url']: 0 for n in self.nodes}

    def get_power_weight(self, power: str) -> int:
        p = power.lower()
        if p == 'high': return 3
        if p == 'medium': return 2
        return 1

    def acquire_node(self, code: str):
        """Выбирает узел и увеличивает счетчик его нагрузки."""
        node = self._select_node(code)
        self.node_active_counts[node['url']] += 1
        return node

    def release_node(self, node_url: str):
        """Уменьшает счетчик нагрузки узла после завершения задачи."""
        self.node_active_counts[node_url] = max(0, self.node_active_counts[node_url] - 1)

    def _select_node(self, code: str):
        # 1. Least Active: берем тот, где меньше всего задач прямо сейчас
        if self.algorithm == "least_active":
            sorted_nodes = sorted(self.nodes, key=lambda n: (self.node_active_counts[n['url']],
                                                             -self.get_power_weight(n['power'])))
            return sorted_nodes[0]

        # 2. Round Robin: просто по кругу
        elif self.algorithm == "round_robin":
            node = self.nodes[self.index % len(self.nodes)]
            self.index += 1
            return node

        # 3. Weighted Round Robin: учитываем "вес" (High получает в 3 раза больше задач, чем Low)
        elif self.algorithm == "weighted_round_robin":
            weighted_list = []
            for n in self.nodes:
                weight = self.get_power_weight(n['power'])
                weighted_list.extend([n] * weight)

            node = weighted_list[self.index % len(weighted_list)]
            self.index += 1
            return node

        # 4. Smart Power (Default): анализ сложности + веса
        else:
            complexity = analyze_complexity(code)
            # Ищем узлы соответствующей мощности
            filtered = [n for n in self.nodes if n['power'].lower() == complexity.lower()]
            if not filtered: filtered = self.nodes

            # Внутри найденной группы используем Weighted RR
            weighted_list = []
            for n in filtered:
                weight = self.get_power_weight(n['power'])
                weighted_list.extend([n] * weight)

            node = weighted_list[self.index % len(weighted_list)]
            self.index += 1
            return node


# --- ЗАДАЧИ ---

tasks = [
    {
        'name': 'Low (Simple)',
        'language': 'python3',
        'code': 'print("Hello world")'
    },
    {
        'name': 'Medium (Single Library)',
        'language': 'python3',
        'code': 'import numpy as np\na = np.array([1, 2, 3])\nprint(a.mean())'
    },
    {
        'name': 'High (Brainfuck Logic)',
        'language': 'python3',
        'code': '''
def check(a, b, c):
    if a > b:
        if b > c:
            for i in range(10):
                while a < 100:
                    a += 1
                    if a == 50: break
        elif a == c:
            for j in range(5): print(j)
    else:
        try:
            res = a / b
        except:
            res = 0
    return res
# Повторим блоки, чтобы набрать controls > 10
print(check(1, 2, 3))
print(check(4, 5, 6))
'''
    }
]

# --- ЛОГИКА ТЕСТА ---
async def run_task(client, task, task_id, scheduler):
    max_retries = 5  # Соответствует логике в server.py
    attempt = 0

    while attempt < max_retries:
        attempt += 1
        start_total = time.time()

        # Выбор узла
        node = scheduler.acquire_node(task['code'])
        complexity = analyze_complexity(task['code'])

        try:
            resp = await client.post(PROXY_URL, json={
                'run_spec': {'language_id': task['language'], 'sourcecode': task['code']}
            }, timeout=60.0)

            # Проброс ошибки для активации повторного запуска
            if resp.status_code == 500:
                raise httpx.HTTPStatusError("Server Error", request=None, response=resp)

            receive_end = time.time()
            total_duration_ms = (receive_end - start_total) * 1000
            server_process_time_ms = float(resp.headers.get("X-Process-Time", 0))
            network_latency_ms = max(0, int(total_duration_ms - server_process_time_ms))

            sys.stdout.write('.' if attempt == 1 else 'R')  # '.' - успех, 'R' - успех после retry
            sys.stdout.flush()

            # Успешное завершение: освобождение узла и возвращение результата
            scheduler.release_node(node['url'])
            return {
                'success': True,
                'complexity': complexity,
                'node': node['name'],
                'total_ms': total_duration_ms,
                'server_ms': server_process_time_ms,
                'network_ms': network_latency_ms,
                'retries': attempt - 1
            }

        except (Exception, httpx.HTTPStatusError):
            # Освобождение узла текущей неудачной попытки
            scheduler.release_node(node['url'])

            if attempt < max_retries:
                # Пауза перед следующей попыткой
                await asyncio.sleep(2)
                continue
            else:
                sys.stdout.write('F')
                sys.stdout.flush()
                return None


def get_proxy_resources(metrics_file="proxy_metrics.json"):
    """Считывает метрики из файла и вычисляет средние значения."""
    try:
        if os.path.exists(metrics_file):
            with open(metrics_file, 'r', encoding='utf-8') as f:
                # чтение списка записей метрик
                data = json.load(f)

                if not data:
                    return 0, 0

                # Извлечение значения CPU и RSS
                cpu_values = [entry.get('cpu_usage_percent', 0) for entry in data]
                rss_values = [entry.get('memory_rss_mb', 0) for entry in data]

                avg_cpu = sum(cpu_values) / len(cpu_values)
                avg_rss = sum(rss_values) / len(rss_values)

                return avg_cpu, avg_rss
        return 0, 0
    except Exception as e:
        print(f"\nОшибка при чтении метрик: {e}")
        return 0, 0

async def start_load_test(total_tasks=100, concurrency=10, algo="smart_power", custom_code=None):
    print(f'=== Starting Load Test | Algo: {algo} ===')
    current_tasks = list(tasks)

    if custom_code:
        print(f'=== Custom code from file added to task pool ===')
        current_tasks.append({
            'name': 'Custom-High-File',
            'language': 'python3',
            'code': str(custom_code)
        })

    scheduler = SchedulerEmulator(algorithm=algo)
    results = []

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

    async with httpx.AsyncClient(limits=limits, timeout=60.0) as client:
        start_time_test = time.perf_counter()
        queue = asyncio.Queue()
        for i in range(total_tasks): queue.put_nowait(i + 1)

        async def worker():
            while True:
                try:
                    # Попытка достать из очереди задачу без ожидания
                    task_idx = queue.get_nowait()
                except asyncio.QueueEmpty:
                    # Только если очередь ТОЧНО пуста, выходим
                    break

                try:
                    task = random.choice(current_tasks)
                    res = await run_task(client, task, task_idx, scheduler)
                    results.append(res)
                except Exception as e:
                    # Падение задачи, логирование без завершения
                    print(f"\nWorker error: {e}")
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(min(concurrency, total_tasks))]
        await asyncio.gather(*workers)
        end_time_test = time.perf_counter()

    # Итоги
    # --- РАСЧЕТ ИТОГОВ ---
    avg_cpu, avg_rss = get_proxy_resources("proxy_metrics.json")
    valid_results = [r for r in results if r is not None and r['success']]
    total_duration_sec = end_time_test - start_time_test

    print(f'\n\n' + '=' * 40)
    print(f'        LOAD TEST FINAL RESULTS')
    print(f'=' * 40)

    avg_total = sum(r['total_ms'] for r in valid_results) / len(valid_results)
    avg_server = sum(r['server_ms'] for r in valid_results) / len(valid_results)
    avg_network = sum(r['network_ms'] for r in valid_results) / len(valid_results)
    throughput = len(valid_results) / total_duration_sec

    print(f'Общее время теста:    {total_duration_sec:.2f} сек')
    print(f'Пропускная способность: {throughput:.2f} запр/сек')
    print(f'-' * 40)
    print(f'Метрика задержки      |  Среднее время (ms)')
    print(f'-' * 40)
    print(f'Полный цикл (RTT)     |  {avg_total:10.2f} ms')
    print(f'Обработка сервером    |  {avg_server:10.2f} ms (Proxy + Jobe)')
    print(f'Сеть и ожидание       |  {avg_network:10.2f} ms (Client -> Server -> Client)')
    print(f'=' * 40)
    print(f'\n=== Потребление ресурсов прокси ===')
    print(f'Средняя нагрузка CPU:   {avg_cpu:.2f}%')
    print(f'Средняя память RSS:    {avg_rss:.2f} MB')
    print(f'=' * 40 + '\n')

    print(f'\n=== Анализ по сложности задач ===')
    for level in ['Low', 'Medium', 'High']:
        lvl_res = [r for r in valid_results if r['complexity'] == level]
        if lvl_res:
            a_total = sum(r['total_ms'] for r in lvl_res) / len(lvl_res)
            a_server = sum(r['server_ms'] for r in lvl_res) / len(lvl_res)
            pct = (len(lvl_res) / len(valid_results)) * 100
            print(f'{level:7} ({pct:4.1f}%) -> Всего: {a_total:8.2f}ms | Сервер: {a_server:8.2f}ms')
    print(f'=' * 40 + '\n')


if __name__ == "__main__":
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    concurrency = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    algo = sys.argv[3] if len(sys.argv) > 3 else "smart_power"
    file_path = sys.argv[4] if len(sys.argv) > 4 else None

    loaded_code = None
    if file_path and os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            loaded_code = f.read()

    asyncio.run(start_load_test(total, concurrency, algo, loaded_code))