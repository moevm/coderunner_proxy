import express from 'express';
import axios from 'axios';
import { createServer as createViteServer } from 'vite';
import path from 'path';

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json());

  // Конфигурация для Jobe узлов
  const jobeServers = (process.env.JOBE_SERVERS || 'http://localhost:8080').split(',');
  let currentServerIndex = 0;

  const getNextServer = () => {
    const server = jobeServers[currentServerIndex];
    currentServerIndex = (currentServerIndex + 1) % jobeServers.length;
    return server;
  };

  console.log('Proxying to Jobe servers:', jobeServers);

  // Logger middleware
  app.use((req, res, next) => {
    console.log(`[Proxy] Incoming request: ${req.method} ${req.url}`);
    next();
  });

  // Jobe API Endpoints
  const JOBE_BASE_PATH = '/jobe/index.php/restapi';

  // Помощник по переадресации запросов
  const forwardToJobe = async (req: express.Request, res: express.Response, endpoint: string) => {
    const targetServer = getNextServer();
    const url = `${targetServer}${JOBE_BASE_PATH}${endpoint}`;
    
    console.log(`[Proxy] Forwarding to Jobe: ${url}`);
    
    try {
      const response = await axios({
        method: req.method,
        url: url,
        data: req.body,
        headers: {
          'Content-Type': 'application/json',
          'X-API-KEY': req.header('X-API-KEY') || '',
        },
        timeout: 20000, // timeout
      });
      
      console.log(`[Proxy] Jobe responded with status ${response.status}`);
      res.status(response.status).json(response.data);
    } catch (error: any) {
      console.error(`[Proxy] Error forwarding to ${url}:`, error.message);
      if (error.response) {
        res.status(error.response.status).json(error.response.data);
      } else {
        res.status(500).json({ error: 'Failed to connect to Jobe server', details: error.message });
      }
    }
  };

  // Универсальный маршрут для любого запроса на Jobe
  app.all(`${JOBE_BASE_PATH}/*`, (req, res) => {
    const endpoint = req.path.replace(JOBE_BASE_PATH, '');
    forwardToJobe(req, res, endpoint);
  });

  // Проверка работоспособности прокси-сервера
  app.get('/api/health', (req, res) => {
    res.json({ 
      status: 'ok', 
      servers: jobeServers,
      nextServer: jobeServers[currentServerIndex]
    });
  });

  // Промежуточное ПО для разработки (обслуживающее пользовательский интерфейс панели мониторинга)
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.join(__dirname, 'dist')));
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Jobe Proxy running on http://0.0.0.0:${PORT}`);
  });
}

startServer().catch(err => {
  console.error('Failed to start server:', err);
});
