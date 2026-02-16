# Naga-7 (N7)

Naga-7 is an open-source, multi-level AI agent system designed to continuously monitor enterprise infrastructure for security threats and actively mitigate them in real time.

## Architecture

The system comprises three core components:

- **N7-Core:** Central orchestrator managing agents, threat intelligence, and decision making.
- **N7-Sentinels:** Autonomous monitoring agents for detecting anomalies and threats.
- **N7-Strikers:** Autonomous response agents for executing containment and remediation actions.

## Directory Structure

- `n7-core/`: Core services (Python)
- `n7-sentinels/`: Sentinel agents (Python)
- `n7-strikers/`: Striker agents (Python)
- `n7-dashboard/`: Web dashboard (React/TypeScript)
- `schemas/`: Shared data schemas (Protobuf/JSON)
- `deploy/`: Deployment configurations (Docker/Helm)
- `docs/`: Project documentation

## Getting Started

See `docs/USER_MANUAL.md` for detailed instructions on setting up and using Naga-7.
