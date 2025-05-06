#!/bin/bash


# Docker run
docker run -p 8082:8082  \
  -p 40000-40100:40000-40100/udp \
  --name agent-server-container \
  --network signaling-network \
  -it \
  --env-file .env \
  -e PYTHONUNBUFFERED=1 \
  -v $(pwd)/src:/app \
  agent-server-image