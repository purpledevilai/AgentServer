#!/bin/bash

SERVER_IP="16.26.56.194"
KEY_PATH="~/keys/agent-server-key.pem"
REMOTE_USER="ec2-user"
DOMAIN="agent.ajentify.com"

echo "🔍 Checking SSL certificate status..."
echo ""

ssh -i $KEY_PATH $REMOTE_USER@$SERVER_IP << EOF
  set -e

  echo "=== Host Certificate Info (what certbot renewed) ==="
  sudo openssl x509 -in /etc/letsencrypt/live/$DOMAIN/fullchain.pem -noout -dates
  echo ""

  echo "=== Container Certificate Info (what the app is using) ==="
  docker exec agent-server-container cat /etc/ssl/certs/fullchain.pem | openssl x509 -noout -dates
  echo ""

  echo "=== Checking if certificates match ==="
  HOST_HASH=\$(sudo openssl x509 -in /etc/letsencrypt/live/$DOMAIN/fullchain.pem -noout -hash)
  CONTAINER_HASH=\$(docker exec agent-server-container cat /etc/ssl/certs/fullchain.pem | openssl x509 -noout -hash)
  
  if [ "\$HOST_HASH" = "\$CONTAINER_HASH" ]; then
    echo "✅ Certificates match"
  else
    echo "❌ Certificates DON'T match - Container needs restart!"
  fi
EOF


