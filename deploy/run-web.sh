#!/bin/bash
set -euo pipefail
set -a
source /home/numinga/.config/legal-consult/app.env
set +a
release=$(readlink -f /home/numinga/.local/share/legal-consult-deploy/current)
export APP_RELEASE=${release##*/}
export DJANGO_STATIC_ROOT=/var/www/legal-consult/releases/$APP_RELEASE
cd "$release/legal_consultant"
exec /home/numinga/legal_consult/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8001 --timeout 60 legal_consultant.wsgi:application
