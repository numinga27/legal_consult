#!/usr/bin/env bash
# Explicit one-time rebuild on 176.53.224.200 after loss of the old host.
# Requires /root/legal-consult-recovery/seed.sqlite3 and recover-catalog.py.
# seed.sqlite3 MUST be the catalogue-only export produced by create-catalog-seed.py.
# Prerequisites: nginx supervisor git python3-venv python3-pip curl sudo fonts-dejavu-core.
set -Eeuo pipefail
umask 027
[[ $(id -u) == 0 ]] || exit 1
base=/root/legal-consult-recovery
repo=/home/numinga/legal_consult
runtime=/home/numinga/.config/legal-consult
state=/home/numinga/.local/share/legal-consult-deploy
test -f "$base/seed.sqlite3"
test -f "$base/recover-catalog.py"
if [[ -e "$runtime/app.env" ]]; then
    echo 'Runtime exists: inspect recovery checkpoint instead of rerunning bootstrap.' >&2
    exit 1
fi
id numinga >/dev/null 2>&1 || useradd --create-home --shell /bin/bash numinga
chmod 750 /home/numinga
install -d -m 700 -o numinga -g numinga /home/numinga/.config /home/numinga/.local /home/numinga/.local/share
install -d -m 700 -o numinga -g numinga "$runtime" "$state" "$state/backups"
install -d -m 755 -o numinga -g numinga /var/www/legal-consult /var/www/legal-consult/releases /var/www/legal-consult/media
install -d -m 755 /var/www/legal-consult-acme /var/www/legal-consult-acme/.well-known /var/www/legal-consult-acme/.well-known/acme-challenge
if [[ ! -d "$repo/.git" ]]; then
    runuser -u numinga -- git clone --quiet https://github.com/numinga27/legal_consult.git "$repo"
fi
runuser -u numinga -- python3 -m venv "$repo/venv"
runuser -u numinga -- "$repo/venv/bin/pip" install --quiet -r "$repo/deploy/requirements-recovery.txt"
runuser -u numinga -- "$repo/venv/bin/pip" freeze > "$state/recovery-requirements.txt"
python3 -m venv /opt/legal-consult-certbot
/opt/legal-consult-certbot/bin/pip install --quiet 'certbot==5.8.0'

# Restore the sanitized catalogue seed with SQLite's backup API and verify integrity.
python3 - "$base/seed.sqlite3" "$repo/legal_consultant/db.sqlite3" "$state/backups/recovery-seed-2026-09-10.sqlite3" <<'PY'
import sqlite3, sys
from pathlib import Path
source = sqlite3.connect(Path(sys.argv[1]).as_uri() + '?mode=ro', uri=True)
assert source.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
allowed = {'django_migrations', 'core_legaldirection', 'core_questionnaire',
           'core_question', 'core_answer', 'core_conclusion', 'core_answerconclusion',
           'core_documenttemplate'}
for (name,) in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
    if name not in allowed:
        assert source.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0] == 0, 'Seed must contain catalogue only'
for filename in sys.argv[2:]:
    path = Path(filename)
    with sqlite3.connect(path) as destination:
        source.backup(destination)
        assert destination.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    path.chmod(0o600)
source.close()
print('SEED RESTORE VERIFIED')
PY
chown numinga:numinga "$repo/legal_consultant/db.sqlite3" "$state/backups/recovery-seed-2026-09-10.sqlite3"
install -d -m 700 -o numinga -g numinga "$repo/legal_consultant/protected_media"
python3 - "$runtime/app.env" <<'PY'
import os, secrets, sys
values = {
 'DJANGO_SETTINGS_MODULE': 'legal_consultant.production_settings',
 'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
 'DJANGO_ALLOWED_HOSTS': 'www.k-urist.ru,k-urist.ru,176.53.224.200,127.0.0.1,localhost',
 'DJANGO_DB_PATH': '/home/numinga/legal_consult/legal_consultant/db.sqlite3',
 'DJANGO_STATIC_ROOT': '/var/www/legal-consult/bootstrap-static',
 'DJANGO_MEDIA_ROOT': '/var/www/legal-consult/media',
 'DJANGO_PROTECTED_MEDIA_ROOT': '/home/numinga/legal_consult/legal_consultant/protected_media',
 'DJANGO_CSRF_ORIGINS': 'https://www.k-urist.ru,https://k-urist.ru,https://176.53.224.200',
 'DJANGO_HTTPS': '1',
 'YANDEX_API_KEY': '',
}
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    for key, value in values.items():
        f.write(key + '=' + value + '\n')
PY
chown numinga:numinga "$runtime/app.env"
install -m 755 "$repo/deploy/deploy.sh" /usr/local/bin/legal-consult-deploy
install -m 755 "$repo/deploy/run-web.sh" /usr/local/bin/legal-consult-web
cat > /etc/supervisor/conf.d/legal_consult.conf <<'CONF'
[program:legal_consult]
command=/usr/local/bin/legal-consult-web
user=numinga
autostart=false
autorestart=true
stopasgroup=true
killasgroup=true
stdout_logfile=/var/log/supervisor/legal-consult.out.log
stderr_logfile=/var/log/supervisor/legal-consult.err.log
environment=PYTHONUNBUFFERED="1"
CONF
printf '%s\n' 'numinga ALL=(root) NOPASSWD: /usr/bin/supervisorctl reread, /usr/bin/supervisorctl update legal_consult, /usr/bin/supervisorctl restart legal_consult' > /etc/sudoers.d/legal-consult-deploy
chmod 440 /etc/sudoers.d/legal-consult-deploy
visudo -cf /etc/sudoers.d/legal-consult-deploy
systemctl enable --now supervisor nginx
runuser -u numinga -- /usr/local/bin/legal-consult-deploy
install -m 600 -o numinga -g numinga "$base/recover-catalog.py" "$state/recover-catalog.py"
runuser -u numinga -- bash -c 'set -a; source /home/numinga/.config/legal-consult/app.env; set +a; cd /home/numinga/.local/share/legal-consult-deploy/current/legal_consultant; /home/numinga/legal_consult/venv/bin/python manage.py shell < /home/numinga/.local/share/legal-consult-deploy/recover-catalog.py'
sed -i 's/autostart=false/autostart=true/' /etc/supervisor/conf.d/legal_consult.conf
supervisorctl reread
supervisorctl update legal_consult
cat > /etc/nginx/conf.d/legal-consult.conf <<'NGINX'
server {
    listen 80;
    server_name 176.53.224.200 k-urist.ru www.k-urist.ru;
    client_max_body_size 12m;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/legal-consult-acme;
        default_type text/plain;
    }
    location /static/ { alias /var/www/legal-consult/current/; }
    location /media/ { alias /var/www/legal-consult/media/; }
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX
nginx -t
systemctl reload nginx
install -m 644 "$repo/deploy/legal-consult-deploy.service" /etc/systemd/system/
install -m 644 "$repo/deploy/legal-consult-deploy.timer" /etc/systemd/system/
install -m 644 "$repo/deploy/legal-consult-cert-renew.service" /etc/systemd/system/
install -m 644 "$repo/deploy/legal-consult-cert-renew.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now legal-consult-cert-renew.timer
# Deployment timer enabled explicitly after the recovery readback is complete.
curl -fsS -H 'Host: www.k-urist.ru' http://127.0.0.1/healthz/
echo 'RECOVERY HTTP READY; HTTPS and DNS still require verification.'
