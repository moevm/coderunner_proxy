#!/bin/bash
set -e

# Обеспечение наличия git для загрузки плагинов
if ! command -v git &> /dev/null; then
  echo 'Installing git...'
  apt-get update && apt-get install -y git
fi

# Клонирование исходного кода Moodle и создание конфигурации
if [ ! -f /var/www/html/config.php ]; then
  echo '--- Starting Moodle Source Code Initialization ---'
  echo 'Cloning Moodle (this may take a few minutes)...'
  git clone --depth 1 --branch MOODLE_403_STABLE https://github.com/moodle/moodle.git /tmp/moodle
  echo 'Copying files...'
  cp -r /tmp/moodle/* /var/www/html/
  cp /tmp/moodle/.gitignore /var/www/html/

  echo 'Generating config.php...'
  cat <<EOF > /var/www/html/config.php
<?php
unset(\$CFG);
global \$CFG;
\$CFG = new stdClass();
\$CFG->dbtype    = 'pgsql';
\$CFG->dblibrary = 'native';
\$CFG->dbhost    = 'db';
\$CFG->dbname    = 'moodle';
\$CFG->dbuser    = 'moodle';
\$CFG->dbpass    = 'moodle';
\$CFG->prefix    = 'mdl_';
\$CFG->dboptions = array (
  'dbpersist' => 0,
  'dbport' => '',
  'dbsocket' => '',
);
\$CFG->wwwroot   = 'http://localhost:8080';
\$CFG->dataroot  = '/var/moodledata';
\$CFG->admin     = 'admin';
\$CFG->directorypermissions = 0777;
require_once(__DIR__ . '/lib/setup.php');
EOF
  echo '--- Moodle Source Code Initialization Complete ---'
fi

# Установка плагинов CodeRunner (ДО установки базы данных)
echo 'Checking CodeRunner plugins...'
export GIT_TERMINAL_PROMPT=0

install_plugin() {
  local repo=$1
  local dest=$2
  local name=$3

  if [ ! -d "$dest/.git" ]; then
    echo "Installing $name..."
    rm -rf "$dest"
    mkdir -p "$(dirname "$dest")"
    if git clone --depth 1 "$repo" "$dest"; then
      echo "$name installed successfully."
    else
      echo "Error: Failed to install $name."
    fi
  else
    echo "$name is already installed."
  fi
}

install_plugin "https://github.com/trampgeek/moodle-qtype_coderunner.git" "/var/www/html/question/type/coderunner" "CodeRunner question type"
install_plugin "https://github.com/trampgeek/moodle-qbehaviour_adaptivemultipleresponse.git" "/var/www/html/question/behaviour/adaptivemultipleresponse" "Adaptive Multi-Response behaviour"
install_plugin "https://github.com/trampgeek/moodle-qbehaviour_adaptive_adapted_for_coderunner.git" "/var/www/html/question/behaviour/adaptive_adapted_for_coderunner" "Adaptive adapted for CodeRunner behaviour"

# Выставление корректных прав перед установкой
echo 'Setting directory permissions...'
mkdir -p /var/moodledata
chown -R www-data:www-data /var/moodledata
chmod -R 777 /var/moodledata
chown -R www-data:www-data /var/www/html

# Ожидание доступности контейнера PostgreSQL
echo "Waiting for PostgreSQL to be ready..."
until bash -c "cat < /dev/null > /dev/tcp/db/5432" 2>/dev/null; do
    echo "PostgreSQL is unavailable - sleeping"
    sleep 2
done
echo "PostgreSQL is online."

# Инициализация и наполнение структуры БД таблицами Moodle
if [ ! -f /var/moodledata/.db_initialized ]; then
  echo '--- Starting Moodle Database Schema Installation ---'

  # Запуск CLI установщика от имени www-data
  if su -s /bin/bash www-data -c "php /var/www/html/admin/cli/install_database.php \
      --agree-license \
      --adminemail='admin@example.com' \
      --adminpass='AdminPassword123!' \
      --fullname='Moodle Local Site' \
      --shortname='moodle'"; then

      touch /var/moodledata/.db_initialized
      echo '--- Moodle Database Installed Successfully ---'
  else
      echo 'Error: Database installation failed.'
      exit 1
  fi
else
  echo 'Database schema is already initialized. Running database upgrades if necessary...'
  su -s /bin/bash www-data -c "php /var/www/html/admin/cli/upgrade.php --non-interactive"
fi

# Проверка прав перед стартом веб-сервера
chown -R www-data:www-data /var/moodledata
chown -R www-data:www-data /var/www/html

echo 'Starting Apache Web Server...'
exec apache2-foreground