import asyncio
import httpx
import time
import random
import sys
import ast
import re

PROXY_URL = 'http://localhost:3000/jobe/index.php/restapi/runs'

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
                heavy_imports += 1  # Упрощенно для теста считаем все импорты в задачах

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
        self.nodes = [
            {'url': 'http://jobe-low:80', 'name': 'Jobe-Low', 'power': 'Low'},
            {'url': 'http://jobe-mid:80', 'name': 'Jobe-Medium', 'power': 'Medium'},
            {'url': 'http://jobe-high:80', 'name': 'Jobe-High', 'power': 'High'}
        ]
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
    start = time.time()
    # "Бронируем" узел в планировщике
    node = scheduler.acquire_node(task['code'])
    complexity = analyze_complexity(task['code'])

    try:
        resp = await client.post(PROXY_URL, json={
            'run_spec': {'language_id': task['language'], 'sourcecode': task['code']}
        }, timeout=60.0)

        duration = (time.time() - start) * 1000
        sys.stdout.write('.' if resp.status_code == 200 else 'F')
        sys.stdout.flush()

        return {
            'success': resp.status_code == 200,
            'complexity': complexity,
            'node': node['name'],
            'duration': duration
        }
    finally:
        # Освобождаем узел
        scheduler.release_node(node['url'])


async def start_load_test(total_tasks=100, concurrency=10, algo="smart_power"):
    print(f'=== Starting Load Test | Algo: {algo} ===')
    scheduler = SchedulerEmulator(algorithm=algo)
    results = []
    start_time = time.time()

    async with httpx.AsyncClient() as client:
        queue = asyncio.Queue()
        for i in range(total_tasks): queue.put_nowait(i + 1)

        async def worker():
            while not queue.empty():
                task_id = await queue.get()
                task = random.choice(tasks)
                res = await run_task(client, task, task_id, scheduler)
                results.append(res)
                queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(min(concurrency, total_tasks))]
        await asyncio.gather(*workers)

    # Итоги
    # --- РАСЧЕТ ИТОГОВ ---
    end_time = time.time()
    total_duration_sec = end_time - start_time
    total_duration_ms = total_duration_sec * 1000
    throughput = len(results) / total_duration_sec if total_duration_sec > 0 else 0

    print(f'\n\n' + '=' * 40)
    print(f'        LOAD TEST FINAL RESULTS')
    print(f'=' * 40)
    print(f'Total Tasks Run:      {len(results)}')
    print(f'Total Time Taken:     {total_duration_sec:.2f} seconds ({total_duration_ms:.2f} ms)')
    print(f'Throughput:           {throughput:.2f} tasks/sec')
    print(f'=' * 40)

    print(f'\n=== Results by Predicted Complexity ===')
    for level in ['Low', 'Medium', 'High']:
        level_results = [r for r in results if r.get('complexity') == level]
        count = len(level_results)
        if count > 0:
            avg_time = sum([r['duration'] for r in level_results]) / count
            # Считаем процент от общего числа задач
            percentage = (count / len(results)) * 100
            print(f'{level:6}: {count:3} tasks ({percentage:4.1f}%) | Avg Response: {avg_time:8.2f}ms')
    print(f'=' * 40 + '\n')


if __name__ == "__main__":
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    concurrency = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    algo = sys.argv[3] if len(sys.argv) > 3 else "smart_power"
    asyncio.run(start_load_test(total, concurrency, algo))