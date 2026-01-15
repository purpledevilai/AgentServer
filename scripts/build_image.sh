#!/bin/bash

# Docker build for x86_64 (Amazon Linux EC2 target)
# This uses QEMU emulation on ARM Macs but gets prebuilt wheels
docker build --platform linux/amd64 -t agent-server-image .