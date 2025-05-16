#!/bin/bash

# === Configuration ===
SERVER_IP="16.26.56.194"
KEY_PATH="~/keys/agent-server-key.pem"
REMOTE_USER="ec2-user"
CONTAINER_NAME="agent-server-container"

# === SSH into Server and Tail Docker Logs ===
ssh -i $KEY_PATH $REMOTE_USER@$SERVER_IP "
  echo '🔍 Attaching to container logs...';
  docker logs -f $CONTAINER_NAME
"