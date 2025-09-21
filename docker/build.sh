#!/bin/bash
# Build and push to Docker Hub

set -e

# Configuration - CHANGE YOUR_DOCKERHUB_USERNAME
DOCKERHUB_USERNAME="warmlyale"  # <-- Change this to your Docker Hub username
PROJECT_NAME="puzzle-solver"
VERSION="v1.0"

# Derived names
ORCHESTRATOR_IMAGE="${DOCKERHUB_USERNAME}/${PROJECT_NAME}-orchestrator:${VERSION}"
WORKER_IMAGE="${DOCKERHUB_USERNAME}/${PROJECT_NAME}-worker:${VERSION}"

echo "Building Docker images for Docker Hub..."
echo "Orchestrator: ${ORCHESTRATOR_IMAGE}"
echo "Worker: ${WORKER_IMAGE}"

# Build orchestrator
echo "Building orchestrator..."
docker build \
    -t "${ORCHESTRATOR_IMAGE}" \
    -f docker/Dockerfile.orchestrator \
    .

# Build worker
echo "Building worker with RCKangaroo..."
docker build \
    -t "${WORKER_IMAGE}" \
    -f docker/Dockerfile.worker \
    .

# Test images locally
echo "Testing orchestrator image..."
docker run --rm --name test-orchestrator -p 8000:8000 -d "${ORCHESTRATOR_IMAGE}"
sleep 5
if curl -f http://localhost:8000/; then
    echo "✅ Orchestrator test passed"
else
    echo "❌ Orchestrator test failed"
fi
docker stop test-orchestrator

echo "Testing worker image (GPU check)..."
if docker run --rm "${WORKER_IMAGE}" python3 -c "
import subprocess
try:
    result = subprocess.run(['/usr/local/bin/RCKangaroo', '-h'], capture_output=True, timeout=5)
    print('✅ RCKangaroo binary working')
    exit(0)
except:
    print('❌ RCKangaroo binary test failed')
    exit(1)
"; then
    echo "✅ Worker image test passed"
else
    echo "❌ Worker image test failed"
fi

# Ask before pushing
read -p "Push images to Docker Hub? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Pushing orchestrator..."
    docker push "${ORCHESTRATOR_IMAGE}"

    echo "Pushing worker..."
    docker push "${WORKER_IMAGE}"

    echo "✅ Images pushed to Docker Hub!"
    echo ""
    echo "Your images are now available:"
    echo "  Orchestrator: ${ORCHESTRATOR_IMAGE}"
    echo "  Worker: ${WORKER_IMAGE}"
    echo ""
    echo "To deploy on vast.ai, use: ${WORKER_IMAGE}"
else
    echo "Images built but not pushed."
fi

# Update docker-compose with correct image names
echo "Updating docker-compose.yml with your images..."
sed -i.bak "s|your-registry.com/puzzle-solver-orchestrator:latest|${ORCHESTRATOR_IMAGE}|g" docker/docker-compose.yml
sed -i.bak "s|your-registry.com/puzzle-solver-worker:latest|${WORKER_IMAGE}|g" docker/docker-compose.yml

echo "Updated docker-compose.yml with your Docker Hub images"