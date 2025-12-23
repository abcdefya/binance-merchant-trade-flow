#!/bin/bash

LOG_FILE="/var/log/install_docker_jenkins.log"
exec > >(tee -a ${LOG_FILE}) 2>&1

echo "--- Starting Docker + Jenkins + gcloud installation ---"
date

# ----------------------------------------------------
# 1. Install Docker on HOST
# ----------------------------------------------------
echo "[1/6] Installing Docker..."
apt-get update
apt-get install -y docker.io
systemctl enable docker
systemctl start docker
echo "Docker installed."

# ----------------------------------------------------
# 2. Start Jenkins container
# ----------------------------------------------------
echo "[2/6] Starting Jenkins container..."

docker rm -f jenkins 2>/dev/null || true

docker run -d \
  --name jenkins \
  --restart unless-stopped \
  --privileged \
  --user root \
  -p 8081:8080 \
  -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  jenkins/jenkins:lts

echo "Jenkins container started."

# ----------------------------------------------------
# 3. Wait Jenkins container to be ready
# ----------------------------------------------------
echo "[3/6] Waiting for Jenkins container..."
sleep 15

# ----------------------------------------------------
# 4. Install gcloud INSIDE Jenkins container
# ----------------------------------------------------
echo "[4/6] Installing gcloud CLI inside Jenkins container..."

docker exec jenkins bash -c "
apt-get update &&
apt-get install -y ca-certificates curl gnupg apt-transport-https &&
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
 | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg &&
echo 'deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main' \
 > /etc/apt/sources.list.d/google-cloud-sdk.list &&
apt-get update &&
apt-get install -y google-cloud-cli kubectl docker.io
"

echo "gcloud installed inside Jenkins container."

# ----------------------------------------------------
# 5. Verify gcloud
# ----------------------------------------------------
echo "[5/6] Verifying gcloud installation..."

docker exec jenkins bash -c "gcloud version"

# ----------------------------------------------------
# 6. Done
# ----------------------------------------------------
echo "[6/6] Installation finished successfully."
date
