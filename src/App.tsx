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
  CssBaseline
} from '@mui/material';
import { 
  Dns as ServerIcon, 
  Security as ShieldIcon, 
  CheckCircle as CheckCircleIcon, 
  Error as ErrorIcon, 
  Refresh as RefreshIcon,
  Settings as SettingsIcon,
  Storage as StorageIcon,
  Hub as HubIcon
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

interface HealthStatus {
  status: string;
  servers: string[];
  nextServer: string;
}

export default function App() {
  const [status, setStatus] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
                      {status?.servers.length || 0}
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      Количество настроенных экземпляров Jobe в кластере.
                    </Typography>
                  </CardContent>
                </Card>
              </motion.div>
            </Grid>

            {/* Карточка API шлюза */}
            <Grid size={{ xs: 12, md: 4 }}>
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
                <Card elevation={1}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                      <Typography color="textSecondary" variant="overline" sx={{ fontWeight: 'bold' }}>
                        API Шлюз
                      </Typography>
                      <ShieldIcon sx={{ color: '#f57c00' }} />
                    </Box>
                    <Typography variant="h4" component="div" sx={{ mb: 1 }}>
                      Активен
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      Пересылка X-API-KEY включена для всех запросов.
                    </Typography>
                  </CardContent>
                </Card>
              </motion.div>
            </Grid>

            {/* Список серверов в кластере */}
            <Grid size={{ xs: 12 }}>
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
                <Paper elevation={1} sx={{ overflow: 'hidden' }}>
                  <Box sx={{ p: 2, backgroundColor: '#fafafa', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="h6">Конфигурация кластера</Typography>
                    <Chip label="Round-Robin Планирование" size="small" variant="outlined" />
                  </Box>
                  <Divider />
                  <List disablePadding>
                    {status?.servers.map((server, idx) => (
                      <React.Fragment key={idx}>
                        <ListItem sx={{ py: 2 }}>
                          <ListItemIcon>
                            <Box 
                              sx={{ 
                                width: 12, 
                                height: 12, 
                                borderRadius: '50%', 
                                backgroundColor: status.nextServer === server ? 'success.main' : 'grey.400',
                                boxShadow: status.nextServer === server ? '0 0 8px #4caf50' : 'none'
                              }} 
                            />
                          </ListItemIcon>
                          <ListItemText 
                            primary={server} 
                            primaryTypographyProps={{ sx: { fontFamily: 'monospace', fontSize: '0.9rem' } }}
                          />
                          {status.nextServer === server && (
                            <Chip 
                              label="Следующий в очереди" 
                              color="success" 
                              size="small" 
                              sx={{ fontWeight: 'bold', fontSize: '0.7rem' }} 
                            />
                          )}
                        </ListItem>
                        {idx < status.servers.length - 1 && <Divider component="li" />}
                      </React.Fragment>
                    ))}
                    {!status && !loading && (
                      <ListItem>
                        <ListItemText 
                          primary="Серверы не обнаружены. Проверьте переменные окружения." 
                          sx={{ textAlign: 'center', fontStyle: 'italic', color: 'text.secondary' }} 
                        />
                      </ListItem>
                    )}
                  </List>
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
                    Jobe Server: <Box component="span" sx={{ color: 'white' }}>http://proxy:3000</Box>
                  </Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                    Jobe Port: <Box component="span" sx={{ color: 'white' }}>3000</Box>
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
                    <ListItemText primary="Node.js Proxy" secondary="Балансировщик нагрузки и API шлюз" />
                  </ListItem>
                  <ListItem>
                    <ListItemText primary="PostgreSQL" secondary="База данных для Moodle" />
                  </ListItem>
                </List>
              </motion.div>
            </Grid>
          </Grid>
        </Container>
      </Box>
    </ThemeProvider>
  );
}
