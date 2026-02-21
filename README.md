<p align="center">
  <img src="docs/Naga-7.jpg" alt="Naga-7 Logo" width="200"/>
</p>

# Naga-7 (N7)

Naga-7 is an open-source, multi-level AI agent system designed to continuously monitor enterprise infrastructure for security threats and actively mitigate them in real time.

## 🏗️ Architecture

The system comprises four core components:

- **N7-Core:** Central orchestrator managing agents, threat intelligence, and decision making (10 microservices)
- **N7-Sentinels:** Autonomous monitoring agents for detecting anomalies and threats
- **N7-Strikers:** Autonomous response agents for executing containment and remediation actions
- **N7-Dashboard:** Web-based management and visualization interface (React + TypeScript)

### Infrastructure Services

- **NATS:** Message broker for inter-service communication
- **PostgreSQL (TimescaleDB):** Time-series database for events and metrics
- **Redis:** Caching and rate limiting

## 📁 Directory Structure

```
naga-7/
├── n7-core/              # Core services (Python)
│   ├── n7_core/
│   │   ├── api_gateway/       # FastAPI gateway
│   │   ├── event_pipeline/    # Event ingestion & processing
│   │   ├── agent_manager/     # Agent lifecycle management
│   │   ├── threat_correlator/ # Threat correlation engine
│   │   ├── decision_engine/   # Decision-making logic
│   │   ├── audit_logger/      # Audit logging
│   │   ├── enrichment/        # Event enrichment
│   │   ├── threat_intel/      # Threat intelligence feeds
│   │   ├── playbooks/         # Playbook engine
│   │   └── notifier/          # Notification service
│   └── requirements.txt
├── n7-sentinels/         # Sentinel agents (Python)
│   ├── n7_sentinels/
│   │   ├── agent_runtime/     # Agent lifecycle
│   │   ├── event_emitter/     # Event emission
│   │   ├── detection_engine/  # Anomaly detection
│   │   └── probes/            # System probes
│   └── requirements.txt
├── n7-strikers/          # Striker agents (Python)
│   ├── n7_strikers/
│   │   ├── agent_runtime/     # Agent lifecycle
│   │   ├── action_executor/   # Action execution
│   │   ├── rollback_manager/  # Action rollback
│   │   └── evidence_collector/# Evidence collection
│   └── requirements.txt
├── n7-dashboard/         # Web dashboard (React + TypeScript)
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── schemas/              # Shared data schemas (Protobuf/JSON)
├── deploy/               # Deployment configurations
│   └── docker-compose.yml
├── docs/                 # Project documentation
│   ├── BRD.md
│   ├── SRS.md
│   ├── TDD.md
│   ├── TEST_PLAN.md
│   └── USER_MANUAL.md
└── start.sh              # Single command startup script
```

## 🚀 Quick Start

### Prerequisites

- **Python 3.9+** with pip
- **Node.js 18+** with npm
- **Docker** and **Docker Compose**
- **Git**

### One-Command Startup

For the fastest way to get started, use the startup script:

```bash
# Make the script executable (first time only)
chmod +x start.sh

# Start all services
./start.sh
```

This will:
1. Start infrastructure services (NATS, PostgreSQL, Redis) via Docker Compose
2. Install Python dependencies for all components
3. Install Node.js dependencies for the dashboard
4. Start N7-Core services
5. Start N7-Sentinels agent
6. Start N7-Strikers agent
7. Start the N7-Dashboard

### Manual Setup

If you prefer to start services individually:

#### 1. Start Infrastructure Services

```bash
cd deploy
docker-compose up -d
```

Verify services are running:
```bash
docker-compose ps
```

#### 2. Install Python Dependencies

```bash
# N7-Core
cd n7-core
pip install -r requirements.txt

# N7-Sentinels
cd ../n7-sentinels
pip install -r requirements.txt

# N7-Strikers
cd ../n7-strikers
pip install -r requirements.txt
```

#### 3. Install Dashboard Dependencies

```bash
cd n7-dashboard
npm install
```

#### 4. Start Services

Open 4 separate terminal windows/tabs:

**Terminal 1 - N7-Core:**
```bash
cd n7-core
python main.py
```

**Terminal 2 - N7-Sentinels:**
```bash
cd n7-sentinels
python main.py
```

**Terminal 3 - N7-Strikers:**
```bash
cd n7-strikers
python main.py
```

**Terminal 4 - N7-Dashboard:**
```bash
cd n7-dashboard
npm run dev
```

## 📊 Access Points

Once all services are running:

- **Dashboard:** http://localhost:5173
- **API Gateway:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs
- **NATS Monitoring:** http://localhost:8222

## 🛑 Stopping Services

### Using the Startup Script

Press `Ctrl+C` in the terminal running the script to stop all services.

### Manual Shutdown

1. Press `Ctrl+C` in each terminal running Python/Node services
2. Stop infrastructure services:
   ```bash
   cd deploy
   docker-compose down
   ```

To stop and remove all data:
```bash
cd deploy
docker-compose down -v
```

## 🔧 Configuration

Configuration files are located in each component:

- **N7-Core:** Environment variables can be set in the shell or create `.env` file
- **N7-Sentinels:** `n7_sentinels/config.py`
- **N7-Strikers:** `n7_strikers/config.py`
- **Infrastructure:** `deploy/docker-compose.yml`

### Key Environment Variables

```bash
# Database
POSTGRES_USER=n7user
POSTGRES_PASSWORD=n7password
POSTGRES_DB=n7
DATABASE_URL=postgresql://n7user:n7password@localhost:5432/n7

# NATS
NATS_URL=nats://localhost:4222

# Redis
REDIS_URL=redis://localhost:6379

# API Gateway
API_HOST=0.0.0.0
API_PORT=8000
```

## 📚 Documentation

For more detailed information, see:

- **[User Manual](docs/USER_MANUAL.md)** - Complete user guide
- **[Technical Design](docs/TDD.md)** - Technical architecture and design
- **[Requirements](docs/SRS.md)** - Software requirements specification
- **[Test Plan](docs/TEST_PLAN.md)** - Testing strategy and procedures

## 🐛 Troubleshooting

### Common Issues

**Issue: Docker containers won't start**
```bash
# Check if ports are already in use
lsof -i :4222  # NATS
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis

# Solution: Stop conflicting services or change ports in docker-compose.yml
```

**Issue: Python import errors**
```bash
# Ensure you're in the correct directory and dependencies are installed
cd n7-core  # or n7-sentinels, n7-strikers
pip install -r requirements.txt
```

**Issue: Dashboard won't start**
```bash
# Clear npm cache and reinstall
cd n7-dashboard
rm -rf node_modules package-lock.json
npm install
```

**Issue: NATS connection errors**
```bash
# Verify NATS is running
docker-compose ps

# Check NATS logs
docker logs n7-nats

# Restart NATS
docker-compose restart nats
```

### Logs

View logs for each service:

```bash
# Infrastructure services
docker-compose logs -f nats
docker-compose logs -f postgres
docker-compose logs -f redis

# Application services
# Check the terminal where each service is running
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is open-source. See LICENSE file for details.

## 🔗 Links

- [GitHub Repository](https://github.com/yourusername/naga-7)
- [Documentation](docs/)
- [Issue Tracker](https://github.com/yourusername/naga-7/issues)

## 💡 Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Check the [User Manual](docs/USER_MANUAL.md)
- Review the [Technical Documentation](docs/TDD.md)
