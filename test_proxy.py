import requests
import json


def test_proxy():
    """Тестирование прокси-сервера"""

    proxy_url = "http://localhost:5000"

    print("Тестирование Jobe Proxy...")
    print()

    # 1. Главная страница
    print("1. Главная страница:")
    response = requests.get(f"{proxy_url}/")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {json.dumps(response.json(), indent=2)}")

    # 2. Health check
    print("\n2. Health check:")
    response = requests.get(f"{proxy_url}/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {json.dumps(response.json(), indent=2)}")

    # 3. Получение языков через прокси
    print("\n3. Получение языков (через прокси):")
    response = requests.get(f"{proxy_url}/jobe/index.php/restapi/languages")
    print(f"   Status: {response.status_code}")
    try:
        languages = response.json()
        print(f"   Languages: {languages}")
    except:
        print(f"   Response: {response.text[:200]}")

    # 4. Тестовый запуск кода через прокси
    print("\n4. Тестовый запуск кода:")

    test_code = {
        "run_spec": {
            "language_id": "python3",
            "sourcecode": """print("Hello, World!")
for i in range(5):
    print(f"Number: {i}")""",
            "sourcefilename": "test.py"
        }
    }

    response = requests.post(
        f"{proxy_url}/jobe/index.php/restapi/runs",
        json=test_code,
        headers={'Content-Type': 'application/json'}
    )

    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"   Outcome: {result.get('outcome')}")
        print(f"   Output: {result.get('stdout', '')}")
        if result.get('stderr'):
            print(f"   Stderr: {result.get('stderr')}")
    else:
        print(f"   Error: {response.text[:500]}")

    # 5. Тестовый эндпоинт
    print("\n5. Тестовый эндпоинт:")
    response = requests.get(f"{proxy_url}/test")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {json.dumps(response.json(), indent=2)}")

    print("\n" + "=" * 60)
    print("Тестирование завершено!")


if __name__ == "__main__":
    test_proxy()
