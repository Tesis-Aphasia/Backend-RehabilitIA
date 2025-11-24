# Docker Deployment Guide

This guide explains how to build and run the RehabilitIA Backend using Docker.

## Prerequisites

- Docker installed on your system
- Docker Compose (optional, but recommended)
- `env.env` file with required environment variables
- `serviceAccountKey.json` for Firebase authentication

## Quick Start with Docker Compose

The easiest way to run the application:

```bash
# Build and start the container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

The API will be available at `http://localhost:8000`

## Manual Docker Commands

### Build the Docker Image

```bash
docker build -t rehabilitia-backend .
```

### Run the Container

```bash
docker run -d \
  --name rehabilitia-backend \
  -p 8000:8000 \
  --env-file env.env \
  -v $(pwd)/serviceAccountKey.json:/app/serviceAccountKey.json:ro \
  rehabilitia-backend
```

### View Logs

```bash
docker logs -f rehabilitia-backend
```

### Stop the Container

```bash
docker stop rehabilitia-backend
docker rm rehabilitia-backend
```

## Environment Variables

Make sure your `env.env` file contains all necessary environment variables:

```env
# Example structure (adjust based on your actual needs)
OPENAI_API_KEY=your_api_key_here
# Add other environment variables as needed
```

## Health Check

The container includes a health check that runs every 30 seconds. You can check the health status:

```bash
docker ps
```

Look for the "STATUS" column which will show "(healthy)" when the service is running properly.

## Troubleshooting

### Container won't start

1. Check logs: `docker logs rehabilitia-backend`
2. Verify `env.env` file exists and contains required variables
3. Ensure `serviceAccountKey.json` exists in the project root

### Port already in use

If port 8000 is already in use, modify the port mapping:

```bash
# Use port 8080 instead
docker run -d -p 8080:8000 ...
```

Or update `docker-compose.yml`:

```yaml
ports:
  - "8080:8000"
```

### Permission issues with serviceAccountKey.json

Ensure the file has proper read permissions:

```bash
chmod 644 serviceAccountKey.json
```

## Production Deployment

For production deployment, consider:

1. **Use environment-specific configurations**: Create separate `env.production` files
2. **Enable HTTPS**: Use a reverse proxy like Nginx or Traefik
3. **Resource limits**: Add resource constraints in docker-compose.yml:

```yaml
deploy:
  resources:
    limits:
      cpus: '1'
      memory: 1G
    reservations:
      cpus: '0.5'
      memory: 512M
```

4. **Logging**: Configure proper logging drivers
5. **Monitoring**: Integrate with monitoring solutions (Prometheus, Grafana, etc.)

## API Endpoints

Once running, the following endpoints are available:

- `GET /` - Health check endpoint
- `POST /context/generate` - Generate VNEST exercise
- `POST /spaced-retrieval/` - Generate SR cards
- `POST /personalize-exercise/` - Personalize exercise
- `POST /profile/structure/` - Structure profile

Access the interactive API documentation at `http://localhost:8000/docs`
