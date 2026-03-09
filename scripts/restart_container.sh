#!/bin/bash

SERVER_IP="16.50.102.112"
KEY_PATH="~/keys/agent-server-key.pem"
REMOTE_USER="ec2-user"
CONTAINER_NAME="agent-server-container"
IMAGE_NAME="agent-server-image"

# SSL certificate paths on server
CERT_FULLCHAIN_PATH="/etc/letsencrypt/live/agent.ajentify.com/fullchain.pem"
CERT_PRIVKEY_PATH="/etc/letsencrypt/live/agent.ajentify.com/privkey.pem"

echo "🔄 Restarting container to pick up new SSL certificates..."

ssh -i $KEY_PATH $REMOTE_USER@$SERVER_IP << EOF
  set -e

  echo "Stopping container..."
  docker stop $CONTAINER_NAME || true
  docker rm $CONTAINER_NAME || true

  echo "Starting container with updated SSL certificates..."
  docker run -d \
    --network host \
    --name $CONTAINER_NAME \
    --env-file .env \
    -e PYTHONUNBUFFERED=1 \
    -v $CERT_FULLCHAIN_PATH:/etc/ssl/certs/fullchain.pem:ro \
    -v $CERT_PRIVKEY_PATH:/etc/ssl/private/privkey.pem:ro \
    $IMAGE_NAME

  echo "✅ Container restarted successfully!"
  
  echo ""
  echo "Verifying certificate dates..."
  docker exec $CONTAINER_NAME cat /etc/ssl/certs/fullchain.pem | openssl x509 -noout -dates
EOF

echo "🚀 Done! Your server should now be using the new SSL certificates."


