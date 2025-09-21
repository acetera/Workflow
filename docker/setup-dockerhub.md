# Docker Hub Setup Instructions

## Step 1: Create Docker Hub Account
1. Go to https://hub.docker.com
2. Sign up for a free account
3. Note your username (you'll need this)

## Step 2: Login Locally
```bash
docker login
# Enter your Docker Hub username and password
```

## Step 3: Update Configuration
Edit `docker/build.sh` and change this line:
```bash
DOCKERHUB_USERNAME="YOUR_DOCKERHUB_USERNAME"  # <-- Change to your actual username
```

For example, if your Docker Hub username is `johnsmith`, change it to:
```bash
DOCKERHUB_USERNAME="johnsmith"
```

## Step 4: Build and Push
```bash
# Make script executable
chmod +x docker/build.sh

# Build and push images
./docker/build.sh
```

## Step 5: Your Images Will Be Available At:
- **Orchestrator**: `yourusername/puzzle-solver-orchestrator:v1.0`
- **Worker**: `yourusername/puzzle-solver-worker:v1.0`

## Step 6: Test Locally
```bash
# Start the full system
docker-compose -f docker/docker-compose.yml up
```

## Step 7: Deploy to vast.ai
Use your worker image: `yourusername/puzzle-solver-worker:v1.0`

## What the Build Process Does:
1. ✅ **Builds orchestrator** with FastAPI and DP database
2. ✅ **Builds worker** with RCKangaroo compiled from source
3. ✅ **Tests both images** locally
4. ✅ **Pushes to Docker Hub** (if you confirm)
5. ✅ **Updates docker-compose.yml** with your image names

## Security Notes:
- RCKangaroo is built from source (most secure)
- No binary files stored in your repo
- Images are publicly available on Docker Hub
- Each build is reproducible and auditable

## Pricing:
- Docker Hub is **free** for public repositories
- No limits on pulls (perfect for vast.ai scaling)
- Images will be ~2GB each (includes CUDA runtime)

## After Setup:
Your worker containers will:
1. **Auto-download** when deployed to vast.ai
2. **Self-register** with your orchestrator
3. **Start mining** immediately
4. **Submit DPs** automatically
5. **Handle collisions** and report results

Ready to revolutionize Bitcoin puzzle solving! 🚀