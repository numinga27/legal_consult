#!/usr/bin/env bash
set -Eeuo pipefail

domain="k-urist.ru"
www_domain="www.k-urist.ru"
expected_ip="51.250.99.226"
webroot="/var/www/legal-consult-acme"
certbot="/opt/legal-consult-certbot/bin/certbot"
tls_conf="/etc/nginx/conf.d/legal-consult-domain-https.conf"
http_conf="/etc/nginx/conf.d/legal-consult-domain-http.conf"

if [[ $(id -u) -ne 0 ]]; then
    echo "Run as root: sudo bash $0" >&2
    exit 1
fi

for name in "$domain" "$www_domain"; do
    if ! getent ahostsv4 "$name" | awk '{print $1}' | grep -Fxq "$expected_ip"; then
        echo "$name does not resolve to $expected_ip" >&2
        exit 1
    fi
done

test -x "$certbot"
install -d -m 755 "$webroot/.well-known/acme-challenge"

# Keep the ACME webroot reachable even if the pre-cutover HTTP block was not installed.
probe="legal-consult-$(date +%s)-$$"
printf '%s\n' "$probe" > "$webroot/.well-known/acme-challenge/$probe"
if [[ "$(curl -fsS --resolve "$domain:80:127.0.0.1" "http://$domain/.well-known/acme-challenge/$probe" || true)" != "$probe" ]]; then
    cat > "$http_conf.tmp" <<'NGINX'
server {
    listen 80;
    server_name k-urist.ru www.k-urist.ru;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/legal-consult-acme;
        default_type text/plain;
    }
    location / { return 308 https://www.k-urist.ru$request_uri; }
}
NGINX
    install -m 644 "$http_conf.tmp" "$http_conf"
    rm -f "$http_conf.tmp"
    nginx -t
    systemctl reload nginx
fi
rm -f "$webroot/.well-known/acme-challenge/$probe"

"$certbot" certonly \
    --non-interactive \
    --agree-tos \
    --webroot -w "$webroot" \
    --cert-name "$domain" \
    -d "$domain" -d "$www_domain"

if [[ -e "$tls_conf" ]]; then
    cp -a "$tls_conf" "$tls_conf.backup-$(date +%Y%m%d-%H%M%S)"
fi

cat > "$tls_conf.tmp" <<'NGINX'
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

    location /static/ {
        alias /var/www/legal-consult/current/;
    }

    location /media/ {
        alias /home/numinga/legal_consult/legal_consultant/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
NGINX

install -m 644 "$tls_conf.tmp" "$tls_conf"
rm -f "$tls_conf.tmp"
nginx -t
systemctl reload nginx

curl -fsSI --resolve "$www_domain:443:127.0.0.1" "https://$www_domain/" >/dev/null
curl -fsSI --resolve "$domain:443:127.0.0.1" "https://$domain/" | grep -Fiq "location: https://$www_domain/"
openssl x509 -in "/etc/letsencrypt/live/$domain/fullchain.pem" \
    -noout -subject -issuer -dates -ext subjectAltName
echo "DOMAIN HTTPS VERIFIED"
