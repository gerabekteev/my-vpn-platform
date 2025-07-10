#!/bin/bash
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
docker run -d --name outline-server \
  -p 1025:1025 -p 5000:5000 \
  -e ACCESS_TOKEN=$1 \
  quay.io/outline/outline-server:latest