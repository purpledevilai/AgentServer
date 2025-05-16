#!/bin/bash

# === Configuration ===
SERVER_IP="16.26.56.194"
KEY_PATH="~/keys/agent-server-key.pem"
REMOTE_USER="ec2-user"

# Project-specific settings
IMAGE_NAME="agent-server-image"
CONTAINER_NAME="agent-server-container"
DOCKERFILE_NAME="Dockerfile.prod"

# Ports
HTTPS_PORT=443
ICE_PORT_START=40000
ICE_PORT_END=40100

# SSL certificate paths on server
CERT_FULLCHAIN_PATH="/etc/letsencrypt/live/agent.ajentify.com/fullchain.pem"
CERT_PRIVKEY_PATH="/etc/letsencrypt/live/agent.ajentify.com/privkey.pem"

# === Parse flags ===
SKIP_BUILD=false

for arg in "$@"; do
  case $arg in
    --skip-build)
      SKIP_BUILD=true
      shift
      ;;
    *)
      ;;
  esac
done

# === Build and Save ===
if [ "$SKIP_BUILD" = false ]; then
  echo "Building docker image from $DOCKERFILE_NAME..."
  docker build -f $DOCKERFILE_NAME -t $IMAGE_NAME .

  echo "Saving docker image to tar..."
  docker save $IMAGE_NAME > ${IMAGE_NAME}.tar

  echo "Copying files to server..."
  scp -i $KEY_PATH ${IMAGE_NAME}.tar $REMOTE_USER@$SERVER_IP:~/
fi

# Always copy .env (in case it changed)
scp -i $KEY_PATH .env $REMOTE_USER@$SERVER_IP:~/

# === SSH into Server and Deploy ===
echo "Deploying on server..."
ssh -i $KEY_PATH $REMOTE_USER@$SERVER_IP << EOF
  set -e  # Exit immediately if any command fails

  echo "Stopping old container (if exists)..."
  docker stop $CONTAINER_NAME || true
  docker rm $CONTAINER_NAME || true

  if [ "$SKIP_BUILD" = false ]; then
    echo "Removing old image (if exists)..."
    docker rmi $IMAGE_NAME || true
    
    echo "Loading new image..."
    docker load < ${IMAGE_NAME}.tar
    echo "Cleaning up tar file..."
    rm -f ${IMAGE_NAME}.tar
  fi

  echo "Checking for SSL certificates..."
  if [ ! -f "$CERT_FULLCHAIN_PATH" ] || [ ! -f "$CERT_PRIVKEY_PATH" ]; then
    echo "❌ SSL certificates not found! Expected at:"
    echo " - $CERT_FULLCHAIN_PATH"
    echo " - $CERT_PRIVKEY_PATH"
    exit 1
  fi
  echo "✅ SSL certificates found."

  echo "Running new container with SSL certs mounted..."
  docker run -d \
    --network host \
    --name $CONTAINER_NAME \
    --env-file .env \
    -e PYTHONUNBUFFERED=1 \
    -v $CERT_FULLCHAIN_PATH:/etc/ssl/certs/fullchain.pem:ro \
    -v $CERT_PRIVKEY_PATH:/etc/ssl/private/privkey.pem:ro \
    $IMAGE_NAME
EOF

# === Clean Up Local Tar (only if built) ===
if [ "$SKIP_BUILD" = false ]; then
  rm -f ${IMAGE_NAME}.tar
fi

echo "🚀 Deployment complete!"
