#!/bin/bash
# Build and push worker container with RCKangaroo binary

set -e

# Configuration
REGISTRY="your-registry.com"  # Replace with your container registry
IMAGE_NAME="puzzle-solver-worker"
VERSION="latest"

echo "Building RCKangaroo worker container..."

# Build container with binary
docker build \
    -t "${REGISTRY}/${IMAGE_NAME}:${VERSION}" \
    -f docker/Dockerfile.worker \
    .

# Test the container locally
echo "Testing container..."
docker run --rm --gpus all \
    "${REGISTRY}/${IMAGE_NAME}:${VERSION}" \
    --test-gpu

# Push to registry
echo "Pushing to registry..."
docker push "${REGISTRY}/${IMAGE_NAME}:${VERSION}"

echo "Container available at: ${REGISTRY}/${IMAGE_NAME}:${VERSION}"

# Generate deployment manifest
cat > docker/worker-deployment.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: puzzle-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: puzzle-worker
  template:
    metadata:
      labels:
        app: puzzle-worker
    spec:
      containers:
      - name: worker
        image: ${REGISTRY}/${IMAGE_NAME}:${VERSION}
        env:
        - name: ORCHESTRATOR_URL
          value: "https://your-orchestrator.com"
        - name: WORKER_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        resources:
          limits:
            nvidia.com/gpu: 1
          requests:
            nvidia.com/gpu: 1
EOF

echo "Deployment manifest created: docker/worker-deployment.yaml"