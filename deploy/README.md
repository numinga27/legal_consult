# Current recovery host: 176.53.224.200 (2026-10-15)

The owner reported the old server lost and authorized restoration on the new
host. SSH uses `root@176.53.224.200` and the existing deployment key; the app
runs as `numinga`, not root. The historical notes below describe the lost host.

Current verified entry point: **https://www.k-urist.ru/**. Both domain A records
point to `176.53.224.200`; HTTP and the bare HTTPS domain redirect to this URL.
The trusted domain certificate covers both names and expires 2027-01-13.
External HTTPS pages, static assets, questionnaire 10, and real staff login with
CSRF and logout were verified on 2026-10-15. Certificate renewal dry-run passed;
`legal-consult-cert-renew.timer` renews certificates and reloads Nginx.
The trusted **https://176.53.224.200/** entry point also remains available.

`activate-recovery-domain.sh` checks DNS, issues/reuses the domain certificate,
validates/reloads Nginx, and checks HTTPS with bounded retries because worker
reload is asynchronous. The installed domain configuration is
`/etc/nginx/conf.d/legal-consult-domain-https.conf`. No DNS change is pending.

## Recovered data and remaining gaps

## Owner catalogue update (2026-10-15)

The owner dashboard now uses server-side search, section/type/status filters,
and ten questionnaires per page. Every row offers metadata editing, preview,
documents, publication/hiding, archiving/restoration, and confirmed deletion.
New manual questionnaires start as private drafts. Imported content retains
its established new-version workflow; metadata edits keep the same record.
Manual questions, answers, and results have scoped editing forms.

Archive hides the questionnaire from the default owner list and public routes;
restoration returns a draft. Deletion requires the exact title and is blocked
when orders or legacy payment records reference the questionnaire.
Migration 0014 adds the archive flag and anonymous attempt records. Statistics
show starts, completions, completion ratio, and saved order count. Reloads and
staff previews do not create additional attempts; an explicit restart does.
Historical starts/completions are not inferred. Account email (login fallback)
is visible in the shared header and home page.

## Recovery data limitations

- The source is the local SQLite catalogue dated 2026-09-10, not the latest
  production DB. `create-catalog-seed.py` made a fresh file with only the legal
  catalogue and five embedded HTML templates. All authentication, payment,
  session, generated-document and other tables were verified empty before
  transfer. The full historical database was not transferred.
- Six historical questionnaires were recovered. The saved, reviewed
  `core/import_examples/court_order.json` was imported as questionnaire **10**:
  24 contextual nodes, 48 transitions, 18 conclusions. Its graph validates.
- Total: **7 questionnaires**, of which 5 active. The seed experiments
  `Тестовый опросник` (6) and `kfjdesc (AI)` (5) remain as inactive drafts.
- Historical questionnaires 7 (alimony), 8 (privatization), and 9 (goods return)
  contain an unavailable answer target at questions 17, 19, and 21 respectively.
  Existing safe handling remains; missing legal text was not invented.
- No uploaded DOCX/PDF pairs were found or restored. The five embedded HTML
  templates are not uploaded paid DOCX/PDF materials.
- Old production users/orders and post-snapshot edits were not recovered.
  Payment provider/webhook integration was already absent from the saved app;
  it is not represented as working. Yandex AI credentials are unset.

## Recovery operations

`bootstrap-recovery.sh` is a one-time script for an empty host. It refuses to
overwrite an existing runtime. Do not rerun it on a working installation.
Its seed must be produced by `create-catalog-seed.py`; it rechecks that all
non-catalogue tables are empty. Prerequisites and required files are in its
header. Dependencies are pinned in `requirements-recovery.txt` (52 tests PASS).

The private runtime directory remains `/home/numinga/.config/legal-consult`.
It is the designated secret store, mode 700; `app.env` and `recovery-admin.txt`
are mode 600. The new staff login is `recovery-owner`; its password is generated
on the server and stored only in `recovery-admin.txt`. Never print it in logs,
commit it, or include it in recovery reports. Owner access was tested through
the HTTPS login form, including CSRF, then logged out.

`verify-recovery.py` checks public HTTPS, static assets, staff login/import pages,
and catalogue completeness without logging credentials. Run with production
settings through `manage.py shell`. Paths are pinned to this recovery host.

Verified server backups are in
`/home/numinga/.local/share/legal-consult-deploy/backups` (private): the sanitized
seed and the migrated recovery DB. These are on-server copies, not offsite
backups. The original local DB remains unchanged.

## Historical deployment architecture (old host 51.250.99.226)

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
- Paid DOCX/PDF files remain in the private `legal_consultant/protected_media`
  path and are served only through the authenticated Django download view.
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
Release/backup cleanup is also an explicit maintenance operation. HTTPS is
configured separately on this server, as documented below.

## HTTPS and customer accounts — 2026-09-16

Public address: https://51.250.99.226/ (HTTP redirects with 308).
The owner explicitly approved Let's Encrypt terms and certificate issuance.
Certbot 5.8.0 is installed in `/opt/legal-consult-certbot`, independently of
the application virtualenv. The `legal-consult-ip` IP certificate uses the
short-lived profile. Its first expiry is 2026-09-23; renewal is essential.

Nginx uses `/etc/letsencrypt/live/legal-consult-ip/fullchain.pem` and
`privkey.pem`; keep the private key on the server, outside Git. HTTP ACME
requests under `/.well-known/acme-challenge/` are served from
`/var/www/legal-consult-acme`. Other HTTP paths redirect to HTTPS. The TLS
proxy overwrites `X-Forwarded-Proto`; Gunicorn remains on loopback only.
Private runtime configuration sets `DJANGO_HTTPS=1` and includes the HTTPS
origin in `DJANGO_CSRF_ORIGINS`. This enables Secure session/CSRF cookies.
Public registration fails closed without HTTPS and Secure session cookies.

`legal-consult-cert-renew.timer` checks twice daily, with up to 30 minutes
randomization and persistent catch-up. A successful renewal validates and
reloads Nginx. Installed units are mirrored here; normal Git deployment does
not install systemd/Nginx changes automatically. The existing Nginx backup
is private at `~numinga/.local/share/legal-consult-deploy/before-https-nginx.conf`.

```sh
sudo systemctl status legal-consult-cert-renew.timer
sudo /opt/legal-consult-certbot/bin/certbot renew --dry-run --cert-name legal-consult-ip
```

Initial issuance, trusted HTTPS connection, and simulated renewal were
verified. See `CUSTOMER_ACCOUNTS.md` for account ownership and payment gates.

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

## Domain cutover preparation — 2026-09-28

The pre-cutover Nginx configuration is mirrored in
`deploy/legal-consult-domain-http.nginx`. It keeps the IP certificate and IP
entry point working while accepting ACME challenges for `k-urist.ru` and
`www.k-urist.ru`. Install the domain certificate only after both A records
resolve to `51.250.99.226`, then add the domain TLS virtual host and verify it
before treating `https://www.k-urist.ru/` as canonical.

