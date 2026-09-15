# Production: 51.250.99.226

The server checks public `numinga27/legal_consult:main` every two minutes with
`legal-consult-deploy.timer`. No GitHub secret or inbound webhook is required.
Push is the trigger for the next server check, not evidence of completion.
`/healthz/` reports the SHA actually running after a successful deployment.

Deployment runs as `numinga`: fetch → separate release → schema check → tests
in an in-memory database → verified SQLite backup → migrations → static assets
→ switch release → Supervisor restart → health/readback. Concurrent deployments
are locked. Failed SHAs are not continuously retried; use a new commit or the
explicit `--retry` option after fixing the cause. A failed post-switch health
check restores the prior code release. The database is never automatically
restored over potentially newer user data; incompatible migrations need an
operator-led recovery using the pre-migration backup.

Paths verified on the existing server:

- Original checkout and Python environment: `/home/numinga/legal_consult`.
- Live database: `/home/numinga/legal_consult/legal_consultant/db.sqlite3`.
- Existing uploads remain at the original `legal_consultant/media` path.
- Releases, lock, status and private backups:
  `/home/numinga/.local/share/legal-consult-deploy`.
- Private runtime configuration: `/home/numinga/.config/legal-consult/app.env`.
- Only collected public static assets: `/var/www/legal-consult/releases/<SHA>`;
  Nginx uses `/var/www/legal-consult/current`.
- Supervisor program: `legal_consult`; existing Gunicorn listener `127.0.0.1:8001`.
- Entrypoints: `/usr/local/bin/legal-consult-deploy` and
  `/usr/local/bin/legal-consult-web` (installed from the two scripts here).

Operational commands:

```sh
sudo systemctl status legal-consult-deploy.timer
sudo journalctl -u legal-consult-deploy.service --since today
sudo systemctl start legal-consult-deploy.service
curl -fsS http://127.0.0.1:8001/healthz/
```

The initial server had an applied but uncommitted `0010_userdocumentdata`
migration. It is now tracked with the same name/schema and joined to
`0010_helporder` by migration `0011`, so existing data is preserved.
The old checkout (including staged changes and untracked scripts) is retained.
Do not use `git reset --hard`, replace the live database, or run the RAM preview
on production. The published court-order questionnaire is imported separately
once; deployment never re-seeds or overwrites owner-managed questionnaires.

Dependencies use the existing server virtualenv and are not silently upgraded.
If a new feature needs another dependency, install and verify it explicitly.
Release/backup cleanup is also an explicit maintenance operation. HTTPS is not
configured by these scripts; the existing HTTP address remains in use.

## Verified rollout — 2026-09-15

The initial rollout of `b0cb774` passed all 37 core tests on the server,
verified the SQLite backup, applied migrations and returned the matching
release from the public health endpoint. Nginx now serves the collected CSS
successfully. The timer is enabled and its scheduled service runs exit cleanly.

Public entry points:

- Site: http://51.250.99.226/
- Imported court-order questionnaire: http://51.250.99.226/questionnaire/17/
- Owner import (staff login required): http://51.250.99.226/admin-import/
- Deployment readback: http://51.250.99.226/healthz/

Production questionnaire IDs differ from the local RAM preview: court order
is **17** on this server; existing questionnaire **10** is child support.
The seven existing questionnaires and existing users/payments were preserved.
Installing changes to the deployment scripts or systemd units themselves
requires updating their installed copies; normal application commits are
picked up automatically from `main`.
