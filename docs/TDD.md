# Naga-7 (N7) — Technical Design Document (TDD)

**Version:** 1.0.0
**Date:** 2026-02-17
**Status:** Draft
**Classification:** Open Source — Public

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Architectural Overview](#2-architectural-overview)
3. [Technology Stack](#3-technology-stack)
4. [N7-Core Architecture](#4-n7-core-architecture)
5. [N7-Sentinel Architecture](#5-n7-sentinel-architecture)
6. [N7-Striker Architecture](#6-n7-striker-architecture)
7. [Communication Architecture](#7-communication-architecture)
8. [Data Architecture](#8-data-architecture)
9. [Security Architecture](#9-security-architecture)
10. [Deployment Architecture](#10-deployment-architecture)
11. [Plugin and Extension System](#11-plugin-and-extension-system)
12. [Observability Architecture](#12-observability-architecture)
13. [Failure Modes and Recovery](#13-failure-modes-and-recovery)
14. [Performance Engineering](#14-performance-engineering)
15. [Development Standards](#15-development-standards)

---

## 1. Introduction

### 1.1 Purpose

This Technical Design Document defines the system architecture, component design, technology choices, and implementation
patterns for Naga-7. It serves as the technical blueprint for development.

### 1.2 Audience

Software engineers, security engineers, DevOps engineers, and open-source contributors building and extending N7.

### 1.3 References

- [BRD.md](./BRD.md) — Business Requirements
- [SRS.md](./SRS.md) — Software Requirements Specification

---

## 2. Architectural Overview

### 2.1 High-Level Architecture

N7 follows a **hub-and-spoke architecture** with the Core as the central hub and Sentinels/Strikers as distributed
spokes.

```
                              ┌─────────────────────┐
                              │     External         │
                              │   Integrations       │
                              │ (Slack, JIRA, SIEM)  │
                              └──────────┬──────────┘
                                         │ Webhooks/API
                                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                         N7-CORE CLUSTER                          │
│                                                                  │
│  ┌───────────┐  ┌────────────┐  ┌───────────┐  ┌─────────────┐  │
│  │  API      │  │  Event     │  │ Decision  │  │   Agent     │  │
│  │  Gateway  │  │  Pipeline  │  │  Engine   │  │   Manager   │  │
│  └─────┬─────┘  └──────┬─────┘  └─────┬─────┘  └──────┬──────┘  │
│        │               │              │               │          │
│        ▼               ▼              ▼               ▼          │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              Shared State Layer                           │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐               │    │
│  │  │PostgreSQL│  │  Redis   │  │TimescaleDB│               │    │
│  │  │(State)   │  │(Cache/   │  │(Events/  │               │    │
│  │  │          │  │ PubSub)  │  │ Metrics) │               │    │
│  │  └──────────┘  └──────────┘  └──────────┘               │    │
│  └──────────────────────────────────────────────────────────┘    │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │   Message Bus   │
                    │  (NATS / Kafka) │
                    └───┬─────────┬───┘
            ┌───────────┘         └───────────┐
            ▼                                 ▼
┌─────────────────────────┐    ┌─────────────────────────┐
│     N7-SENTINELS        │    │     N7-STRIKERS         │
│                         │    │                         │
│  ┌───────┐ ┌───────┐   │    │  ┌───────┐ ┌────────┐  │
│  │Network│ │Endpt. │   │    │  │Network│ │Endpt.  │  │
│  │Sentin.│ │Sentin.│   │    │  │Strike.│ │Strike. │  │
│  └───────┘ └───────┘   │    │  └───────┘ └────────┘  │
│  ┌───────┐ ┌───────┐   │    │  ┌───────┐ ┌────────┐  │
│  │ Cloud │ │  Log  │   │    │  │ Cloud │ │Forensic│  │
│  │Sentin.│ │Sentin.│   │    │  │Strike.│ │Collect.│  │
│  └───────┘ └───────┘   │    │  └───────┘ └────────┘  │
└─────────────────────────┘    └─────────────────────────┘
```

### 2.2 Design Principles

1. **Defense in Depth:** N7 itself is designed with layered security — compromising one agent does not compromise the
   system.
2. **Fail-Safe Defaults:** When uncertain, N7 escalates to humans rather than taking autonomous action.
3. **Explainability:** Every automated decision includes a machine-readable and human-readable reasoning trace.
4. **Loose Coupling:** Components communicate via message bus; any component can be replaced or upgraded independently.
5. **Convention over Configuration:** Sensible defaults with deep customization available.
6. **Minimal Privilege:** Each agent operates with the minimum permissions required for its function.
7. **Idempotency:** All response actions are designed to be safely re-executable.

### 2.3 Component Ownership

| Component                       | Primary Language       | Repository Path        |
|---------------------------------|------------------------|------------------------|
| N7-Core                         | Python 3.12+           | `n7-core/`             |
| N7-Sentinels (Framework)        | Python 3.12+           | `n7-sentinels/`        |
| Sentinel Probes (perf-critical) | Rust                   | `n7-sentinels/probes/` |
| N7-Strikers (Framework)         | Python 3.12+           | `n7-strikers/`         |
| Dashboard                       | TypeScript (React)     | `n7-dashboard/`        |
| Shared Schemas                  | Protobuf + JSON Schema | `schemas/`             |
| Deployment                      | Helm / Docker Compose  | `deploy/`              |

---

## 3. Technology Stack

### 3.1 Core Technologies

| Layer                           | Technology                                     | Rationale                                                                                        |
|---------------------------------|------------------------------------------------|--------------------------------------------------------------------------------------------------|
| **Primary Language**            | Python 3.12+                                   | Rich security ecosystem, AI/ML libraries, async support, large contributor pool                  |
| **Performance-Critical Probes** | Rust                                           | Memory safety, zero-overhead abstractions, eBPF tooling                                          |
| **Message Bus**                 | NATS 2.10+ (default) / Kafka 3.5+ (enterprise) | NATS: lightweight, built-in JetStream persistence. Kafka: for high-volume enterprise deployments |
| **Primary Database**            | PostgreSQL 16+                                 | ACID compliance, JSONB support, mature ecosystem                                                 |
| **Time-Series Data**            | TimescaleDB (PostgreSQL extension)             | Hypertable partitioning for events, native SQL, compression                                      |
| **Cache / PubSub**              | Redis 7+                                       | In-memory speed for threat intel cache, real-time dashboard updates                              |
| **Object Storage**              | MinIO (self-hosted) / S3-compatible            | Forensic evidence, long-term event archival                                                      |
| **Dashboard**                   | React 18+ / TypeScript                         | Component ecosystem, real-time updates via WebSocket                                             |
| **API Framework**               | FastAPI                                        | Async, OpenAPI auto-generation, Pydantic validation                                              |
| **Serialization**               | Protocol Buffers (inter-agent), JSON (API)     | Protobuf for performance, JSON for human readability                                             |
| **Container Runtime**           | Docker / Podman                                | OCI-compliant, rootless container support                                                        |
| **Orchestration**               | Kubernetes / Docker Compose                    | K8s for production, Compose for development/small deployments                                    |

### 3.2 Key Libraries

| Domain        | Library                              | Purpose                      |
|---------------|--------------------------------------|------------------------------|
| Async Runtime | `asyncio` + `uvloop`                 | High-performance event loop  |
| HTTP Client   | `httpx`                              | Async HTTP for integrations  |
| ORM / DB      | `SQLAlchemy 2.0` + `asyncpg`         | Async database access        |
| Validation    | `pydantic` v2                        | Data model validation        |
| Task Queue    | `arq` (Redis-backed)                 | Background task processing   |
| CLI           | `typer`                              | Agent CLI tooling            |
| Crypto        | `cryptography`                       | TLS, signing, hashing        |
| eBPF          | `bcc` / `libbpf-rs`                  | Linux kernel instrumentation |
| YARA          | `yara-python`                        | Malware signature scanning   |
| ML            | `scikit-learn`, `pytorch` (optional) | Anomaly detection models     |
| Testing       | `pytest`, `pytest-asyncio`           | Test framework               |
| Linting       | `ruff`                               | Fast Python linter/formatter |

---

## 4. N7-Core Architecture

### 4.1 Core Service Decomposition

The Core runs as a set of cooperating async services within a single process (or distributed across processes for
scale).

```
┌──────────────────────────────────────────────────────────────┐
│                       N7-CORE PROCESS                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                   Service Manager                     │    │
│  │        (Lifecycle, Health Checks, Graceful Shutdown)  │    │
│  └────────┬──────────┬──────────┬──────────┬────────────┘    │
│           │          │          │          │                  │
│  ┌────────▼──┐ ┌─────▼──────┐ ┌▼────────┐ ┌▼────────────┐   │
│  │  Event    │ │  Threat    │ │Decision │ │   Agent     │   │
│  │  Pipeline │ │  Correlator│ │ Engine  │ │   Manager   │   │
│  │  Service  │ │  Service   │ │ Service │ │   Service   │   │
│  └────────┬──┘ └─────┬──────┘ └┬────────┘ └┬────────────┘   │
│           │          │         │           │                 │
│  ┌────────▼──┐ ┌─────▼──────┐ ┌▼────────┐ ┌▼────────────┐   │
│  │Enrichment │ │  Threat    │ │Playbook │ │  Notifier   │   │
│  │  Service  │ │  Intel     │ │ Engine  │ │  Service    │   │
│  │           │ │  Service   │ │         │ │             │   │
│  └───────────┘ └────────────┘ └─────────┘ └─────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                    API Gateway                        │    │
│  │          (FastAPI, Auth, RBAC, Rate Limiting)         │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                   Audit Logger                        │    │
│  │     (Append-only, Hash-chained, All Services Feed)    │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Event Pipeline Service

**Responsibility:** Ingest, validate, normalize, deduplicate, and enrich events from Sentinels.

**Processing Stages:**

```
Sentinel Event → [Deserialize] → [Validate Schema] → [Normalize]
    → [Deduplicate] → [Enrich] → [Persist] → [Publish to Correlator]
```

**Key Design Decisions:**

- **Async consumer groups:** Multiple consumers per NATS subject/Kafka partition for parallel processing.
- **Back-pressure handling:** If enrichment or persistence is slow, the pipeline applies back-pressure to the message
  bus consumer (NATS flow control / Kafka consumer lag).
- **Enrichment pipeline:** Enrichment is plugin-based. Built-in enrichers include:
    - Asset inventory lookup (which host/service does this event belong to?)
    - GeoIP resolution for external IPs
    - Threat intelligence IOC matching (IP, domain, file hash)
    - Historical context (has this entity been seen in prior alerts?)

**Deduplication Strategy:**

```python
# Dedup key = hash of (sentinel_type, event_class, key_fields)
# Stored in Redis with TTL = dedup_window (default 60s)
dedup_key = sha256(f"{event.sentinel_type}:{event.event_class}:{event.dedup_fields}")
if not await redis.set(dedup_key, 1, nx=True, ex=dedup_window):
    metrics.increment("events.deduplicated")
    return  # Skip duplicate
```

### 4.3 Threat Correlator Service

**Responsibility:** Correlate individual events/alerts into multi-stage attack patterns.

**Correlation Methods:**

1. **Time-Window Correlation:** Group events from the same source/target within a time window.
2. **Entity-Based Correlation:** Link events sharing common entities (IP, hostname, user, process).
3. **ATT&CK Chain Correlation:** Detect sequences of techniques that form known attack patterns (e.g., Initial Access →
   Execution → Persistence).
4. **Statistical Correlation:** Flag entity behavior that deviates from established baselines.

**Correlation Rule Format (YAML):**

```yaml
# Example: Detect brute-force followed by lateral movement
rule:
  id: "n7-corr-001"
  name: "Brute Force to Lateral Movement"
  description: "Detects successful login after brute-force attempts followed by lateral movement"
  severity: high
  mitre:
    tactics: [credential-access, lateral-movement]
    techniques: [T1110, T1021]

  stages:
    - id: brute_force
      match:
        event_class: authentication
        outcome: failure
      threshold:
        count: 10
        window: 5m
        group_by: [target_user, source_ip]

    - id: successful_login
      match:
        event_class: authentication
        outcome: success
      requires:
        after: brute_force
        window: 2m
        same_fields: [target_user, source_ip]

    - id: lateral_move
      match:
        event_class: network_connection
        direction: outbound
      requires:
        after: successful_login
        window: 15m
        same_fields: [source_ip]
```

### 4.4 Decision Engine Service

**Responsibility:** Evaluate alerts and produce verdicts (auto-respond, escalate, dismiss).

**Decision Flow:**

```
Alert → [Check Escalation Policy] → [Calculate Confidence]
    → [Check Blast Radius] → [Check Cool-down] → Verdict

Verdict Types:
  - auto_respond: Dispatch playbook to Striker
  - escalate: Create incident, notify operators
  - dismiss: Log and close (low confidence / known benign)
  - pending: Insufficient data, request additional Sentinel scans
```

**Escalation Policy Schema:**

```yaml
escalation_policy:
  name: "default"
  rules:
    - severity: [critical, high]
      confidence_threshold: 0.0  # Always escalate
      action: escalate
      notify: [slack, pagerduty]

    - severity: [medium]
      confidence_threshold: 0.85
      action: auto_respond
      playbook: "contain-medium"
      require_approval: false

    - severity: [medium]
      confidence_threshold: 0.0  # Below 0.85 confidence
      action: escalate
      notify: [slack]

    - severity: [low]
      confidence_threshold: 0.70
      action: auto_respond
      playbook: "contain-low"
      require_approval: false

    - severity: [low]
      confidence_threshold: 0.0
      action: dismiss
      log_reason: true

    - severity: [informational]
      action: dismiss
      log_reason: true

  blast_radius_limits:
    max_hosts_per_action: 10
    max_actions_per_hour: 50
    cool_down_minutes: 15
```

**Explainability:** Every verdict includes a reasoning trace:

```json
{
  "verdict": "auto_respond",
  "reasoning": {
    "alert_severity": "medium",
    "threat_score": 72,
    "confidence": 0.91,
    "matching_policy_rule": "medium_high_confidence",
    "blast_radius_check": "passed (1 host affected, limit 10)",
    "cool_down_check": "passed (no recent action on this asset)",
    "selected_playbook": "contain-medium",
    "factors": [
      "Matched known C2 beacon pattern (Cobalt Strike)",
      "Source host is non-critical workstation",
      "No active incident on this asset",
      "Threat intel match: IOC-2024-88712 (high confidence)"
    ]
  }
}
```

### 4.5 Agent Manager Service

**Responsibility:** Track agent lifecycle, health, and capability routing.

**Agent Registry Data Model:**

```python
class AgentRecord:
    agent_id: UUID
    agent_type: Literal["sentinel", "striker"]
    agent_subtype: str  # "network", "endpoint", "cloud", "log", "forensic"
    status: Literal["active", "unhealthy", "draining", "retired"]
    capabilities: list[str]  # ["block_ip", "kill_process", ...]
    zone: str  # Deployment zone/segment
    last_heartbeat: datetime
    config_version: int
    resource_usage: ResourceMetrics
    metadata: dict
```

**Capability-Based Routing:** When the Decision Engine dispatches a playbook, the Agent Manager selects the appropriate
Striker:

```python
async def select_striker(action_type: str, target_zone: str) -> AgentRecord:
    candidates = await registry.find(
        agent_type="striker",
        status="active",
        capabilities__contains=action_type,
        zone=target_zone,
    )
    if not candidates:
        raise NoAvailableStrikerError(action_type, target_zone)
    # Select least-loaded active Striker
    return min(candidates, key=lambda a: a.resource_usage.cpu_percent)
```

---

## 5. N7-Sentinel Architecture

### 5.1 Sentinel Process Model

Each Sentinel runs as an independent process with the following internal architecture:

```
┌──────────────────────────────────────────────────┐
│                 SENTINEL PROCESS                  │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │              Probe Layer                     │  │
│  │  (Data collection — may be Rust for perf)   │  │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐   │  │
│  │  │Probe │ │Probe │ │Probe │ │  Custom  │   │  │
│  │  │  1   │ │  2   │ │  3   │ │  Plugin  │   │  │
│  │  └───┬──┘ └───┬──┘ └───┬──┘ └────┬─────┘   │  │
│  └──────┼────────┼────────┼─────────┼──────────┘  │
│         │        │        │         │             │
│         ▼        ▼        ▼         ▼             │
│  ┌─────────────────────────────────────────────┐  │
│  │           Detection Engine                   │  │
│  │  ┌──────────┐ ┌───────────┐ ┌────────────┐  │  │
│  │  │Signature │ │ Anomaly   │ │  Rule      │  │  │
│  │  │ Matcher  │ │ Detector  │ │  Engine    │  │  │
│  │  └──────────┘ └───────────┘ └────────────┘  │  │
│  └──────────────────────┬──────────────────────┘  │
│                         │                         │
│  ┌──────────────────────▼──────────────────────┐  │
│  │           Event Emitter                      │  │
│  │  (Serialization, Batching, Local Cache)      │  │
│  └──────────────────────┬──────────────────────┘  │
│                         │                         │
│  ┌──────────────────────▼──────────────────────┐  │
│  │           Agent Runtime                      │  │
│  │  (Heartbeat, Config Sync, Resource Monitor)  │  │
│  └─────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### 5.2 Probe Architecture

Probes are the data collection components. They are designed to be:

- **Pluggable:** New probes can be added without modifying the Sentinel framework.
- **Language-agnostic at the interface level:** Probes communicate with the Detection Engine via shared memory (Rust
  probes) or async queues (Python probes).
- **Resource-bounded:** Each probe has a CPU and memory budget enforced by the Agent Runtime.

**Probe Interface (Python):**

```python
from abc import ABC, abstractmethod
from n7.sentinel.types import RawObservation

class Probe(ABC):
    @abstractmethod
    async def initialize(self, config: dict) -> None:
        """Set up probe resources (sockets, eBPF programs, etc.)"""

    @abstractmethod
    async def observe(self) -> AsyncIterator[RawObservation]:
        """Yield raw observations as they occur"""

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up probe resources"""

    @property
    @abstractmethod
    def probe_type(self) -> str:
        """Unique identifier for this probe type"""
```

### 5.3 Detection Engine

The Detection Engine processes raw observations through three detection methods:

1. **Signature Matcher:** Pattern matching against known-bad indicators.
    - Network: Suricata-compatible rule format.
    - Endpoint: YARA rules for file scanning, Sigma rules for log patterns.
    - Cloud: Custom YAML rules for API patterns.

2. **Anomaly Detector:** Statistical and ML-based deviation detection.
    - Baseline learning period (configurable, default: 7 days).
    - Isolation Forest for multivariate anomalies.
    - Time-series decomposition for temporal anomalies.
    - Incrementally updated models (no full retraining required).

3. **Rule Engine:** User-defined detection rules in YAML format.

**Detection Rule Format:**

```yaml
detection:
  id: "n7-det-endpoint-001"
  name: "Suspicious PowerShell Execution"
  severity: high
  mitre: [T1059.001]

  match:
    event_class: process_creation
    conditions:
      - field: process.name
        operator: in
        value: ["powershell.exe", "pwsh.exe"]
      - field: process.command_line
        operator: regex
        value: "(-enc|-encodedcommand|-e\\s)"
      - field: process.parent.name
        operator: not_in
        value: ["explorer.exe", "svchost.exe"]

  exceptions:
    - field: process.command_line
      operator: contains
      value: "known-admin-script.ps1"
```

### 5.4 Offline Cache and Replay

When the message bus is unreachable, the Event Emitter buffers events locally:

- **Storage:** SQLite WAL-mode database in a configurable path.
- **Capacity:** Configurable max size (default: 500 MB), oldest events evicted on overflow.
- **Replay:** On reconnection, buffered events are replayed in order with original timestamps.
- **Dedup on replay:** Events include a `first_seen` timestamp so the Core can handle delayed duplicates.

---

## 6. N7-Striker Architecture

### 6.1 Striker Process Model

```
┌──────────────────────────────────────────────────┐
│                 STRIKER PROCESS                    │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │          Action Executor                     │  │
│  │                                              │  │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────────┐  │  │
│  │  │  Pre-    │ │  Action  │ │   Post-     │  │  │
│  │  │  Flight  │→│  Runner  │→│   Action    │  │  │
│  │  │  Checks  │ │          │ │  Verify     │  │  │
│  │  └──────────┘ └──────────┘ └─────────────┘  │  │
│  └──────────────────────┬──────────────────────┘  │
│                         │                         │
│  ┌──────────────────────▼──────────────────────┐  │
│  │          Rollback Manager                    │  │
│  │  (Stores pre-action state for undo)          │  │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │          Evidence Collector                   │  │
│  │  (Forensic capture before destructive ops)    │  │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │          Agent Runtime                        │  │
│  │  (Heartbeat, Auth Token Verification)         │  │
│  └─────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### 6.2 Action Execution Flow

```
Core dispatches action
         │
         ▼
[1. Verify Authorization Token]
    - Check cryptographic signature from Core
    - Verify action matches Striker capabilities
    - Verify action is within blast-radius limits
         │
         ▼
[2. Pre-Flight Checks]
    - Validate target exists and is reachable
    - Check for conflicting actions in progress
    - Capture pre-action state (for rollback)
         │
         ▼
[3. Evidence Collection] (if destructive action)
    - Capture relevant forensic data
    - Store with SHA-256 integrity hash
         │
         ▼
[4. Execute Action]
    - Run the action module
    - Stream status updates to Core
    - Enforce timeout
         │
         ▼
[5. Post-Action Verification]
    - Verify the action achieved its goal
    - Report final status (succeeded/failed)
         │
         ▼
[6. Report to Core]
    - Full action report with evidence references
    - Rollback instructions if needed
```

### 6.3 Playbook Engine

Playbooks define ordered sequences of Striker actions for specific incident types.

**Playbook Format:**

```yaml
playbook:
  id: "pb-contain-medium"
  name: "Medium Severity Containment"
  description: "Standard containment for medium-severity threats"
  version: 1
  max_duration: 30m

  parameters:
    - name: target_ip
      type: ip_address
      required: true
    - name: target_host
      type: hostname
      required: true
    - name: malicious_process
      type: string
      required: false

  steps:
    - id: collect_evidence
      action: forensic_capture
      params:
        target: "{{ target_host }}"
        capture_types: [process_list, network_connections, recent_files]
      on_failure: continue  # Evidence is best-effort

    - id: block_network
      action: block_ip
      params:
        ip: "{{ target_ip }}"
        direction: both
        duration: 24h
      on_failure: abort
      rollback: unblock_ip

    - id: kill_process
      action: kill_process
      condition: "{{ malicious_process is defined }}"
      params:
        target_host: "{{ target_host }}"
        process_name: "{{ malicious_process }}"
      on_failure: continue

    - id: notify
      action: notify
      params:
        channels: [slack]
        message: "Contained threat on {{ target_host }}: blocked {{ target_ip }}, killed {{ malicious_process | default('N/A') }}"
```

### 6.4 Rollback System

Every action that modifies system state records a rollback entry:

```python
class RollbackEntry:
    action_id: UUID
    rollback_action: str  # The action type to undo
    rollback_params: dict  # Parameters for the undo action
    pre_state: dict  # Captured state before action
    created_at: datetime
    expires_at: datetime  # Rollback entries expire (default: 24h)
```

Rollback can be triggered:

- **Manually** by an operator via dashboard or API.
- **Automatically** if a playbook step fails and `on_failure: rollback_all` is set.
- **On timeout** if the incident is not confirmed within a configurable window.

---

## 7. Communication Architecture

### 7.1 Message Bus Topology

**NATS Configuration (Default):**

```
NATS Subjects:
  n7.events.{sentinel_type}      → Event stream from Sentinels
  n7.heartbeat.{agent_id}        → Agent heartbeat
  n7.alerts                      → Alert notifications (internal)
  n7.actions.{striker_id}        → Action dispatch to Strikers
  n7.actions.status              → Action status updates from Strikers
  n7.config.{agent_id}           → Configuration updates to agents
  n7.audit                       → Audit log stream

JetStream Streams:
  EVENTS     → Persistent event storage (subjects: n7.events.>)
  ACTIONS    → Persistent action tracking (subjects: n7.actions.>)
  AUDIT      → Persistent audit log (subjects: n7.audit)
```

**Message Envelope:**

```protobuf
message N7Envelope {
  string message_id = 1;       // UUID
  string source_agent_id = 2;  // Sender agent UUID
  int64 timestamp_ns = 3;      // Nanosecond Unix timestamp
  string message_type = 4;     // "event", "alert", "action", "heartbeat", etc.
  bytes payload = 5;           // Serialized inner message
  bytes signature = 6;         // Ed25519 signature of payload
}
```

### 7.2 Authentication and Authorization

All inter-agent messages are:

1. **Signed:** Each agent has an Ed25519 key pair. The payload is signed by the sender.
2. **Verified:** The receiver verifies the signature against the sender's registered public key.
3. **Transported over mTLS:** NATS/Kafka connections use mutual TLS for transport encryption.

**Action Authorization:** Striker actions carry an authorization token from the Core:

```protobuf
message ActionAuthorization {
  string action_id = 1;
  string incident_id = 2;
  string authorized_action = 3;    // e.g., "block_ip"
  map<string, string> params = 4;
  string target_zone = 5;
  int64 expires_at_ns = 6;
  bytes core_signature = 7;        // Core's Ed25519 signature
}
```

Strikers reject any action that:

- Has an invalid or expired authorization token.
- Requests an action not in the Striker's declared capabilities.
- Targets a zone the Striker is not assigned to.

---

## 8. Data Architecture

### 8.1 Database Schema Overview

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   agents    │    │   events    │    │threat_intel │
│             │    │ (timescale) │    │             │
├─────────────┤    ├─────────────┤    ├─────────────┤
│ agent_id PK │    │ event_id PK │    │ ioc_id PK   │
│ agent_type  │    │ timestamp   │    │ ioc_type    │
│ subtype     │    │ sentinel_id │──→ │ ioc_value   │
│ status      │    │ event_class │    │ confidence  │
│ capabilities│    │ severity    │    │ source      │
│ zone        │    │ raw_data    │    │ expires_at  │
│ config      │    │ enrichments │    └─────────────┘
│ last_hb     │    │ mitre_ids   │
└─────────────┘    └──────┬──────┘
                          │
                   ┌──────▼──────┐    ┌─────────────┐
                   │   alerts    │    │  playbooks  │
                   ├─────────────┤    ├─────────────┤
                   │ alert_id PK │    │playbook_id  │
                   │ event_ids   │    │ name        │
                   │ threat_score│    │ version     │
                   │ severity    │    │ definition  │
                   │ status      │    │ enabled     │
                   │ verdict     │    └──────┬──────┘
                   │ reasoning   │           │
                   └──────┬──────┘    ┌──────▼──────┐
                          │           │  incidents  │
                   ┌──────▼──────┐    ├─────────────┤
                   │   actions   │    │incident_id  │
                   ├─────────────┤    │ alert_ids   │
                   │ action_id PK│←──│ status      │
                   │ incident_id │    │ assigned_to │
                   │ striker_id  │    │ playbook_id │
                   │ action_type │    │ timeline    │
                   │ parameters  │    └─────────────┘
                   │ status      │
                   │ evidence    │    ┌─────────────┐
                   │ rollback    │    │ audit_log   │
                   └─────────────┘    ├─────────────┤
                                      │ log_id PK   │
                                      │ timestamp   │
                                      │ actor       │
                                      │ action      │
                                      │ resource    │
                                      │ details     │
                                      │ prev_hash   │
                                      │ hash        │
                                      └─────────────┘
```

### 8.2 Audit Log Hash Chain

Audit logs are tamper-evident via hash chaining:

```python
import hashlib, json

def compute_audit_hash(entry: AuditEntry, prev_hash: str) -> str:
    content = json.dumps({
        "log_id": str(entry.log_id),
        "timestamp": entry.timestamp.isoformat(),
        "actor": entry.actor,
        "action": entry.action,
        "resource": entry.resource,
        "details": entry.details,
        "prev_hash": prev_hash,
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()
```

---

## 9. Security Architecture

### 9.1 Trust Model

```
                    ┌─────────────┐
                    │   Root CA   │
                    │  (Offline)  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │Core CA   │ │Sentinel  │ │Striker   │
        │          │ │  CA      │ │  CA      │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
        ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐
        │Core Cert │ │Agent     │ │Agent     │
        │+ Key     │ │Certs     │ │Certs     │
        └──────────┘ └──────────┘ └──────────┘
```

### 9.2 Certificate Management

- **Root CA:** Generated offline, stored in hardware security module (HSM) or encrypted file.
- **Intermediate CAs:** Per-component type (Core, Sentinel, Striker).
- **Agent Certificates:** Auto-provisioned on agent registration, short-lived (24h), auto-rotated.
- **Certificate Rotation:** Agents request new certificates before expiry. The Core validates agent identity before
  issuing.

### 9.3 Secrets Management

| Secret Type          | Storage                          | Rotation               |
|----------------------|----------------------------------|------------------------|
| Agent private keys   | Agent local keystore (encrypted) | 24h (with cert)        |
| Core signing key     | Vault / K8s Secret (encrypted)   | 30 days                |
| Database credentials | Vault / K8s Secret (encrypted)   | 90 days                |
| API keys             | PostgreSQL (bcrypt hashed)       | User-managed           |
| Integration tokens   | Vault / K8s Secret (encrypted)   | Per-integration policy |

### 9.4 Agent Tamper Detection

Each agent binary is signed during CI/CD. On startup:

1. The agent verifies its own binary hash against a signed manifest.
2. The agent reports its binary hash in heartbeat messages.
3. The Core compares reported hashes against expected values.
4. Mismatches trigger a critical alert and the agent is quarantined.

---

## 10. Deployment Architecture

### 10.1 Kubernetes Deployment (Production)

```
┌──────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                          │
│                                                               │
│  Namespace: n7-system                                         │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │ │
│  │  │Core Pod  │  │Core Pod  │  │Core Pod  │  (3 replicas)│ │
│  │  │(active)  │  │(active)  │  │(standby) │              │ │
│  │  └──────────┘  └──────────┘  └──────────┘              │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │ │
│  │  │Dashboard │  │NATS Pod  │  │NATS Pod  │  (HA NATS)  │ │
│  │  │Pod       │  │          │  │          │              │ │
│  │  └──────────┘  └──────────┘  └──────────┘              │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │ │
│  │  │Postgres  │  │Redis     │  │MinIO     │              │ │
│  │  │(Primary) │  │(Cluster) │  │(Evidence)│              │ │
│  │  └──────────┘  └──────────┘  └──────────┘              │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
│  Namespace: n7-sentinels                                      │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  DaemonSet: endpoint-sentinel  (one per node)            │ │
│  │  Deployment: network-sentinel  (per-segment)             │ │
│  │  Deployment: cloud-sentinel    (per-cloud-account)       │ │
│  │  Deployment: log-sentinel      (per-log-source)          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
│  Namespace: n7-strikers                                       │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Deployment: network-striker   (per-zone)                │ │
│  │  Deployment: endpoint-striker  (per-zone)                │ │
│  │  Deployment: cloud-striker     (per-cloud-account)       │ │
│  │  Deployment: forensic-collector (shared pool)            │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 10.2 Docker Compose Deployment (Development / Small)

For development and small-scale deployments, a Docker Compose configuration provides all components:

```yaml
# Simplified — full compose file in deploy/docker-compose.yml
services:
  n7-core:
    image: n7/core:latest
    ports: ["8080:8080"]
    depends_on: [postgres, redis, nats]

  n7-dashboard:
    image: n7/dashboard:latest
    ports: ["3000:3000"]
    depends_on: [n7-core]

  n7-network-sentinel:
    image: n7/sentinel-network:latest
    network_mode: host  # Requires host networking for packet capture
    depends_on: [nats]

  n7-endpoint-sentinel:
    image: n7/sentinel-endpoint:latest
    privileged: true  # Required for eBPF
    depends_on: [nats]

  n7-network-striker:
    image: n7/striker-network:latest
    depends_on: [nats]

  postgres:
    image: timescale/timescaledb:latest-pg16
    volumes: ["pgdata:/var/lib/postgresql/data"]

  redis:
    image: redis:7-alpine

  nats:
    image: nats:2.10-alpine
    command: ["--jetstream"]

  minio:
    image: minio/minio:latest
    command: ["server", "/data"]
```

### 10.3 Deployment Sizing Guide

| Deployment Size | Endpoints    | Events/sec     | Core              | Sentinels | Strikers  | DB                |
|-----------------|--------------|----------------|-------------------|-----------|-----------|-------------------|
| **Small**       | < 100        | < 1,000        | 1x (4 CPU, 8 GB)  | Per scope | 2-3 total | Single node       |
| **Medium**      | 100-1,000    | 1,000-10,000   | 3x (4 CPU, 16 GB) | Per scope | 4-6 total | Primary + replica |
| **Large**       | 1,000-10,000 | 10,000-100,000 | 5x (8 CPU, 32 GB) | Per scope | 10+ total | HA cluster        |

---

## 11. Plugin and Extension System

### 11.1 Plugin Types

| Plugin Type                 | Extension Point             | Interface               |
|-----------------------------|-----------------------------|-------------------------|
| **Custom Sentinel Probe**   | New data collection source  | `Probe` ABC             |
| **Custom Detection Rule**   | New detection logic         | YAML rule format        |
| **Custom Correlation Rule** | New correlation patterns    | YAML correlation format |
| **Custom Striker Action**   | New response action         | `StrikerAction` ABC     |
| **Custom Enricher**         | New event enrichment source | `Enricher` ABC          |
| **Custom Notifier**         | New notification channel    | `Notifier` ABC          |
| **Dashboard Widget**        | New dashboard visualization | React component         |

### 11.2 Plugin Discovery and Loading

Plugins are discovered via Python entry points:

```toml
# Plugin's pyproject.toml
[project.entry-points."n7.sentinel.probes"]
my_custom_probe = "my_plugin:MyCustomProbe"

[project.entry-points."n7.striker.actions"]
my_custom_action = "my_plugin:MyCustomAction"

[project.entry-points."n7.enrichers"]
my_custom_enricher = "my_plugin:MyCustomEnricher"
```

### 11.3 Plugin Sandboxing

Plugins run within the agent process but are sandboxed:

- **Resource limits:** CPU and memory budgets per plugin.
- **Capability restrictions:** Plugins declare required permissions in their manifest.
- **Fault isolation:** Plugin exceptions are caught and logged without crashing the host agent.
- **Audit:** All plugin actions are logged in the audit trail.

---

## 12. Observability Architecture

### 12.1 Metrics

All components emit Prometheus-compatible metrics:

**Core Metrics:**

- `n7_events_ingested_total` — Total events ingested (by sentinel_type)
- `n7_events_deduplicated_total` — Events dropped as duplicates
- `n7_alerts_generated_total` — Alerts created (by severity)
- `n7_verdicts_total` — Verdicts issued (by type: auto_respond, escalate, dismiss)
- `n7_actions_dispatched_total` — Actions sent to Strikers (by action_type)
- `n7_actions_completed_total` — Actions completed (by status: succeeded, failed)
- `n7_pipeline_latency_seconds` — Event pipeline processing time (histogram)
- `n7_decision_latency_seconds` — Decision engine latency (histogram)

**Sentinel Metrics:**

- `n7_sentinel_observations_total` — Raw observations collected
- `n7_sentinel_detections_total` — Events emitted (by detection_method)
- `n7_sentinel_cache_size_bytes` — Offline cache size
- `n7_sentinel_cpu_usage_percent` — Agent CPU usage
- `n7_sentinel_memory_usage_bytes` — Agent memory usage

**Striker Metrics:**

- `n7_striker_actions_received_total` — Actions received
- `n7_striker_actions_executed_total` — Actions executed (by status)
- `n7_striker_action_duration_seconds` — Action execution time (histogram)
- `n7_striker_rollbacks_total` — Rollback operations performed

### 12.2 Logging

All components output structured JSON logs:

```json
{
  "timestamp": "2026-02-17T10:30:00.000Z",
  "level": "INFO",
  "component": "n7-core.decision_engine",
  "message": "Verdict issued for alert",
  "alert_id": "a1b2c3d4",
  "verdict": "auto_respond",
  "playbook": "contain-medium",
  "trace_id": "t9x8y7z6"
}
```

### 12.3 Distributed Tracing

All operations carry a `trace_id` that threads through the entire pipeline:

```
Sentinel detection → Event Pipeline → Correlator → Decision Engine
    → Striker dispatch → Action execution → Status report
```

This enables operators to trace any action back to the original detection event.

---

## 13. Failure Modes and Recovery

| Failure                             | Detection                | Impact                                                | Recovery                                         |
|-------------------------------------|--------------------------|-------------------------------------------------------|--------------------------------------------------|
| Core process crash                  | K8s liveness probe       | No new verdicts, actions stall                        | Auto-restart, standby promotion                  |
| Message bus outage                  | Connection error + retry | Sentinels cache locally, Strikers idle                | Reconnect with backoff, replay cached events     |
| Database outage                     | Connection pool errors   | No persistence, read-only mode                        | Failover to replica, queue writes                |
| Sentinel crash                      | Missed heartbeats        | Blind spot in monitoring                              | Auto-restart, Core marks coverage gap            |
| Striker crash                       | Missed heartbeats        | Cannot execute assigned actions                       | Core reassigns pending actions to other Strikers |
| Network partition (Sentinel ↔ Core) | Heartbeat timeout        | Sentinel operates autonomously, caches events         | Reconnect and replay                             |
| Network partition (Striker ↔ Core)  | Heartbeat timeout        | Striker completes in-flight actions, rejects new ones | Reconnect, Core re-dispatches pending actions    |

---

## 14. Performance Engineering

### 14.1 Event Pipeline Optimization

- **Batch processing:** Events are consumed in batches (default: 100) to amortize serialization overhead.
- **Parallel enrichment:** Enrichment stages run concurrently (asset lookup, geo-IP, threat intel).
- **Connection pooling:** Database connections pooled via `asyncpg` (default: 20 connections per Core instance).
- **Compression:** NATS messages use zstd compression for payloads > 1KB.

### 14.2 Sentinel Performance (Endpoint)

- **eBPF for Linux:** Kernel-level instrumentation avoids context-switch overhead of user-space polling.
- **Ring buffers:** eBPF programs emit events via perf ring buffers; user-space reads in batches.
- **Sampling:** High-volume data sources (e.g., network packets) support configurable sampling rates.
- **Resource governor:** A watchdog thread monitors CPU/memory and throttles probes if limits are approached.

### 14.3 Benchmarking Targets

| Scenario                  | Target                 | Measurement Method                      |
|---------------------------|------------------------|-----------------------------------------|
| Event ingestion (Core)    | 10,000 events/sec      | Load test with synthetic events         |
| Alert correlation (Core)  | 1,000 alerts/sec       | Load test with correlated event streams |
| Sentinel CPU overhead     | < 5% on monitored host | `perf stat` during normal workload      |
| Sentinel memory footprint | < 256 MB RSS           | `/proc/pid/status` monitoring           |
| Striker action latency    | < 2 seconds (p99)      | End-to-end timing in integration tests  |

---

## 15. Development Standards

### 15.1 Code Organization

```
naga-7/
├── n7-core/
│   ├── n7_core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── services/
│   │   │   ├── event_pipeline.py
│   │   │   ├── threat_correlator.py
│   │   │   ├── decision_engine.py
│   │   │   ├── agent_manager.py
│   │   │   ├── enrichment.py
│   │   │   ├── threat_intel.py
│   │   │   ├── playbook_engine.py
│   │   │   ├── notifier.py
│   │   │   └── audit_logger.py
│   │   ├── api/
│   │   │   ├── app.py
│   │   │   ├── auth.py
│   │   │   ├── routes/
│   │   │   └── middleware/
│   │   ├── models/
│   │   └── schemas/
│   ├── tests/
│   └── pyproject.toml
├── n7-sentinels/
│   ├── n7_sentinels/
│   │   ├── framework/
│   │   ├── probes/
│   │   ├── detection/
│   │   └── types/
│   ├── probes/           # Rust probes
│   │   ├── ebpf/
│   │   └── network/
│   └── tests/
├── n7-strikers/
│   ├── n7_strikers/
│   │   ├── framework/
│   │   ├── actions/
│   │   ├── rollback/
│   │   └── evidence/
│   └── tests/
├── n7-dashboard/
│   ├── src/
│   └── package.json
├── schemas/
│   ├── protobuf/
│   └── json/
├── deploy/
│   ├── docker/
│   ├── helm/
│   ├── compose/
│   └── ansible/
└── docs/
```

### 15.2 Coding Standards

- **Python:** PEP 8, enforced by `ruff`. Type hints required on all public interfaces.
- **Rust:** `rustfmt` + `clippy` with `#![deny(clippy::all)]`.
- **TypeScript:** ESLint + Prettier, strict mode.
- **Commits:** Conventional Commits format (`feat:`, `fix:`, `docs:`, etc.).
- **PRs:** Require 2 approvals, CI must pass, no merge if security scan fails.

### 15.3 Testing Standards

- **Unit tests:** All business logic, minimum 80% coverage.
- **Integration tests:** Inter-component communication, database queries, API endpoints.
- **End-to-end tests:** Full pipeline from synthetic event injection to Striker action.
- **Security tests:** SAST (Bandit, Semgrep), dependency scanning (Safety, Trivy), fuzz testing for parsers.
- **Performance tests:** Load testing for event pipeline throughput, latency benchmarks.

See [TEST_PLAN.md](./TEST_PLAN.md) for comprehensive test plan.
