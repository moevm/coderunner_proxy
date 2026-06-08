FROM public.ecr.aws/docker/library/node:20-slim AS frontend-builder
WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build


FROM python:3.9-slim
WORKDIR /app

# Установка системных зависимостей для компиляции
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./

COPY --from=frontend-builder /app/dist ./dist

# Порт из переменной окружения PROXY_PORT (по умолчанию 3000)
EXPOSE 3000

# Запуск FastAPI приложения
CMD ["python", "server.py"]