import json
import pandas as pd
import matplotlib.pyplot as plt
import os


def plot_proxy_metrics(file_path='proxy_metrics.json'):
    if not os.path.exists(file_path):
        print(f"Файл {file_path} не найден. Сначала запустите нагрузочные тесты.")
        return

    with open(file_path, 'r') as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Создаем фигуру с тремя графиками
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    fig.suptitle('Proxy Resource Usage Metrics', fontsize=16)

    # График CPU
    ax1.plot(df['timestamp'], df['cpu_usage_percent'], color='red', label='CPU Usage (%)')
    ax1.set_ylabel('CPU %')
    ax1.grid(True, linestyle='--', alpha=0.7)
    ax1.legend()

    # График RSS (Физическая память)
    ax2.plot(df['timestamp'], df['memory_rss_mb'], color='blue', label='Memory RSS (MB)')
    ax2.set_ylabel('RSS MB')
    ax2.grid(True, linestyle='--', alpha=0.7)
    ax2.legend()

    # График VMS (Виртуальная память)
    ax3.plot(df['timestamp'], df['memory_vms_mb'], color='green', label='Memory VMS (MB)')
    ax3.set_ylabel('VMS MB')
    ax3.set_xlabel('Time')
    ax3.grid(True, linestyle='--', alpha=0.7)
    ax3.legend()

    # Автоматический формат даты на оси X
    plt.gcf().autofmt_xdate()

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig('proxy_resources_graph.png')
    print("График сохранен в файл proxy_resources_graph.png")
    plt.show()


if __name__ == "__main__":
    plot_proxy_metrics()
