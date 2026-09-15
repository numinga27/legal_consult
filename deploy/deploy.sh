#!/bin/bash
# Run as numinga. Existing checkout/data are never reset, stashed or overwritten.
set -euo pipefail
umask 027
state=/home/numinga/.local/share/legal-consult-deploy
repo=/home/numinga/legal_consult
python=$repo/venv/bin/python
mkdir -p "$state/releases" "$state/backups"
chmod 700 "$state" "$state/backups"
exec 9>"$state/deploy.lock"
flock -n 9 || exit 0
git -C "$repo" fetch --quiet origin main
sha=$(git -C "$repo" rev-parse origin/main)
[[ $sha =~ ^[0-9a-f]{40}$ ]] || exit 1
[[ ! -f "$state/success" || $(cat "$state/success") != "$sha" ]] || exit 0
# A failed revision needs a new commit or explicit operator retry, not endless retries.
[[ ! -f "$state/failed" || $(cat "$state/failed") != "$sha" || ${1:-} == --retry ]] || exit 0
release=$state/releases/$sha
previous=''
previous_static=''
[[ ! -L "$state/current" ]] || previous=$(readlink -f "$state/current")
[[ ! -L /var/www/legal-consult/current ]] || previous_static=$(readlink -f /var/www/legal-consult/current)
switched=0
failed() {
    printf '%s\n' "$sha" > "$state/failed"
    if [[ $switched == 1 && -n $previous ]]; then
        ln -sfn "$previous" "$state/current.next"
        mv -Tf "$state/current.next" "$state/current"
        if [[ -n $previous_static ]]; then
            ln -sfn "$previous_static" /var/www/legal-consult/current.next
            mv -Tf /var/www/legal-consult/current.next /var/www/legal-consult/current
        fi
        sudo -n supervisorctl restart legal_consult || true
    elif [[ $switched == 1 && -f "$state/bootstrap-supervisor.conf" ]]; then
        sudo -n cp "$state/bootstrap-supervisor.conf" /etc/supervisor/conf.d/legal_consult.conf
        sudo -n supervisorctl reread || true
        sudo -n supervisorctl update legal_consult || true
    fi
    echo "FAILED $sha; see system journal. Database is not automatically restored."
}
trap failed ERR
echo "DEPLOY $sha"
mkdir -p "$release"
git -C "$repo" archive "$sha" | tar -x -C "$release"
set -a
source /home/numinga/.config/legal-consult/app.env
set +a
export APP_RELEASE=$sha
export DJANGO_STATIC_ROOT=/var/www/legal-consult/releases/$sha
cd "$release/legal_consultant"
"$python" manage.py check
"$python" manage.py makemigrations --check --dry-run
"$python" manage.py test core --noinput --verbosity 1
"$python" - "$state/backups/$sha.sqlite3" <<'PY'
import os,sqlite3,sys
from pathlib import Path
target=Path(sys.argv[1])
if not target.exists():
    source=sqlite3.connect(Path(os.environ['DJANGO_DB_PATH']).as_uri()+'?mode=ro',uri=True)
    with sqlite3.connect(target) as backup:
        source.backup(backup)
        assert backup.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    source.close()
    target.chmod(0o600)
print('DATABASE BACKUP VERIFIED')
PY
"$python" manage.py migrate --noinput
mkdir -p "$DJANGO_STATIC_ROOT"
"$python" manage.py collectstatic --noinput --verbosity 0
# Only collected public assets are exposed to Nginx.
find "$DJANGO_STATIC_ROOT" -type d -exec chmod 755 {} +
find "$DJANGO_STATIC_ROOT" -type f -exec chmod 644 {} +
ln -sfn "$DJANGO_STATIC_ROOT" /var/www/legal-consult/current.next
mv -Tf /var/www/legal-consult/current.next /var/www/legal-consult/current
ln -sfn "$release" "$state/current.next"
mv -Tf "$state/current.next" "$state/current"
switched=1
sudo -n supervisorctl reread
sudo -n supervisorctl update legal_consult
sudo -n supervisorctl restart legal_consult
"$python" - "$sha" <<'PY'
import json,sys,time,urllib.request
for attempt in range(10):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8001/healthz/',timeout=3) as r: data=json.load(r)
        assert data=={'ok':True,'release':sys.argv[1]},data
        break
    except Exception:
        if attempt==9: raise
        time.sleep(1)
print('HEALTH VERIFIED',sys.argv[1])
PY
printf '%s\n' "$sha" > "$state/success"
echo "DEPLOYED $sha"
