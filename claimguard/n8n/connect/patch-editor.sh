#!/bin/sh
# Puts the ClaimGuard architecture view on the n8n workflows page, then starts n8n.
set -e
UI=$(find /usr/local/lib/node_modules/n8n -path '*/n8n-editor-ui/dist/index.html' | head -1)
if [ -n "$UI" ] && [ -f /claimguard/claimguard-connect.js ]; then
  STATIC=$(dirname "$UI")/static
  cp /claimguard/claimguard-connect.js "$STATIC/claimguard-connect.js"
  chmod 644 "$STATIC/claimguard-connect.js"
  if grep -q 'claimguard-connect.js' "$UI"; then
    sed -i 's#claimguard-connect\.js[^"]*#claimguard-connect.js?v=9#' "$UI"
  else
    sed -i 's#</body>#<script src="/{{BASE_PATH}}/static/claimguard-connect.js?v=9" nonce="{{CSP_NONCE}}"></script></body>#' "$UI"
  fi
fi
if [ "$(id -u)" = "0" ]; then
  exec su -s /bin/sh node -c 'exec tini -- /docker-entrypoint.sh'
fi
exec tini -- /docker-entrypoint.sh
