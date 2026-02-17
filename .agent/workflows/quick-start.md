---
description: Quick start guide for Naga-7
---

# Quick Start Guide

This guide shows you how to start and stop all Naga-7 services.

## Starting Naga-7

### Option 1: One-Command Startup (Recommended)

**On macOS/Linux:**

```bash
./start.sh
```

**On Windows:**

```cmd
start.bat
```

### Option 2: One-Command Startup (Skip Dependency Installation)

If dependencies are already installed and you just want to restart services:

**On macOS/Linux:**

```bash
./start.sh --skip-deps
```

**On Windows:**

```cmd
start.bat --skip-deps
```

### What Gets Started

The startup script will:

1. ✅ Check prerequisites (Python, Node.js, Docker)
2. ✅ Start infrastructure services (NATS, PostgreSQL, Redis)
3. ✅ Install Python dependencies (unless --skip-deps)
4. ✅ Install dashboard dependencies (unless --skip-deps)
5. ✅ Start N7-Core with all 10 microservices
6. ✅ Start N7-Sentinels agent
7. ✅ Start N7-Strikers agent
8. ✅ Start N7-Dashboard

### Expected Startup Time

- First run (with dependencies): ~2-3 minutes
- Subsequent runs (--skip-deps): ~10-15 seconds

## Stopping Naga-7

### Stop All Services

**On macOS/Linux:**

```bash
# If using start.sh (press Ctrl+C in the terminal)
# OR use the stop script:
./stop.sh
```

**On Windows:**

```cmd
stop.bat
```

### Keep Infrastructure Running

To stop only application services but keep infrastructure (NATS, PostgreSQL, Redis) running:

**On macOS/Linux:**

```bash
./stop.sh --keep-infra
```

**On Windows:**

```cmd
stop.bat --keep-infra
```

## Access Points

Once all services are running, access them at:

| Service          | URL                        | Description                   |
|------------------|----------------------------|-------------------------------|
| **Dashboard**    | http://localhost:5173      | Web UI for management         |
| **API Gateway**  | http://localhost:8000      | REST API endpoint             |
| **API Docs**     | http://localhost:8000/docs | Interactive API documentation |
| **NATS Monitor** | http://localhost:8222      | NATS message broker status    |

## Monitoring

### View Logs

All service logs are written to the `logs/` directory:

```bash
# View all logs
ls -la logs/

# Monitor all services in real-time
tail -f logs/*.log

# Monitor specific service
tail -f logs/n7-core.log
tail -f logs/n7-sentinels.log
tail -f logs/n7-strikers.log
tail -f logs/n7-dashboard.log
```

### Check Service Health

```bash
# Check infrastructure services
docker-compose ps

# Check API Gateway
curl http://localhost:8000/health

# Check NATS
curl http://localhost:8222/varz
```

## Common Issues

### Port Already in Use

If you get port conflict errors:

```bash
# Check what's using the ports
lsof -i :4222  # NATS
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis
lsof -i :8000  # API Gateway
lsof -i :5173  # Dashboard

# Kill the process or change ports in docker-compose.yml
```

### Services Won't Start

1. Ensure Docker is running
2. Check logs in `logs/` directory
3. Try stopping and starting again:
   ```bash
   ./stop.sh
   ./start.sh
   ```

### Infrastructure Services Failed

```bash
# Check Docker logs
cd deploy
docker-compose logs -f

# Restart infrastructure
docker-compose down
docker-compose up -d
```

## Development Workflow

### Quick Restart After Code Changes

```bash
# Stop services
./stop.sh --keep-infra

# Make your code changes

# Restart (skip dependency installation)
./start.sh --skip-deps
```

### Full Clean Restart

```bash
# Stop everything including infrastructure
./stop.sh

# Remove all data volumes (WARNING: deletes all data)
cd deploy
docker-compose down -v

# Start fresh
cd ..
./start.sh
```

## Next Steps

- Read the [User Manual](../docs/USER_MANUAL.md) for detailed usage
- Explore the [API Documentation](http://localhost:8000/docs)
- Check out the [Technical Design](../docs/TDD.md)
