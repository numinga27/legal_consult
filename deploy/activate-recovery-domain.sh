#!/usr/bin/env bash
# Use ONLY on the replacement server after BOTH DNS A records have changed.
set -Eeuo pipefail
[[ $(id -u) == 0 ]] || exit 1
expected_ip=176.53.224.200
for domain in k-urist.ru www.k-urist.ru; do
    resolved=$(getent ahostsv4 "$domain" | awk '{print $1}' | sort -u)
    [[ "$resolved" == "$expected_ip" ]] || { echo "DNS not ready: $domain = $resolved"; exit 1; }
done
certbot=/opt/legal-consult-certbot/bin/certbot
"$certbot" certonly --non-interactive --agree-tos --webroot \
    -w /var/www/legal-consult-acme --cert-name k-urist.ru \
    -d k-urist.ru -d www.k-urist.ru
target=/etc/nginx/conf.d/legal-consult-domain-https.conf
backup=$(mktemp /root/legal-consult-domain-before.XXXXXX)
existed=0
if [[ -f "$target" ]]; then cp -p "$target" "$backup"; existed=1; fi
rollback() {
    if [[ $existed == 1 ]]; then cp -p "$backup" "$target"; else rm -f "$target"; fi
    nginx -t && systemctl reload nginx
}
trap rollback ERR
cat > "$target" <<'NGINX'
server {
    listen 443 ssl;
    server_name k-urist.ru;
    ssl_certificate /etc/letsencrypt/live/k-urist.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/k-urist.ru/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    return 308 https://www.k-urist.ru$request_uri;
}
server {
    listen 443 ssl;
    server_name www.k-urist.ru;
    ssl_certificate /etc/letsencrypt/live/k-urist.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/k-urist.ru/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 12m;
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
chmod 644 "$target"
nginx -t
systemctl reload nginx
# Reload signals nginx asynchronously; allow workers to load the new certificate.
curl -fsS --retry 5 --retry-all-errors --retry-delay 1 --max-time 10 --resolve www.k-urist.ru:443:127.0.0.1 https://www.k-urist.ru/healthz/
curl -fsSI --retry 5 --retry-all-errors --retry-delay 1 --max-time 10 --resolve k-urist.ru:443:127.0.0.1 https://k-urist.ru/ | grep -Fi 'Location: https://www.k-urist.ru/'
trap - ERR
echo 'DOMAIN HTTPS VERIFIED'
