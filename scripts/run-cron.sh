#!/bin/sh

# Exit on error
set -e

# Default schedule: everyday at 3 AM, configurable via APP_SCHEDULE env var
CRON_SCHEDULE_INTERNAL="${APP_SCHEDULE:-0 3 * * *}"

# Default arguments for the collect script, configurable via APP_ARGS env var
APP_ARGS_INTERNAL="${APP_ARGS:---all --overwrite --skip}"

# Full path to the Python script
PYTHON_SCRIPT_PATH="/app/subscribe/collect.py"

# Create a crontab file
echo "Creating crontab file with schedule: ${CRON_SCHEDULE_INTERNAL}"
echo "${CRON_SCHEDULE_INTERNAL} python -u ${PYTHON_SCRIPT_PATH} ${APP_ARGS_INTERNAL} > /proc/1/fd/1 2>/proc/1/fd/2" | crontab -

# List crontab entries for verification (optional, logs to container log)
crontab -l

# Start cron daemon in foreground
echo "Starting cron daemon..."
exec crond -f -n -L /dev/stdout
