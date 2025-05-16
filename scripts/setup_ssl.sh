#!/bin/bash

SERVER_IP="16.26.56.194"
KEY_PATH="~/keys/agent-server-key.pem"
REMOTE_USER="ec2-user"
DOMAIN="agent.ajentify.com"
EMAIL="purpledevilai@gmail.com"

ssh -i $KEY_PATH $REMOTE_USER@$SERVER_IP << EOF
  set -e

  echo "Installing certbot..."
  sudo yum install -y certbot

  echo "Requesting certificate for $DOMAIN..."
  sudo certbot certonly --standalone \
    --non-interactive \
    --agree-tos \
    --email $EMAIL \
    -d $DOMAIN

  echo "Adjusting certificate file permissions (live folder only)..."
  sudo chmod 644 /etc/letsencrypt/live/$DOMAIN/fullchain.pem
  sudo chmod 644 /etc/letsencrypt/live/$DOMAIN/privkey.pem

  echo "Adjusting directory permissions for traversal..."
  sudo chmod 755 /etc/letsencrypt
  sudo chmod 755 /etc/letsencrypt/live
  sudo chmod 755 /etc/letsencrypt/archive

  echo "✅ SSL Certificate setup complete and permissions adjusted for $DOMAIN!"
EOF
