# Naga-7 (N7) — Software Requirements Specification (SRS)

**Version:** 1.0.0
**Date:** 2026-02-17
**Status:** Draft
**Classification:** Open Source — Public
**Standard:** IEEE 830-1998 Adapted

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Overall Description](#2-overall-description)
3. [Functional Requirements — N7-Core](#3-functional-requirements--n7-core)
4. [Functional Requirements — N7-Sentinels](#4-functional-requirements--n7-sentinels)
5. [Functional Requirements — N7-Strikers](#5-functional-requirements--n7-strikers)
6. [Functional Requirements — Dashboard & API](#6-functional-requirements--dashboard--api)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [External Interface Requirements](#8-external-interface-requirements)
9. [Data Requirements](#9-data-requirements)
10. [Security Requirements](#10-security-requirements)
11. [Appendices](#11-appendices)

---

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification defines the functional and non-functional requirements for the Naga-7 (N7) multi-level AI agent security system. It serves as the authoritative reference for development, testing, and acceptance.

### 1.2 Scope

N7 is a distributed agent system with three tiers:

- **N7-Core:** Central orchestrator providing coordination, state management, threat intelligence, and operator interface.
- **N7-Sentinels:** Monitoring agents that observe infrastructure and detect threats.
- **N7-Strikers:** Response agents that execute containment and remediation actions.

### 1.3 Definitions and Abbreviations

See [BRD Glossary](./BRD.md#10-glossary) for shared definitions.

Additional terms:

| Term | Definition |
|------|-----------|
| **Event** | A raw observation from a Sentinel (e.g., suspicious process spawned) |
| **Alert** | An event or correlated set of events that exceeds a detection threshold |
| **Incident** | A confirmed threat that requires response action |
| **Playbook** | A defined sequence of Striker actions for a specific incident type |
| **Verdict** | The Core's decision on how to handle an alert (auto-respond, escalate, dismiss) |
| **Agent Manifest** | A configuration file declaring a Sentinel or Striker's capabilities, requirements, and permissions |

### 1.4 References

- [BRD.md](./BRD.md) — Business Requirements Document
- [TDD.md](./TDD.md) — Technical Design Document
- MITRE ATT&CK Framework v14+
- STIX 2.1 Specification
- OCSF (Open Cybersecurity Schema Framework) v1.1

---

## 2. Overall Description

### 2.1 System Context

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Enterprise Infrastructure                     │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │
│  │ Endpoints │  │ Network  │  │  Cloud   │  │ Applications / APIs  │ │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └──────────┬───────────┘ │
│        │             │             │                   │             │
│        ▼             ▼             ▼                   ▼             │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    N7-Sentinels (Monitoring)                  │    │
│  │  ┌──────────┐ ┌────────────┐ ┌───────────┐ ┌─────────────┐  │    │
│  │  │ Endpoint │ │  Network   │ │   Cloud   │ │    Log      │  │    │
│  │  │ Sentinel │ │  Sentinel  │ │  Sentinel │ │  Sentinel   │  │    │
│  │  └────┬─────┘ └─────┬──────┘ └─────┬─────┘ └──────┬──────┘  │    │
│  └───────┼─────────────┼──────────────┼───────────────┼─────────┘    │
│          │             │              │               │              │
│          ▼             ▼              ▼               ▼              │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                      N7-Core (Orchestrator)                   │    │
│  │                                                               │    │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐  │    │
│  │  │  Event     │ │  Threat    │ │  Decision  │ │  Agent    │  │    │
│  │  │  Pipeline  │ │  Correlator│ │  Engine    │ │  Manager  │  │    │
│  │  └────────────┘ └────────────┘ └─────┬──────┘ └───────────┘  │    │
│  └──────────────────────────────────────┼────────────────────────┘    │
│                                         │                            │
│                                         ▼                            │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    N7-Strikers (Response)                      │    │
│  │  ┌──────────┐ ┌────────────┐ ┌───────────┐ ┌─────────────┐  │    │
│  │  │ Network  │ │  Endpoint  │ │   Cloud   │ │  Forensic   │  │    │
│  │  │ Striker  │ │  Striker   │ │  Striker  │ │  Collector  │  │    │
│  │  └──────────┘ └────────────┘ └───────────┘ └─────────────┘  │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 User Classes

| User Class | Description | Access Level |
|------------|-------------|-------------|
| **Administrator** | Deploys, configures, and maintains N7 infrastructure | Full system access |
| **Analyst** | Monitors dashboards, reviews alerts, approves escalated actions | Read + approve actions |
| **Operator** | Interacts with N7 during active incidents, triggers manual responses | Read + execute responses |
| **Auditor** | Reviews audit logs and compliance reports | Read-only to audit data |
| **Developer** | Extends N7 with custom Sentinels, Strikers, or integrations | Plugin development access |

### 2.3 Operating Environment

| Component | Requirement |
|-----------|-------------|
| **Core** | Linux (x86_64, ARM64), 4+ CPU cores, 8+ GB RAM, container runtime |
| **Sentinels** | Linux/Windows/macOS, 1+ CPU core, 256 MB RAM per agent |
| **Strikers** | Linux (x86_64, ARM64), 2+ CPU cores, 2+ GB RAM per agent |
| **Database** | PostgreSQL 15+ for relational data, Redis 7+ for cache/pubsub |
| **Message Bus** | NATS 2.10+ or Apache Kafka 3.5+ |
| **Runtime** | Python 3.12+, Rust (for performance-critical Sentinel probes) |

---

## 3. Functional Requirements — N7-Core

### 3.1 Event Pipeline

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-C001 | The Core shall accept events from Sentinels via a message bus (NATS/Kafka) using a standardized event schema (OCSF-based) | Critical | BR-D01 |
| FR-C002 | The Core shall validate, normalize, and enrich incoming events with contextual metadata (asset inventory, threat intel, geolocation) | Critical | BR-D03 |
| FR-C003 | The Core shall deduplicate events with identical signatures within a configurable time window (default: 60 seconds) | High | BR-D01 |
| FR-C004 | The Core shall persist all raw and enriched events to a time-series data store with configurable retention (default: 90 days) | High | BR-O05 |
| FR-C005 | The Core shall process a minimum of 10,000 events per second on reference hardware (4 cores, 8 GB RAM) | High | BR-OP03 |

### 3.2 Threat Correlation

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-C010 | The Core shall correlate events across multiple Sentinels using configurable correlation rules (time-window, entity-based, pattern-based) | Critical | BR-D06 |
| FR-C011 | The Core shall map correlated events to MITRE ATT&CK techniques and tactics | High | BR-D05 |
| FR-C012 | The Core shall maintain a real-time threat graph linking related events, alerts, and affected assets | High | BR-O01 |
| FR-C013 | The Core shall support user-defined correlation rules in a declarative YAML format | High | BR-D04 |
| FR-C014 | The Core shall calculate a composite threat score (0-100) for each alert based on severity, confidence, asset criticality, and threat intelligence context | Critical | BR-D05 |

### 3.3 Decision Engine

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-C020 | The Core shall evaluate each alert against the configured escalation policy to produce a verdict (auto-respond, escalate, dismiss) | Critical | BR-O03 |
| FR-C021 | The Core shall support multi-level escalation policies with configurable thresholds per severity level | Critical | BR-R02 |
| FR-C022 | For auto-respond verdicts, the Core shall select an appropriate playbook and dispatch it to available Strikers | Critical | BR-R01 |
| FR-C023 | For escalate verdicts, the Core shall create an incident record and notify operators via configured channels (dashboard, webhook, email, Slack) | Critical | BR-R02 |
| FR-C024 | The Core shall enforce a configurable cool-down period between repeated automated responses targeting the same asset (default: 15 minutes) | Critical | BR-R05 |
| FR-C025 | The Core shall support a dry-run mode where response actions are logged but not executed | High | BR-R05 |
| FR-C026 | The Decision Engine shall provide an explanation (reasoning trace) for every verdict it produces | Critical | C-05 |

### 3.4 Agent Lifecycle Management

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-C030 | The Core shall maintain a registry of all deployed Sentinels and Strikers with their status, capabilities, and health | Critical | BR-O02 |
| FR-C031 | The Core shall detect agent failures via heartbeat monitoring (configurable interval, default: 30 seconds) and mark agents as unhealthy after 3 consecutive missed heartbeats | Critical | BR-O02 |
| FR-C032 | The Core shall support rolling updates of agent configurations without requiring agent restart | High | BR-O02 |
| FR-C033 | The Core shall enforce agent capability-based routing — only dispatch tasks to Strikers with matching capabilities | Critical | BR-O02 |
| FR-C034 | The Core shall support agent grouping by zone/segment for scoped deployments | Medium | BR-OP02 |

### 3.5 Audit and Compliance

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-C040 | The Core shall log every event, alert, verdict, and response action with timestamps, actor identity, and full context | Critical | BR-O05 |
| FR-C041 | Audit logs shall be append-only and tamper-evident (hash-chained) | Critical | BR-O05 |
| FR-C042 | The Core shall support export of audit logs in OCSF and CEF formats | High | BR-O04 |
| FR-C043 | The Core shall support configurable audit log retention policies with automated archival | Medium | BR-O05 |

---

## 4. Functional Requirements — N7-Sentinels

### 4.1 Common Sentinel Requirements

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-S001 | Each Sentinel shall declare its capabilities and monitored domain in an agent manifest (YAML) | Critical | BR-O02 |
| FR-S002 | Each Sentinel shall emit events to the message bus in the standardized OCSF-based schema | Critical | FR-C001 |
| FR-S003 | Each Sentinel shall send heartbeat messages to the Core at configurable intervals | Critical | FR-C031 |
| FR-S004 | Each Sentinel shall support dynamic configuration updates from the Core without restart | High | FR-C032 |
| FR-S005 | Each Sentinel shall operate within a configurable resource budget (CPU, memory) and self-throttle if limits are approached | High | BR-OP03 |
| FR-S006 | Each Sentinel shall cache events locally if the message bus is unreachable and replay them upon reconnection | High | BR-OP04 |
| FR-S007 | Each Sentinel shall support a plugin interface for custom detection logic | High | BR-D04 |

### 4.2 Network Sentinel

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-S010 | The Network Sentinel shall capture and analyze network traffic via packet capture (libpcap/AF_PACKET) or flow data (NetFlow v9, IPFIX, sFlow) | Critical | BR-D01 |
| FR-S011 | The Network Sentinel shall detect known malicious traffic patterns using signature-based rules (Suricata-compatible rule format) | Critical | BR-D01 |
| FR-S012 | The Network Sentinel shall detect anomalous traffic patterns using statistical baselines (connection frequency, data volume, protocol distribution) | High | BR-D01 |
| FR-S013 | The Network Sentinel shall extract and analyze DNS queries for DGA detection, known-bad domains, and tunneling indicators | High | BR-D01 |
| FR-S014 | The Network Sentinel shall identify and flag unencrypted credentials in network traffic (HTTP Basic Auth, FTP, Telnet) | High | BR-D01 |

### 4.3 Endpoint Sentinel

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-S020 | The Endpoint Sentinel shall monitor process creation and termination events (including command-line arguments, parent process, user context) | Critical | BR-D02 |
| FR-S021 | The Endpoint Sentinel shall monitor file system changes (creation, modification, deletion, permission changes) on configurable paths | Critical | BR-D02 |
| FR-S022 | The Endpoint Sentinel shall monitor authentication events (login success/failure, privilege escalation) | Critical | BR-D02 |
| FR-S023 | The Endpoint Sentinel shall detect known malware signatures via YARA rule scanning on specified paths | High | BR-D02 |
| FR-S024 | The Endpoint Sentinel shall monitor network connections per process (outbound connections, listening ports) | High | BR-D02 |
| FR-S025 | The Endpoint Sentinel shall support Linux (via eBPF), Windows (via ETW), and macOS (via Endpoint Security Framework) | High | BR-D02 |

### 4.4 Cloud Sentinel

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-S030 | The Cloud Sentinel shall ingest cloud audit logs (AWS CloudTrail, Azure Activity Log, GCP Audit Logs) | High | BR-D03 |
| FR-S031 | The Cloud Sentinel shall detect IAM policy changes, new resource provisioning, and security group modifications | High | BR-D03 |
| FR-S032 | The Cloud Sentinel shall detect exposed resources (public S3 buckets, open security groups, unencrypted storage) | High | BR-D03 |
| FR-S033 | The Cloud Sentinel shall detect anomalous API usage patterns (unusual regions, high-frequency calls, off-hours activity) | High | BR-D03 |

### 4.5 Log Sentinel

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-S040 | The Log Sentinel shall ingest logs from syslog (RFC 5424), JSON, and CEF sources | High | BR-D03 |
| FR-S041 | The Log Sentinel shall parse and normalize logs into the OCSF-based event schema | High | FR-C001 |
| FR-S042 | The Log Sentinel shall support configurable log parsing rules (regex, grok, JSON path) | High | BR-D04 |
| FR-S043 | The Log Sentinel shall detect known threat indicators in log content (IOC matching against threat intel feeds) | High | BR-D03 |

---

## 5. Functional Requirements — N7-Strikers

### 5.1 Common Striker Requirements

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-K001 | Each Striker shall declare its capabilities and action types in an agent manifest (YAML) | Critical | FR-C033 |
| FR-K002 | Each Striker shall accept action requests from the Core via the message bus | Critical | FR-C022 |
| FR-K003 | Each Striker shall report action status (queued, executing, succeeded, failed, rolled_back) to the Core in real time | Critical | BR-O05 |
| FR-K004 | Each Striker shall support action rollback — reversing the effects of a previously executed action | High | BR-R04 |
| FR-K005 | Each Striker shall enforce action timeouts (configurable, default: 5 minutes) and report timeout as failure | High | BR-R05 |
| FR-K006 | Each Striker shall validate that received actions match its declared capabilities before execution | Critical | FR-C033 |
| FR-K007 | Each Striker shall capture forensic evidence (logs, screenshots, memory dumps) before executing destructive containment actions | High | BR-O05 |

### 5.2 Network Striker

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-K010 | The Network Striker shall block IP addresses/CIDR ranges by pushing rules to configured firewalls (iptables, cloud security groups, network ACLs) | Critical | BR-R01 |
| FR-K011 | The Network Striker shall isolate network segments by modifying VLAN configurations or SDN policies | High | BR-R01 |
| FR-K012 | The Network Striker shall null-route DNS for known malicious domains via DNS sinkholing | High | BR-R01 |
| FR-K013 | The Network Striker shall terminate active connections to/from specified endpoints | High | BR-R01 |

### 5.3 Endpoint Striker

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-K020 | The Endpoint Striker shall terminate malicious processes by PID or process name | Critical | BR-R01 |
| FR-K021 | The Endpoint Striker shall quarantine files by moving them to an isolated directory with restricted permissions | High | BR-R01 |
| FR-K022 | The Endpoint Striker shall disable compromised user accounts via the system's identity provider (LDAP, AD, cloud IAM) | High | BR-R01 |
| FR-K023 | The Endpoint Striker shall force credential rotation for compromised accounts | High | BR-R01 |
| FR-K024 | The Endpoint Striker shall initiate endpoint isolation (disable network interfaces except management VLAN) | High | BR-R01 |

### 5.4 Cloud Striker

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-K030 | The Cloud Striker shall revoke compromised IAM credentials (access keys, tokens) | Critical | BR-R01 |
| FR-K031 | The Cloud Striker shall modify security group rules to restrict access to compromised resources | High | BR-R01 |
| FR-K032 | The Cloud Striker shall snapshot compromised instances for forensic analysis before termination | High | FR-K007 |
| FR-K033 | The Cloud Striker shall isolate compromised cloud resources by moving them to a quarantine VPC/resource group | High | BR-R01 |

### 5.5 Forensic Collector

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-K040 | The Forensic Collector shall capture memory dumps from specified endpoints | High | FR-K007 |
| FR-K041 | The Forensic Collector shall capture disk images or targeted file collections from specified endpoints | High | FR-K007 |
| FR-K042 | The Forensic Collector shall collect and preserve network packet captures (PCAP) for specified timeframes | High | FR-K007 |
| FR-K043 | The Forensic Collector shall store all evidence with cryptographic integrity verification (SHA-256 hashes) and chain-of-custody metadata | Critical | BR-O05 |

---

## 6. Functional Requirements — Dashboard & API

### 6.1 Dashboard

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-D001 | The dashboard shall display a real-time threat map showing active alerts, incidents, and affected assets | Critical | BR-O01 |
| FR-D002 | The dashboard shall provide alert triage workflows (acknowledge, investigate, escalate, dismiss) | Critical | BR-R02 |
| FR-D003 | The dashboard shall display agent health status for all Sentinels and Strikers | High | FR-C030 |
| FR-D004 | The dashboard shall provide incident timeline views showing event correlation, decisions, and response actions | High | BR-O05 |
| FR-D005 | The dashboard shall support role-based views (Analyst, Operator, Administrator, Auditor) | High | BR-O03 |
| FR-D006 | The dashboard shall provide search and filter capabilities across events, alerts, and incidents | High | BR-O04 |
| FR-D007 | The dashboard shall support configurable notification rules (email, webhook, Slack, PagerDuty) | High | FR-C023 |
| FR-D008 | The dashboard shall provide playbook management UI (create, edit, enable/disable, test) | High | BR-R03 |

### 6.2 REST API

| ID | Requirement | Priority | Traces To |
|----|-------------|----------|-----------|
| FR-A001 | The API shall expose all Core functionality via a versioned REST API (v1) | Critical | BR-O04 |
| FR-A002 | The API shall use JSON as the primary serialization format | Critical | BR-O04 |
| FR-A003 | The API shall require authentication via API keys or OAuth 2.0 bearer tokens | Critical | — |
| FR-A004 | The API shall enforce RBAC based on the authenticated user's role | Critical | — |
| FR-A005 | The API shall support pagination, filtering, and sorting on all list endpoints | High | BR-O04 |
| FR-A006 | The API shall provide webhook registration for event-driven integrations | High | BR-O04 |
| FR-A007 | The API shall expose OpenAPI 3.1 specification at `/api/v1/openapi.json` | High | BR-O04 |
| FR-A008 | The API shall rate-limit requests per authenticated identity (configurable, default: 1000 req/min) | High | — |

---

## 7. Non-Functional Requirements

### 7.1 Performance

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-P01 | Event ingestion throughput | >= 10,000 events/sec on reference hardware |
| NFR-P02 | Alert generation latency (event to alert) | < 5 seconds (p99) |
| NFR-P03 | Decision engine latency (alert to verdict) | < 3 seconds (p99) |
| NFR-P04 | Striker action dispatch latency (verdict to action start) | < 2 seconds (p99) |
| NFR-P05 | Dashboard page load time | < 2 seconds (p95) |
| NFR-P06 | API response time for read endpoints | < 200ms (p95) |
| NFR-P07 | Sentinel endpoint overhead | < 5% CPU, < 256 MB RAM |

### 7.2 Scalability

| ID | Requirement |
|----|-------------|
| NFR-S01 | The Core shall support horizontal scaling behind a load balancer |
| NFR-S02 | Sentinels and Strikers shall scale independently based on monitored scope |
| NFR-S03 | The system shall support monitoring up to 10,000 endpoints with a single Core cluster |
| NFR-S04 | The message bus shall partition events by source domain for parallel processing |

### 7.3 Availability

| ID | Requirement |
|----|-------------|
| NFR-A01 | The Core shall maintain 99.9% uptime (< 8.76 hours downtime per year) |
| NFR-A02 | Sentinels shall continue local detection and event caching if Core is unreachable |
| NFR-A03 | The system shall support active-passive Core failover with < 30 second recovery |
| NFR-A04 | Database shall be configured for replication with automated failover |

### 7.4 Maintainability

| ID | Requirement |
|----|-------------|
| NFR-M01 | All components shall support zero-downtime rolling updates |
| NFR-M02 | Configuration changes shall be applied without service restart where possible |
| NFR-M03 | The system shall expose health check endpoints for monitoring (/healthz, /readyz) |
| NFR-M04 | Log output shall follow structured JSON format with configurable verbosity |

### 7.5 Portability

| ID | Requirement |
|----|-------------|
| NFR-PO01 | All server-side components shall run in OCI-compliant containers |
| NFR-PO02 | Endpoint Sentinels shall support Linux (kernel 5.4+), Windows (10/Server 2019+), macOS (12+) |
| NFR-PO03 | Cloud Sentinels/Strikers shall support AWS, Azure, and GCP |
| NFR-PO04 | The system shall have no hard dependency on specific cloud providers for core functionality |

---

## 8. External Interface Requirements

### 8.1 Inbound Integrations (Data Sources)

| Interface | Protocol | Format | Description |
|-----------|----------|--------|-------------|
| Syslog | UDP/TCP 514, TLS 6514 | RFC 5424, CEF | Log ingestion from network devices, servers |
| STIX/TAXII | HTTPS | STIX 2.1 JSON | Threat intelligence feed ingestion |
| Cloud APIs | HTTPS | JSON | AWS CloudTrail, Azure Activity, GCP Audit |
| NetFlow | UDP 2055/9996 | NetFlow v9, IPFIX | Network flow data |
| Webhook Receiver | HTTPS | JSON | Generic event ingestion from external tools |

### 8.2 Outbound Integrations (Actions & Notifications)

| Interface | Protocol | Format | Description |
|-----------|----------|--------|-------------|
| Webhook | HTTPS | JSON | Event notifications to external systems |
| Slack | HTTPS | Slack API | Alert notifications and interactive responses |
| Email | SMTP/SMTPS | MIME | Alert notifications |
| PagerDuty | HTTPS | PagerDuty Events API v2 | Incident escalation |
| Ticketing | HTTPS | JSON | JIRA, ServiceNow integration for incident tracking |
| Firewall APIs | Varies | Vendor-specific | Rule push for network Striker actions |
| Cloud APIs | HTTPS | JSON | AWS/Azure/GCP management actions |

### 8.3 Inter-Agent Communication

| Interface | Protocol | Format | Description |
|-----------|----------|--------|-------------|
| Agent ↔ Core | NATS/Kafka over mTLS | Protobuf | Primary event and command channel |
| Agent → Core Heartbeat | NATS/Kafka over mTLS | Protobuf | Health and status reporting |
| Core → Agent Config | NATS/Kafka over mTLS | Protobuf | Configuration distribution |

---

## 9. Data Requirements

### 9.1 Data Model Overview

#### 9.1.1 Event

| Field | Type | Description |
|-------|------|-------------|
| event_id | UUID | Unique event identifier |
| timestamp | ISO 8601 | Event occurrence time |
| sentinel_id | UUID | Reporting Sentinel |
| event_class | Enum | OCSF event class (network, endpoint, cloud, application) |
| severity | Enum | Informational, Low, Medium, High, Critical |
| raw_data | JSON | Original event data |
| enrichments | JSON | Added context (asset info, threat intel matches) |
| mitre_techniques | Array[String] | Mapped MITRE ATT&CK technique IDs |

#### 9.1.2 Alert

| Field | Type | Description |
|-------|------|-------------|
| alert_id | UUID | Unique alert identifier |
| created_at | ISO 8601 | Alert creation time |
| event_ids | Array[UUID] | Contributing events |
| threat_score | Integer (0-100) | Composite threat score |
| severity | Enum | Computed severity level |
| status | Enum | new, acknowledged, investigating, resolved, dismissed |
| verdict | Enum | auto_respond, escalate, dismiss, pending |
| affected_assets | Array[Asset] | Impacted infrastructure assets |

#### 9.1.3 Incident

| Field | Type | Description |
|-------|------|-------------|
| incident_id | UUID | Unique incident identifier |
| created_at | ISO 8601 | Incident creation time |
| alert_ids | Array[UUID] | Contributing alerts |
| status | Enum | open, contained, eradicated, recovered, closed |
| assigned_to | String | Responsible operator |
| actions | Array[Action] | Response actions taken |
| timeline | Array[TimelineEntry] | Chronological event/action log |

#### 9.1.4 Action

| Field | Type | Description |
|-------|------|-------------|
| action_id | UUID | Unique action identifier |
| incident_id | UUID | Parent incident |
| striker_id | UUID | Executing Striker |
| action_type | Enum | block_ip, kill_process, isolate_host, revoke_creds, etc. |
| parameters | JSON | Action-specific parameters |
| status | Enum | queued, executing, succeeded, failed, rolled_back |
| initiated_by | Enum | auto (decision engine) or manual (operator username) |
| evidence | JSON | Pre-action forensic captures |

### 9.2 Data Retention

| Data Type | Default Retention | Storage |
|-----------|-------------------|---------|
| Raw Events | 90 days hot, 1 year cold | TimescaleDB / S3 |
| Alerts | 2 years | PostgreSQL |
| Incidents | 7 years | PostgreSQL |
| Audit Logs | 7 years | PostgreSQL + archival |
| Forensic Evidence | 1 year | Object storage (S3/MinIO) |
| Agent Configuration | Indefinite | PostgreSQL + Git |

---

## 10. Security Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| SR-01 | All inter-agent communication shall use mutual TLS (mTLS) with certificate rotation | Critical |
| SR-02 | All API endpoints shall require authentication (API key or OAuth 2.0) | Critical |
| SR-03 | All secrets (API keys, certificates, credentials) shall be stored in a secrets manager (HashiCorp Vault, Kubernetes Secrets with encryption) | Critical |
| SR-04 | The Core shall enforce RBAC with least-privilege defaults | Critical |
| SR-05 | Agent binaries shall be signed and verified on deployment | High |
| SR-06 | The Core shall implement tamper detection for its own configuration and binaries | High |
| SR-07 | All database connections shall use TLS encryption | Critical |
| SR-08 | Passwords and credentials shall never appear in logs or API responses | Critical |
| SR-09 | The system shall support integration with external authentication providers (LDAP, SAML, OIDC) | High |
| SR-10 | Rate limiting shall be enforced on all public-facing endpoints | High |
| SR-11 | Striker actions shall require cryptographic authorization tokens from the Core (prevent rogue action execution) | Critical |
| SR-12 | The system shall undergo regular dependency vulnerability scanning (automated in CI) | High |

---

## 11. Appendices

### 11.1 Requirement Traceability Matrix

All functional requirements (FR-*) trace to business requirements (BR-*) as documented in the "Traces To" column of each requirements table.

### 11.2 Event Schema Reference

The N7 event schema extends OCSF v1.1 with N7-specific extensions. The full schema will be maintained as a separate JSON Schema document at `schemas/n7-event-schema.json`.

### 11.3 MITRE ATT&CK Coverage Matrix

N7 aims to provide detection coverage for the following ATT&CK tactics in the initial release:

- Initial Access (TA0001)
- Execution (TA0002)
- Persistence (TA0003)
- Privilege Escalation (TA0004)
- Defense Evasion (TA0005)
- Credential Access (TA0006)
- Discovery (TA0007)
- Lateral Movement (TA0008)
- Command and Control (TA0011)
- Exfiltration (TA0010)

Specific technique coverage will be documented in a living matrix at `docs/mitre-coverage.md`.
