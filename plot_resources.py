import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

from matplotlib.ticker import FuncFormatter


def plot_proxy_metrics(file_path='proxy_metrics.json'):
    if not os.path.exists(file_path):
        print(f"Файл {file_path} не найден.")
        return

    with open(file_path, 'r') as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12))
    fig.suptitle('Показатели использования ресурсов прокси', fontsize=22)

    # Настройки для оси X (общие для всех графиков)
    start_time = df['timestamp'].min()
    end_time = df['timestamp'].max()

    def time_formatter(x, pos):
        dt = mdates.num2date(x)
        return f"{dt.strftime('%M:%S')}:{int(dt.microsecond / 1000):03d}"

    formatter = FuncFormatter(time_formatter)

    # Настройка точности времени на оси X
    for ax in [ax1, ax2, ax3]:
        ax.set_xlim(start_time, end_time)
        ax.xaxis.set_major_formatter(formatter)
        ax.xaxis.set_major_locator(plt.MaxNLocator(13))
        existing_ticks = list(ax.get_xticks())
        all_ticks = sorted(list(set(existing_ticks + [mdates.date2num(start_time), mdates.date2num(end_time)])))
        ax.set_xticks(all_ticks)
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.set_xlabel('Время (m:s:ms)', fontsize=17)
        plt.setp(ax.get_xticklabels(), rotation=30, ha='right')

    # 1. График CPU
    ax1.plot(df['timestamp'], df['cpu_usage_percent'], color='red', label='CPU Usage (%)')
    ax1.set_ylabel('CPU, %', fontsize=18)
    ax1.legend(fontsize=12)

    # 2. График RSS (Физическая память)
    rss_mean = df['memory_rss_mb'].mean()
    y_min = rss_mean - 2.5
    y_max = rss_mean + 2.5
    ax2.plot(df['timestamp'], df['memory_rss_mb'], color='blue', label='Memory RSS (MB)')
    ax2.set_ylim(y_min, y_max)

    ax2.axhline(rss_mean, color='orange', linestyle=':', linewidth=2, label=f'Среднее: {rss_mean:.2f}')

    current_ticks = list(ax2.get_yticks())
    current_ticks = [t for t in current_ticks if abs(t - rss_mean) > (max(current_ticks) - min(current_ticks)) * 0.05]
    ax2.set_yticks(current_ticks + [rss_mean])

    ax2.set_ylabel('RSS, MB', fontsize=18)
    ax2.legend(fontsize=12)

    # 3. График VMS (Виртуальная память)
    ax3.plot(df['timestamp'], df['memory_vms_mb'], color='green', label='Memory VMS (MB)')
    ax3.set_ylabel('VMS, MB', fontsize=18)
    ax3.legend(fontsize=12)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    plt.savefig('proxy_resources_graph.png')
    print(f"График сохранен. Начало: {start_time}, Конец: {end_time}")
    plt.show()


if __name__ == "__main__":
    plot_proxy_metrics()