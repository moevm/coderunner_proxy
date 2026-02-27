#!/bin/bash
set -e

# Ensure git is installed for plugin management
if ! command -v git &> /dev/null; then
  echo 'Installing git...'
  apt-get update && apt-get install -y git
fi

if [ ! -f /var/www/html/config.php ]; then
  echo '--- Starting Moodle Initialization ---'
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
\$CFG->curlsecurityallowedhosts = 'proxy';
require_once(__DIR__ . '/lib/setup.php');
EOF
  echo '--- Moodle Initialization Complete ---'
fi

# Install/Verify CodeRunner plugins even if Moodle is already initialized
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
      echo "Error: Failed to install $name. Please check your internet connection."
      # Don't exit here to allow Moodle to start even if plugins fail
    fi
  else
    echo "$name is already installed."
  fi
}

install_plugin "https://github.com/trampgeek/moodle-qtype_coderunner.git" "/var/www/html/question/type/coderunner" "CodeRunner question type"
install_plugin "https://github.com/trampgeek/moodle-qbehaviour_adaptivemultipleresponse.git" "/var/www/html/question/behaviour/adaptivemultipleresponse" "Adaptive Multi-Response behaviour"
install_plugin "https://github.com/trampgeek/moodle-qbehaviour_adaptive_adapted_for_coderunner.git" "/var/www/html/question/behaviour/adaptive_adapted_for_coderunner" "Adaptive adapted for CodeRunner behaviour"

echo 'Ensuring directory permissions...'
mkdir -p /var/moodledata
chown -R www-data:www-data /var/moodledata
chmod -R 777 /var/moodledata
chown -R www-data:www-data /var/www/html

exec apache2-foreground
