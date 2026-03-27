/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from 'react';
import {
  Container,
  Typography,
  Box,
  Card,
  CardContent,
  Grid,
  Button,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Chip,
  CircularProgress,
  Alert,
  AppBar,
  Toolbar,
  Paper,
  Divider,
  ThemeProvider,
  createTheme,
  CssBaseline,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions
} from '@mui/material';
import {
  Dns as ServerIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Refresh as RefreshIcon,
  Settings as SettingsIcon,
  Storage as StorageIcon,
  Hub as HubIcon,
  Queue as QueueIcon,
  Speed as SpeedIcon,
  InfoOutlined as InfoIcon // Новая иконка
} from '@mui/icons-material';
import { motion } from 'motion/react';

// Создаем тему оформления
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#388e3c',
    },
    background: {
      default: '#f4f6f8',
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h4: {
      fontWeight: 700,
    },
    h6: {
      fontWeight: 600,
    },
  },
  shape: {
    borderRadius: 12,
  },
});

interface JobeNode {
  url: string;
  name: string;
  languages: string[];
  power: string;
  active_runs?: number;
  is_online?: boolean;
}

interface HealthStatus {
  status: string;
  nodes: JobeNode[];
  algorithm: string;
  source?: string;
  queue: {
    active: number;
    limit: number;
    pending: number;
  };
}

export default function App() {
  const [status, setStatus] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<{ name: string, duration: number, success: boolean }[]>([]);
  const [testing, setTesting] = useState(false);
  const [totalTasksInput, setTotalTasksInput] = useState(1000);
  const [concurrencyInput, setConcurrencyInput] = useState(50);
  const [infoOpen, setInfoOpen] = useState(false);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/health');
      if (!response.ok) throw new Error('Не удалось получить данные о статусе');
      const data = await response.json();
      setStatus(data);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const runLoadTest = async () => {
    setTesting(true);
    setTestResults([]);

    const taskTemplates = [
      { name: 'Low (Print)', code: 'print("Hello world")', lang: 'python3' },
      { name: 'Medium (Single Library)', code: 'import numpy as np\na = np.array([1, 2, 3])\nprint(a.mean())', lang: 'python3' },
      { name: 'High (NumPy)', code: 'def check(a, b, c):\n if a > b:\n if b > c:\n for i in range(10):\n while a < 100:\n a += 1\n if a == 50: break\n elif a == c:\n for j in range(5): print(j)\n else:\n try:\n res = a / b\n except:\n res = 0\n return res\n# Повторим блоки, чтобы набрать controls > 10\nprint(check(1, 2, 3))\nprint(check(4, 5, 6))', lang: 'python3' },
    ];

    const TOTAL_TASKS = totalTasksInput;
    const BATCH_SIZE = concurrencyInput;
    const results: { name: string, duration: number, success: boolean }[] = [];

    for (let i = 0; i < TOTAL_TASKS; i += BATCH_SIZE) {
      const batch = Array.from({ length: Math.min(BATCH_SIZE, TOTAL_TASKS - i) }, (_, j) => {
        const task = taskTemplates[(i + j) % taskTemplates.length];
        const start = Date.now();
        return fetch('/jobe/index.php/restapi/runs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ run_spec: { language_id: task.lang, sourcecode: task.code } })
        })
        .then(res => ({ name: task.name, duration: Date.now() - start, success: res.ok }))
        .catch(() => ({ name: task.name, duration: Date.now() - start, success: false }));
      });

      const batchResults = await Promise.all(batch);
      results.push(...batchResults);
      setTestResults([...results]);
      fetchStatus();
    }

    setTesting(false);
  };

  const handleAlgorithmChange = async (newAlgo: string) => {
    try {
      const response = await fetch('/api/config/algorithm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ algorithm: newAlgo })
      });
      if (response.ok) {
        fetchStatus();
      }
    } catch (err) {
      console.error('Failed to change algorithm:', err);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ flexGrow: 1 }}>
        <AppBar position="static" elevation={0} sx={{ backgroundColor: 'white', borderBottom: '1px solid #e0e0e0' }}>
          <Toolbar>
            <HubIcon sx={{ color: 'primary.main', mr: 2 }} />
            <Typography variant="h6" component="div" sx={{ flexGrow: 1, color: 'text.primary' }}>
              Панель управления Jobe Proxy
            </Typography>
            <Button
              variant="outlined"
              startIcon={loading ? <CircularProgress size={20} /> : <RefreshIcon />}
              onClick={fetchStatus}
              disabled={loading}
            >
              Обновить
            </Button>
          </Toolbar>
        </AppBar>

        <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 3 }}>
              {error}
            </Alert>
          )}

          <Grid container spacing={3}>
            {/* Карточка статуса системы */}
            <Grid size={{ xs: 12, md: 4 }}>
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                <Card elevation={1}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                      <Typography color="textSecondary" variant="overline" sx={{ fontWeight: 'bold' }}>
                        Статус системы
                      </Typography>
                      {status?.status === 'ok' ? (
                        <CheckCircleIcon color="success" />
                      ) : (
                        <ErrorIcon color="error" />
                      )}
                    </Box>
                    <Typography variant="h4" component="div" sx={{ mb: 1 }}>
                      {status?.status === 'ok' ? 'Работает' : 'Ошибка'}
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      Прокси-сервер активен и распределяет трафик.
                    </Typography>
                  </CardContent>
                </Card>
              </motion.div>
            </Grid>

            {/* Карточка активных узлов */}
            <Grid size={{ xs: 12, md: 4 }}>
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
                <Card elevation={1}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                      <Typography color="textSecondary" variant="overline" sx={{ fontWeight: 'bold' }}>
                        Активные узлы
                      </Typography>
                      <ServerIcon color="primary" />
                    </Box>
                    <Typography variant="h4" component="div" sx={{ mb: 1 }}>
                      {status?.nodes.length || 0}
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      Количество настроенных экземпляров Jobe в кластере.
                    </Typography>
                  </CardContent>
                </Card>
              </motion.div>
            </Grid>

            {/* Карточка очереди задач */}
            <Grid size={{ xs: 12, md: 4 }}>
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
                <Card elevation={1}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                      <Typography color="textSecondary" variant="overline" sx={{ fontWeight: 'bold' }}>
                        Очередь задач
                      </Typography>
                      <QueueIcon color="action" />
                    </Box>
                    <Typography variant="h4" component="div" sx={{ mb: 1 }}>
                      {status?.queue?.active || 0} / {status?.queue?.limit || 0}
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      {status?.queue?.pending || 0} задач в ожидании.
                    </Typography>
                    <Box sx={{ mt: 1, height: 4, width: '100%', backgroundColor: '#eee', borderRadius: 2, overflow: 'hidden' }}>
                      <Box
                        sx={{
                          height: '100%',
                          width: `${Math.min(100, ((status?.queue?.active || 0) / (status?.queue?.limit || 1)) * 100)}%`,
                          backgroundColor: (status?.queue?.active || 0) >= (status?.queue?.limit || 0) ? '#f44336' : '#2196f3',
                          transition: 'width 0.3s ease'
                        }}
                      />
                    </Box>
                  </CardContent>
                </Card>
              </motion.div>
            </Grid>

            {/* Список серверов в кластере */}
            <Grid size={{ xs: 12 }}>
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
                <Paper elevation={1} sx={{ overflow: 'hidden' }}>
                  <Box sx={{ p: 2, backgroundColor: '#fafafa', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                      <Typography variant="h6">Конфигурация кластера</Typography>
                      {status?.source && (
                        <Chip
                          label={status.source === 'json' ? 'Из файла' : 'Из настроек Docker'}
                          size="small"
                          color={status.source === 'json' ? 'primary' : 'warning'}
                          variant="outlined"
                        />
                      )}
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                      <FormControl size="small" sx={{ minWidth: 200 }}>
                        <InputLabel>Алгоритм планирования</InputLabel>
                        <Select
                          value={status?.algorithm || 'smart_power'}
                          label="Алгоритм планирования"
                          onChange={(e) => handleAlgorithmChange(e.target.value)}
                          disabled={loading}
                        >
                          <MenuItem value="smart_power">Smart Power (Мощность + Анализ)</MenuItem>
                          <MenuItem value="round_robin">Round-Robin (Простой)</MenuItem>
                          <MenuItem value="weighted_round_robin">Weighted Round-Robin (Мощность + Round-Robin)</MenuItem>
                          <MenuItem value="least_active">Least Active (По нагрузке)</MenuItem>
                        </Select>
                      </FormControl>
                      <IconButton
                      color="primary"
                      onClick={() => setInfoOpen(true)}
                      title="Справка по алгоритмам"
                    >
                      <InfoIcon />
                    </IconButton>
                    </Box>
                  </Box>
                  <Divider />
                  <List disablePadding>
                    {status?.nodes.map((node, idx) => (
                      <React.Fragment key={idx}>
                        <ListItem sx={{ py: 2 }}>
                          <ListItemIcon>
                            <Box
                              sx={{
                                width: 12,
                                height: 12,
                                borderRadius: '50%',
                                // success.main если true (зеленый), error.main если false (красный)
                                backgroundColor: node.is_online ? 'success.main' : 'error.main',
                                 boxShadow: node.is_online ? '0 0 8px #4caf50' : '0 0 8px #f44336'
                              }}
                            />
                          </ListItemIcon>
                          <ListItemText
                            primary={
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                                  {node.name}
                                </Typography>
                                <Chip
                                  label={
                                    node.power === 'High' ? 'Высокая' :
                                    node.power === 'Medium' ? 'Средняя' :
                                    node.power === 'Low' ? 'Низкая' : node.power
                                  }
                                  size="small"
                                  color={node.power === 'High' ? 'error' : node.power === 'Medium' ? 'warning' : 'default'}
                                  sx={{ height: 20, fontSize: '0.65rem' }}
                                />
                                {node.active_runs !== undefined && (
                                  <Chip
                                    label={`Активно: ${node.active_runs}`}
                                    size="small"
                                    color="info"
                                    variant="outlined"
                                    sx={{ height: 20, fontSize: '0.65rem' }}
                                  />
                                )}
                              </Box>
                            }
                            secondary={
                              <Box>
                                <Typography variant="caption" sx={{ fontFamily: 'monospace', display: 'block' }}>
                                  {node.url}
                                </Typography>
                                <Box sx={{ mt: 0.5, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                                  {node.languages.map(lang => (
                                    <Chip key={lang} label={lang} size="small" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />
                                  ))}
                                </Box>
                              </Box>
                            }
                            primaryTypographyProps={{ component: 'div' }}
                            secondaryTypographyProps={{ component: 'div' }}
                          />
                        </ListItem>
                        {idx < status.nodes.length - 1 && <Divider component="li" />}
                      </React.Fragment>
                    ))}
                    {!status && !loading && (
                      <ListItem>
                        <ListItemText
                          primary="Серверы не обнаружены. Проверьте файл nodes.json."
                          sx={{ textAlign: 'center', fontStyle: 'italic', color: 'text.secondary' }}
                        />
                      </ListItem>
                    )}
                  </List>
                </Paper>
              </motion.div>
            </Grid>

            <Grid size={{ xs: 12 }}>
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
                <Paper sx={{ p: 2, mb: 3 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                    <Typography variant="h6">Нагрузочное тестирование</Typography>
                    <Button
                      variant="contained"
                      color="primary"
                      onClick={runLoadTest}
                      disabled={testing}
                      startIcon={testing ? <CircularProgress size={20} color="inherit" /> : <SpeedIcon />}
                    >
                      {testing ? 'Тестирование...' : `Запустить тест (${totalTasksInput} задач)`}
                    </Button>
                  </Box>

                  <Grid container spacing={2} sx={{ mb: 2 }}>
                    <Grid size={{ xs: 6 }}>
                      <TextField
                        label="Всего тестов"
                        type="number"
                        value={totalTasksInput}
                        onChange={(e) => setTotalTasksInput(parseInt(e.target.value) || 0)}
                        fullWidth
                        size="small"
                        disabled={testing}
                      />
                    </Grid>
                    <Grid size={{ xs: 6 }}>
                      <TextField
                        label="Пользователей (одновременно)"
                        type="number"
                        value={concurrencyInput}
                        onChange={(e) => setConcurrencyInput(parseInt(e.target.value) || 0)}
                        fullWidth
                        size="small"
                        disabled={testing}
                      />
                    </Grid>
                  </Grid>

                  <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                    Имитация реальной нагрузки: отправка {totalTasksInput} запросов пачками по {concurrencyInput} (имитация {concurrencyInput} пользователей).
                  </Typography>

                  {testResults.length > 0 && (
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      {testResults.map((res, i) => (
                        <Chip
                          key={i}
                          label={`${res.name}: ${res.duration}ms`}
                          color={res.success ? 'success' : 'error'}
                          variant="outlined"
                          size="small"
                        />
                      ))}
                      <Chip
                        label={`Среднее: ${(testResults.reduce((a, b) => a + b.duration, 0) / testResults.length).toFixed(0)}ms`}
                        sx={{ fontWeight: 'bold' }}
                        variant="filled"
                        size="small"
                      />
                    </Box>
                  )}
                </Paper>
              </motion.div>
            </Grid>

            {/* Инструкции */}
            <Grid size={{ xs: 12, md: 6 }}>
              <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 }}>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <SettingsIcon fontSize="small" /> Настройка Moodle
                </Typography>
                <Paper sx={{ p: 3, backgroundColor: '#1e293b', color: '#e2e8f0' }}>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace', mb: 1, color: '#10b981' }}>
                    # В настройках CodeRunner:
                  </Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                    Jobe Server: <Box component="span" sx={{ color: 'white' }}>proxy:3000</Box>
                  </Typography>
                  <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid #334155' }}>
                    <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                      Прокси автоматически обрабатывает путь /jobe/index.php/restapi
                    </Typography>
                  </Box>
                </Paper>
              </motion.div>
            </Grid>

            <Grid size={{ xs: 12, md: 6 }}>
              <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 }}>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <StorageIcon fontSize="small" /> Стек технологий
                </Typography>
                <Typography variant="body2" color="textSecondary" paragraph>
                  Система развернута с использованием Docker Compose и включает в себя:
                </Typography>
                <List dense>
                  <ListItem>
                    <ListItemText primary="Moodle 4.3" secondary="Основная платформа обучения" />
                  </ListItem>
                  <ListItem>
                    <ListItemText primary="JobeInABox" secondary="Среда выполнения кода (песочница)" />
                  </ListItem>
                  <ListItem>
                    <ListItemText primary="Python Proxy" secondary="Балансировщик нагрузки и API шлюз" />
                  </ListItem>
                  <ListItem>
                    <ListItemText primary="PostgreSQL" secondary="База данных для Moodle" />
                  </ListItem>
                  <ListItem>
                    <ListItemText primary="MongoDB" secondary="База данных для логов" />
                  </ListItem>
                </List>
              </motion.div>
            </Grid>
          </Grid>
        </Container>

        <Dialog
          open={infoOpen}
          onClose={() => setInfoOpen(false)}
          maxWidth="sm"
          fullWidth
        >
          <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SettingsIcon color="primary" />
            Алгоритмы планирования задач
          </DialogTitle>
          <DialogContent dividers>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                Smart Power (Умный)
              </Typography>
              <Typography variant="body2">
                Анализирует код (через AST-дерево или Regex) до его запуска. Оценивает количество циклов, условий и "тяжелых" библиотек (numpy, pandas).
                Направляет сложные задачи на мощные узлы, а простые — на легкие.
              </Typography>
            </Box>

            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                Round-Robin
              </Typography>
              <Typography variant="body2">
                Простое циклическое распределение. Задачи отправляются на узлы по очереди (1, 2, 3...), не учитывая их текущую нагрузку или сложность кода.
              </Typography>
            </Box>

            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                Weighted Round-Robin
              </Typography>
              <Typography variant="body2">
                Усовершенствованный Round-Robin. Учитывает "вес" (мощность) сервера. Сервер с пометкой <b>High</b> получит в 3 раза больше задач, чем <b>Low</b>, за один цикл обхода.
              </Typography>
            </Box>

            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                Least Active
              </Typography>
              <Typography variant="body2">
                Динамическое распределение. Прокси отслеживает количество активных сетевых соединений с каждым узлом и отправляет новую задачу на тот сервер, который в данный момент наименее загружен.
              </Typography>
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setInfoOpen(false)} color="primary" variant="contained">
              Понятно
            </Button>
          </DialogActions>
        </Dialog>

      </Box>
    </ThemeProvider>
  );
}
