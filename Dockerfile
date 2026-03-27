FROM public.ecr.aws/docker/library/node:20-slim

WORKDIR /app

# Install Python
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm install

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "dev"]