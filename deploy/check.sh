#!/usr/bin/env bash
# Проверка развёрнутого стенда: HTTPS, редирект, API, ФСП ID, Mailpit за паролем.
#   deploy/check.sh scout.example.ru
#   deploy/check.sh scout.localhost --local   # локальная проверка оверлея с сертификатом Caddy
set -uo pipefail

domain="${1:?Укажите домен: deploy/check.sh scout.example.ru}"
curl_args=(--silent --show-error --max-time 10)
if [[ "${2:-}" == "--local" ]]; then
  curl_args+=(--insecure)
  for host in "$domain" "fsp.$domain" "mail.$domain"; do
    curl_args+=(--resolve "$host:443:127.0.0.1" --resolve "$host:80:127.0.0.1")
  done
fi

failures=0
check() {
  local title="$1" expected="$2" actual="$3"
  if [[ "$actual" == *"$expected"* ]]; then
    printf '  ✓ %s\n' "$title"
  else
    printf '  ✗ %s: ожидали «%s», получили «%s»\n' "$title" "$expected" "$actual"
    failures=$((failures + 1))
  fi
}

echo "Проверяю https://$domain"
check "API отвечает, база доступна" '"database":"ok"' \
  "$(curl "${curl_args[@]}" "https://$domain/api/v1/health")"
check "HTTP перенаправляется на HTTPS" "308" \
  "$(curl "${curl_args[@]}" -o /dev/null -w '%{http_code}' "http://$domain/")"
check "HSTS включён" "max-age=31536000" \
  "$(curl "${curl_args[@]}" -I "https://$domain/")"
check "Маршруты SPA отдаются" "200" \
  "$(curl "${curl_args[@]}" -o /dev/null -w '%{http_code}' "https://$domain/m/item-bank")"
check "ФСП ID публикует issuer на своём домене" "\"issuer\":\"https://fsp.$domain\"" \
  "$(curl "${curl_args[@]}" "https://fsp.$domain/.well-known/openid-configuration" | tr -d ' ')"
check "Mailpit закрыт паролем" "401" \
  "$(curl "${curl_args[@]}" -o /dev/null -w '%{http_code}' "https://mail.$domain/")"

if ((failures)); then
  echo "Проблем: $failures"
  exit 1
fi
echo "Стенд готов."
