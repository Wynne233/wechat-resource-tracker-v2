#!/usr/bin/env sh
set -eu

ROOT_DIR="${1:-/opt/wechat-resource-tracker-v2}"
CRON_LINE="30 2 * * 0 cd ${ROOT_DIR}/deploy/oracle && /usr/bin/docker compose exec -T api python -m app.jobs weekly-source-check >> /var/log/wechat-resource-tracker-weekly.log 2>&1"

(crontab -l 2>/dev/null | grep -F -v "app.jobs weekly-source-check" || true; echo "$CRON_LINE") | crontab -
echo "Installed weekly check for Sunday 02:30 server time."
