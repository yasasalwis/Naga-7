# Naga-7 (N7) — User Manual

**Version:** 1.0.0
**Date:** 2026-02-17
**Status:** Draft
**Classification:** Open Source — Public

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Installation](#2-installation)
3. [Initial Configuration](#3-initial-configuration)
4. [Dashboard Guide](#4-dashboard-guide)
5. [Sentinel Management](#5-sentinel-management)
6. [Striker Management](#6-striker-management)
7. [Detection Rules](#7-detection-rules)
8. [Escalation Policies](#8-escalation-policies)
9. [Playbooks](#9-playbooks)
10. [Incident Response Workflows](#10-incident-response-workflows)
11. [API Reference](#11-api-reference)
12. [Plugin Development](#12-plugin-development)
13. [Administration](#13-administration)
14. [Troubleshooting](#14-troubleshooting)
15. [FAQ](#15-faq)

---

## 1. Getting Started

### 1.1 What is Naga-7?

Naga-7 (N7) is an open-source, multi-level AI agent system for continuous security monitoring and automated threat
response. It consists of three core components:

- **N7-Core:** The central orchestrator that coordinates everything, processes events, makes decisions, and manages
  agents.
- **N7-Sentinels:** Monitoring agents deployed across your infrastructure to detect threats.
- **N7-Strikers:** Response agents that execute containment and remediation actions.

### 1.2 How N7 Works — The Lifecycle of a Threat

```
1. DETECT         2. CORRELATE       3. DECIDE          4. RESPOND
   Sentinel           Core              Core               Striker
   observes           links             evaluates          executes
   suspicious         related           and issues         containment
   activity           events            a verdict          action

   ┌─────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────┐
   │ Sentinel │───▶│ Correlate│───▶│   Decision   │───▶│ Striker  │
   │ detects  │    │ & Alert  │    │   Engine     │    │ contains │
   │ event    │    │          │    │              │    │ threat   │
   └─────────┘    └──────────┘    └──────────────┘    └──────────┘
                                         │
                                         ▼
                                  ┌──────────────┐
                                  │  OR: Escalate│
                                  │  to human    │
                                  │  operator    │
                                  └──────────────┘
```

### 1.3 Key Concepts

| Concept          | Description                                                                |
|------------------|----------------------------------------------------------------------------|
| **Event**        | A raw observation from a Sentinel (e.g., "Process `mimikatz.exe` started") |
| **Alert**        | One or more correlated events that indicate a potential threat             |
| **Incident**     | A confirmed threat requiring coordinated response                          |
| **Verdict**      | The Core's decision: `auto_respond`, `escalate`, or `dismiss`              |
| **Playbook**     | A sequence of Striker actions to execute for a specific threat type        |
| **Threat Score** | A 0-100 score indicating the severity and confidence of a threat           |
| **Blast Radius** | The scope of impact that an automated response could have                  |

### 1.4 User Roles

| Role              | Can Do                                                    | Cannot Do                                 |
|-------------------|-----------------------------------------------------------|-------------------------------------------|
| **Administrator** | Everything — deploy, configure, manage users              | —                                         |
| **Analyst**       | View dashboards, triage alerts, approve escalated actions | Modify system configuration, manage users |
| **Operator**      | Monitor active incidents, trigger manual responses        | Modify policies, manage users             |
| **Auditor**       | View audit logs and compliance reports                    | Modify anything                           |

---

## 2. Installation

### 2.1 Prerequisites

| Requirement      | Minimum                                 |
|------------------|-----------------------------------------|
| Docker or Podman | v24+                                    |
| Docker Compose   | v2.20+                                  |
| Available RAM    | 8 GB (small deployment)                 |
| Available Disk   | 50 GB (data storage)                    |
| Network          | Outbound HTTPS (for threat intel feeds) |

For Kubernetes deployments, see [Section 2.4](#24-kubernetes-deployment).

### 2.2 Quick Start (Docker Compose)

```bash
# Clone the repository
git clone https://github.com/naga-7/naga-7.git
cd naga-7

# Copy and edit the environment configuration
cp deploy/compose/.env.example deploy/compose/.env
# Edit .env with your settings (see Section 3 for configuration)

# Start all services
docker compose -f deploy/compose/docker-compose.yml up -d

# Verify all services are running
docker compose -f deploy/compose/docker-compose.yml ps

# Access the dashboard
# Open http://localhost:3000 in your browser
```

Expected output after startup:

```
NAME                    STATUS
n7-core                 running (healthy)
n7-dashboard            running (healthy)
n7-network-sentinel     running (healthy)
n7-endpoint-sentinel    running (healthy)
n7-network-striker      running (healthy)
n7-postgres             running (healthy)
n7-redis                running (healthy)
n7-nats                 running (healthy)
n7-minio                running (healthy)
```

### 2.3 Verify Installation

```bash
# Check Core health
curl http://localhost:8080/healthz
# Expected: {"status": "healthy", "version": "1.0.0"}

# Check agent registration
curl -H "Authorization: Bearer <your-api-key>" \
  http://localhost:8080/api/v1/agents
# Expected: List of registered Sentinels and Strikers
```

### 2.4 Kubernetes Deployment

```bash
# Add the N7 Helm repository
helm repo add naga7 https://charts.naga-7.io
helm repo update

# Install with default values
helm install n7 naga7/naga-7 \
  --namespace n7-system \
  --create-namespace

# Install with custom values
helm install n7 naga7/naga-7 \
  --namespace n7-system \
  --create-namespace \
  -f my-values.yaml

# Check deployment status
kubectl -n n7-system get pods
```

### 2.5 Standalone Sentinel Deployment (Remote Hosts)

For monitoring hosts outside the container environment:

```bash
# Download the Sentinel binary
curl -LO https://github.com/naga-7/naga-7/releases/latest/download/n7-sentinel-linux-amd64

# Make executable
chmod +x n7-sentinel-linux-amd64

# Configure
cat > /etc/n7/sentinel.yaml << 'EOF'
agent:
  type: endpoint
  zone: production
  core_url: nats://n7-core.example.com:4222
  tls:
    cert: /etc/n7/certs/sentinel.crt
    key: /etc/n7/certs/sentinel.key
    ca: /etc/n7/certs/ca.crt
EOF

# Run as a service (systemd)
sudo cp n7-sentinel-linux-amd64 /usr/local/bin/n7-sentinel
sudo cp deploy/systemd/n7-sentinel.service /etc/systemd/system/
sudo systemctl enable --now n7-sentinel
```

---

## 3. Initial Configuration

### 3.1 Core Configuration

The Core is configured via `config/core.yaml` or environment variables:

```yaml
# config/core.yaml
core:
  # Server settings
  api:
    host: 0.0.0.0
    port: 8080
    cors_origins: [ "http://localhost:3000" ]

  # Database
  database:
    url: postgresql+asyncpg://n7:password@postgres:5432/n7
    pool_size: 20

  # Message bus
  nats:
    url: nats://nats:4222
    tls:
      cert: /etc/n7/certs/core.crt
      key: /etc/n7/certs/core.key
      ca: /etc/n7/certs/ca.crt

  # Redis
  redis:
    url: redis://redis:6379/0

  # Event pipeline
  pipeline:
    dedup_window_seconds: 60
    batch_size: 100
    enrichment:
      asset_inventory: true
      geoip: true
      threat_intel: true

  # Decision engine
  decision:
    dry_run: false  # Set to true to test without executing actions
    default_policy: default

  # Agent management
  agents:
    heartbeat_interval_seconds: 30
    unhealthy_after_missed: 3
```

### 3.2 Environment Variables

All YAML config values can be overridden with environment variables using the prefix `N7_`:

```bash
N7_CORE_API_PORT=8080
N7_CORE_DATABASE_URL=postgresql+asyncpg://n7:password@postgres:5432/n7
N7_CORE_DECISION_DRY_RUN=true
N7_CORE_PIPELINE_DEDUP_WINDOW_SECONDS=120
```

### 3.3 First-Time Setup Wizard

On first launch, the dashboard displays a setup wizard:

1. **Create Admin Account:** Set the initial administrator username and password.
2. **Configure Notifications:** Set up at least one notification channel (email, Slack, or webhook).
3. **Review Default Policy:** Review and adjust the default escalation policy.
4. **Enable Sentinels:** Verify that deployed Sentinels have registered successfully.
5. **Run Health Check:** The wizard runs a system-wide health check.

---

## 4. Dashboard Guide

### 4.1 Overview Page

The main dashboard shows:

```
┌──────────────────────────────────────────────────────────────┐
│  NAGA-7 DASHBOARD                            [Admin ▼] [⚙]  │
├──────┬───────────────────────────────────────────────────────┤
│      │  ┌─────────────────────────────────────────────────┐  │
│  NAV │  │  THREAT MAP                                     │  │
│      │  │  Active alerts shown on infrastructure topology │  │
│ Over │  │                                                 │  │
│ view │  └─────────────────────────────────────────────────┘  │
│      │                                                       │
│Alerts│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────────┐ │
│      │  │Critical│ │ High   │ │ Medium │ │   Events/sec   │ │
│Incid.│  │   2    │ │   7    │ │   23   │ │    4,521       │ │
│      │  └────────┘ └────────┘ └────────┘ └────────────────┘ │
│Agents│                                                       │
│      │  ┌─────────────────────────────────────────────────┐  │
│Policy│  │  RECENT ALERTS                     [View All →] │  │
│      │  │  ● CRIT  Lateral movement detected    2m ago   │  │
│Audit │  │  ● HIGH  Brute force on SSH           5m ago   │  │
│      │  │  ● MED   Suspicious PowerShell        12m ago  │  │
│Config│  │  ● MED   Public S3 bucket detected    18m ago  │  │
│      │  └─────────────────────────────────────────────────┘  │
└──────┴───────────────────────────────────────────────────────┘
```

### 4.2 Alerts Page

The Alerts page lists all active alerts with filtering and triage capabilities:

**Filtering:**

- By severity: Critical, High, Medium, Low, Informational
- By status: New, Acknowledged, Investigating, Resolved, Dismissed
- By time range: Last hour, 24h, 7 days, custom
- By source Sentinel type: Network, Endpoint, Cloud, Log
- By affected asset: hostname, IP, or asset group

**Triage Actions:**

- **Acknowledge:** Mark as seen, assigned to you.
- **Investigate:** Open investigation view with full event timeline.
- **Escalate:** Manually escalate to a higher-priority team.
- **Dismiss:** Mark as false positive (requires reason).
- **Auto-Respond:** Manually trigger a playbook for this alert.

### 4.3 Incidents Page

Active incidents with their full lifecycle:

- **Timeline View:** Chronological sequence of events, decisions, and actions.
- **Affected Assets:** Visual map of impacted infrastructure.
- **Actions Taken:** List of Striker actions with status (succeeded, failed, rolled back).
- **Rollback Controls:** One-click rollback for any automated action.

### 4.4 Agents Page

Monitor all deployed Sentinels and Strikers:

| Column         | Description                                        |
|----------------|----------------------------------------------------|
| Agent ID       | Unique identifier                                  |
| Type           | Sentinel or Striker                                |
| Subtype        | network, endpoint, cloud, log, forensic            |
| Status         | Active (green), Unhealthy (yellow), Retired (gray) |
| Zone           | Deployment zone                                    |
| Last Heartbeat | Time since last heartbeat                          |
| CPU / Memory   | Current resource usage                             |
| Config Version | Applied configuration version                      |

### 4.5 Real-Time Notifications

Configure notification rules under **Settings > Notifications:**

```yaml
# Example notification rule
notification:
  name: "Critical alerts to Slack"
  trigger:
    alert_severity: [ critical ]
  channels:
    - type: slack
      webhook_url: https://hooks.slack.com/services/xxx/yyy/zzz
      channel: "#security-alerts"
    - type: email
      recipients: [ "soc@company.com" ]
```

---

## 5. Sentinel Management

### 5.1 Deploying a New Sentinel

**Via Dashboard:**

1. Navigate to **Agents > Deploy New Agent**.
2. Select Sentinel type (Network, Endpoint, Cloud, Log).
3. Configure monitoring scope and zone.
4. Download the generated configuration and certificate bundle.
5. Deploy the Sentinel to the target host/environment.

**Via CLI:**

```bash
# Generate agent credentials
n7-cli agent create \
  --type sentinel \
  --subtype endpoint \
  --zone production \
  --output /tmp/sentinel-config/

# Deploy to target host
scp -r /tmp/sentinel-config/ target-host:/etc/n7/
ssh target-host 'systemctl start n7-sentinel'
```

### 5.2 Sentinel Configuration

Each Sentinel type has specific configuration:

**Endpoint Sentinel:**

```yaml
sentinel:
  type: endpoint
  probes:
    process_monitor:
      enabled: true
      track_command_line: true
      track_network_per_process: true
    file_integrity:
      enabled: true
      watched_paths:
        - /etc/
        - /usr/bin/
        - /usr/sbin/
        - /home/*/.ssh/
      exclude_patterns:
        - "*.log"
        - "*.tmp"
    auth_monitor:
      enabled: true
      sources: [ pam, sshd, sudo ]
    yara_scanner:
      enabled: true
      rules_path: /etc/n7/yara-rules/
      scan_paths: [ /tmp, /var/tmp, /dev/shm ]
      scan_interval_seconds: 300

  resource_limits:
    max_cpu_percent: 5
    max_memory_mb: 256
```

**Network Sentinel:**

```yaml
sentinel:
  type: network
  probes:
    packet_capture:
      enabled: true
      interface: eth0
      bpf_filter: "not port 4222"  # Exclude NATS traffic
      mode: af_packet  # or pcap
    flow_collector:
      enabled: true
      protocols: [ netflow_v9, ipfix ]
      listen_port: 2055
    dns_monitor:
      enabled: true
      interface: eth0
  detection:
    signatures:
      enabled: true
      rules_path: /etc/n7/suricata-rules/
    anomaly:
      enabled: true
      baseline_period_days: 7
```

**Cloud Sentinel (AWS):**

```yaml
sentinel:
  type: cloud
  provider: aws
  regions: [ us-east-1, us-west-2 ]
  probes:
    cloudtrail:
      enabled: true
      trail_name: management-events
    config_monitor:
      enabled: true
      check_interval_seconds: 300
      checks:
        - public_s3_buckets
        - open_security_groups
        - unencrypted_volumes
        - iam_policy_changes
  credentials:
    method: iam_role  # or access_key
```

### 5.3 Custom Detection Rules

Add custom detection rules via the dashboard or by placing YAML files in the rules directory:

```yaml
# /etc/n7/rules/custom/detect-cryptominer.yaml
detection:
  id: "custom-001"
  name: "Cryptominer Process Detection"
  description: "Detects known cryptomining processes"
  severity: medium
  mitre: [ T1496 ]

  match:
    event_class: process_creation
    conditions:
      - field: process.name
        operator: in
        value: [ "xmrig", "minerd", "cpuminer", "bfgminer" ]

  # OR match by CPU characteristics
  alternate_match:
    event_class: process_resource
    conditions:
      - field: process.cpu_percent
        operator: gte
        value: 80
      - field: process.duration_seconds
        operator: gte
        value: 300
```

### 5.4 Monitoring Sentinel Health

**Dashboard:** The Agents page shows real-time health for all Sentinels.

**CLI:**

```bash
# List all Sentinels
n7-cli agents list --type sentinel

# Check specific Sentinel
n7-cli agents status <agent-id>

# View Sentinel logs
n7-cli agents logs <agent-id> --tail 100
```

**Alerts:** The Core automatically generates alerts when:

- A Sentinel misses 3+ heartbeats (configurable).
- A Sentinel reports resource usage above thresholds.
- A Sentinel's binary hash doesn't match the expected value.

---

## 6. Striker Management

### 6.1 Deploying Strikers

Strikers are deployed similarly to Sentinels but require additional permissions for response actions:

```bash
# Generate Striker credentials with action capabilities
n7-cli agent create \
  --type striker \
  --subtype network \
  --zone production \
  --capabilities "block_ip,isolate_segment,sinkhole_dns" \
  --output /tmp/striker-config/
```

### 6.2 Striker Capabilities

Each Striker declares what actions it can perform. The Core only dispatches actions to Strikers with matching
capabilities:

| Striker Type | Available Capabilities                                                                                                                 |
|--------------|----------------------------------------------------------------------------------------------------------------------------------------|
| **Network**  | `block_ip`, `unblock_ip`, `isolate_segment`, `restore_segment`, `sinkhole_dns`, `restore_dns`, `kill_connection`                       |
| **Endpoint** | `kill_process`, `quarantine_file`, `restore_file`, `disable_user`, `enable_user`, `rotate_credentials`, `isolate_host`, `restore_host` |
| **Cloud**    | `revoke_credentials`, `restrict_security_group`, `restore_security_group`, `snapshot_instance`, `isolate_resource`, `restore_resource` |
| **Forensic** | `capture_memory`, `capture_disk`, `capture_pcap`, `collect_artifacts`                                                                  |

### 6.3 Manual Action Execution

Operators can trigger Striker actions manually via the dashboard or API:

**Dashboard:**

1. Navigate to the incident or alert.
2. Click **Take Action**.
3. Select the action type and target.
4. Review the action details.
5. Confirm execution.

**API:**

```bash
curl -X POST http://localhost:8080/api/v1/actions \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "inc-123",
    "action_type": "block_ip",
    "parameters": {
      "ip": "203.0.113.42",
      "direction": "both",
      "duration": "24h"
    },
    "reason": "Confirmed C2 traffic from this IP"
  }'
```

### 6.4 Rollback Actions

Every Striker action can be rolled back:

**Dashboard:** Navigate to the incident > Actions tab > Click **Rollback** next to the action.

**API:**

```bash
curl -X POST http://localhost:8080/api/v1/actions/<action-id>/rollback \
  -H "Authorization: Bearer <api-key>" \
  -d '{"reason": "False positive confirmed"}'
```

**Automatic Rollback:** Playbooks can be configured to auto-rollback if a subsequent step fails:

```yaml
steps:
  - id: block_ip
    action: block_ip
    on_failure: abort
    rollback: unblock_ip  # Auto-rollback if later steps fail
```

---

## 7. Detection Rules

### 7.1 Rule Format

Detection rules use a YAML format with these sections:

```yaml
detection:
  id: "unique-rule-id"       # Must be unique across all rules
  name: "Human-readable name"
  description: "What this rule detects"
  severity: critical|high|medium|low|informational
  enabled: true               # Can be disabled without deletion
  mitre: [ T1059.001 ]          # MITRE ATT&CK technique IDs

  match:
    event_class: process_creation|network_connection|file_change|authentication|...
    conditions:
      - field: dotted.path.to.field
        operator: eq|neq|in|not_in|contains|regex|gte|lte|gt|lt|exists
        value: <comparison value>

  exceptions: # Optional: known-good patterns to skip
    - field: process.name
      operator: eq
      value: "known-good-tool.exe"

  metadata: # Optional: additional context
    author: "your-name"
    created: "2026-02-17"
    references:
      - "https://attack.mitre.org/techniques/T1059/001/"
```

### 7.2 Managing Rules

**Via Dashboard:**
Navigate to **Configuration > Detection Rules** to create, edit, enable/disable, and test rules.

**Via File System:**
Place rule files in `/etc/n7/rules/` (or the configured path). Sentinels hot-reload rules when files change.

**Via API:**

```bash
# List rules
curl http://localhost:8080/api/v1/rules

# Create rule
curl -X POST http://localhost:8080/api/v1/rules \
  -H "Authorization: Bearer <api-key>" \
  -d @my-rule.yaml

# Test rule against historical events
curl -X POST http://localhost:8080/api/v1/rules/test \
  -H "Authorization: Bearer <api-key>" \
  -d '{
    "rule": "<rule-yaml>",
    "time_range": "24h"
  }'
```

### 7.3 Rule Testing

Before deploying a rule to production, test it:

1. **Backtest:** Run the rule against historical events to see what it would have matched.
2. **Dry-Run Deploy:** Deploy the rule in dry-run mode (detects but doesn't alert).
3. **Tune Thresholds:** Adjust conditions based on backtest results to minimize false positives.
4. **Enable:** Once satisfied, enable the rule for production alerting.

---

## 8. Escalation Policies

### 8.1 Policy Structure

Escalation policies define how the Decision Engine handles alerts at different severity levels:

```yaml
escalation_policy:
  name: "production"
  description: "Policy for production environment"

  rules:
    # Rules are evaluated in order — first match wins
    - severity: [ critical, high ]
      action: escalate
      notify: [ slack, pagerduty, email ]
      message: "Critical/High threat detected — human review required"

    - severity: [ medium ]
      confidence_threshold: 0.85
      action: auto_respond
      playbook: "contain-medium"

    - severity: [ medium ]
      confidence_threshold: 0.0
      action: escalate
      notify: [ slack ]

    - severity: [ low ]
      confidence_threshold: 0.70
      action: auto_respond
      playbook: "contain-low"

    - severity: [ low, informational ]
      action: dismiss

  # Safety limits for automated responses
  blast_radius_limits:
    max_hosts_per_action: 10     # Don't auto-contain more than 10 hosts
    max_actions_per_hour: 50     # Rate limit automated actions
    cool_down_minutes: 15        # Wait between repeated actions on same asset

  # Override: force escalation during maintenance windows
  maintenance_windows:
    - name: "Weekend maintenance"
      schedule: "0 22 * * 5 - 0 6 * * 1"  # Friday 10pm to Monday 6am
      override_action: escalate
```

### 8.2 Managing Policies

- **Dashboard:** **Configuration > Escalation Policies**
- **Multiple Policies:** You can create different policies for different zones (e.g., "production" vs. "development").
- **Policy Assignment:** Assign policies to agent zones via the configuration.

### 8.3 Dry-Run Mode

To test a policy without executing responses:

```yaml
# In core.yaml
core:
  decision:
    dry_run: true
```

In dry-run mode:

- The Decision Engine still evaluates alerts and produces verdicts.
- Verdicts are logged with `[DRY-RUN]` prefix.
- No actions are dispatched to Strikers.
- Dashboard shows what **would have happened**.

---

## 9. Playbooks

### 9.1 Playbook Structure

Playbooks define automated response sequences:

```yaml
playbook:
  id: "pb-isolate-compromised-host"
  name: "Isolate Compromised Host"
  description: "Collects forensic evidence then isolates a compromised host"
  version: 2
  max_duration: 30m

  parameters:
    - name: target_host
      type: hostname
      required: true
    - name: target_ip
      type: ip_address
      required: true
    - name: incident_id
      type: string
      required: true

  steps:
    - id: snapshot
      name: "Capture forensic evidence"
      action: forensic_capture
      params:
        target: "{{ target_host }}"
        capture_types: [ process_list, network_connections, open_files ]
      on_failure: continue
      timeout: 5m

    - id: block_external
      name: "Block external communication"
      action: block_ip
      params:
        ip: "{{ target_ip }}"
        direction: outbound
        duration: 48h
      on_failure: abort
      rollback: unblock_ip

    - id: isolate
      name: "Isolate host from network"
      action: isolate_host
      params:
        target: "{{ target_host }}"
        allow_management: true
      on_failure: abort
      rollback: restore_host

    - id: notify_team
      name: "Notify incident response team"
      action: notify
      params:
        channels: [ slack, pagerduty ]
        severity: high
        message: |
          Host {{ target_host }} ({{ target_ip }}) has been isolated.
          Incident: {{ incident_id }}
          Forensic evidence captured. Ready for investigation.
      on_failure: continue
```

### 9.2 Creating Playbooks

**Via Dashboard:**

1. Navigate to **Configuration > Playbooks**.
2. Click **Create New Playbook**.
3. Use the visual editor to add steps, set parameters, and configure failure handling.
4. Save and test the playbook.

**Via YAML File:**
Place playbook files in `/etc/n7/playbooks/` or upload via the API.

### 9.3 Testing Playbooks

**Dry-Run Execution:**

```bash
n7-cli playbook test pb-isolate-compromised-host \
  --param target_host=test-server-01 \
  --param target_ip=10.0.1.100 \
  --param incident_id=test-001 \
  --dry-run
```

This shows exactly what actions would execute without actually performing them.

---

## 10. Incident Response Workflows

### 10.1 Automated Response (Low/Medium Severity)

```
Alert Created
     │
     ▼
Decision Engine evaluates
     │
     ├── Confidence >= threshold
     │        │
     │        ▼
     │   Auto-respond verdict
     │        │
     │        ▼
     │   Playbook dispatched to Striker
     │        │
     │        ▼
     │   Striker executes containment
     │        │
     │        ▼
     │   Status reported to Core
     │        │
     │        ▼
     │   Dashboard updated + notification sent
     │        │
     │        ▼
     │   Analyst reviews (can rollback if false positive)
     │
     └── Confidence < threshold
              │
              ▼
         Escalated to human (see 10.2)
```

### 10.2 Human-Escalated Response (High/Critical Severity)

```
Alert Created
     │
     ▼
Decision Engine → Escalate verdict
     │
     ▼
Notification sent (Slack, PagerDuty, email)
     │
     ▼
Analyst opens incident in dashboard
     │
     ▼
Analyst investigates:
  - Reviews event timeline
  - Examines correlated events
  - Checks threat intelligence context
  - Reviews MITRE ATT&CK mapping
     │
     ▼
Analyst decides:
  ├── Confirmed threat → Select playbook → Execute
  ├── Need more info → Request additional Sentinel scans
  └── False positive → Dismiss + tune detection rule
```

### 10.3 Incident Lifecycle

| Status         | Description                               | Transitions To                          |
|----------------|-------------------------------------------|-----------------------------------------|
| **Open**       | Incident created, awaiting response       | Contained, Closed                       |
| **Contained**  | Threat contained but not fully remediated | Eradicated, Open (if containment fails) |
| **Eradicated** | Root cause removed                        | Recovered                               |
| **Recovered**  | Systems restored to normal operation      | Closed                                  |
| **Closed**     | Incident fully resolved                   | — (can be reopened)                     |

### 10.4 Post-Incident Review

After closing an incident:

1. **Timeline Export:** Export the full incident timeline for reporting.
2. **Audit Trail:** All events, decisions, and actions are preserved.
3. **Rule Tuning:** If the incident revealed detection gaps or false positives, update rules.
4. **Playbook Update:** If the response sequence could be improved, update playbooks.
5. **Metrics:** MTTD and MTTR metrics are automatically calculated.

---

## 11. API Reference

### 11.1 Authentication

All API requests require authentication:

```bash
# API Key (header)
curl -H "Authorization: Bearer n7_api_xxxxxxxxxx" http://localhost:8080/api/v1/...

# API Key (query parameter — not recommended for production)
curl http://localhost:8080/api/v1/...?api_key=n7_api_xxxxxxxxxx
```

### 11.2 Common Endpoints

| Method | Endpoint                         | Description                         |
|--------|----------------------------------|-------------------------------------|
| GET    | `/api/v1/alerts`                 | List alerts (paginated, filterable) |
| GET    | `/api/v1/alerts/{id}`            | Get alert details                   |
| PATCH  | `/api/v1/alerts/{id}`            | Update alert status                 |
| GET    | `/api/v1/incidents`              | List incidents                      |
| GET    | `/api/v1/incidents/{id}`         | Get incident details                |
| POST   | `/api/v1/incidents/{id}/actions` | Trigger manual action               |
| GET    | `/api/v1/agents`                 | List all agents                     |
| GET    | `/api/v1/agents/{id}`            | Get agent details                   |
| POST   | `/api/v1/agents/{id}/config`     | Push config to agent                |
| GET    | `/api/v1/events`                 | Query events (time-series)          |
| GET    | `/api/v1/rules`                  | List detection rules                |
| POST   | `/api/v1/rules`                  | Create detection rule               |
| PUT    | `/api/v1/rules/{id}`             | Update detection rule               |
| DELETE | `/api/v1/rules/{id}`             | Delete detection rule               |
| GET    | `/api/v1/playbooks`              | List playbooks                      |
| POST   | `/api/v1/playbooks`              | Create playbook                     |
| GET    | `/api/v1/audit`                  | Query audit log                     |
| POST   | `/api/v1/actions/{id}/rollback`  | Rollback an action                  |
| GET    | `/healthz`                       | Health check                        |
| GET    | `/readyz`                        | Readiness check                     |
| GET    | `/api/v1/openapi.json`           | OpenAPI specification               |

### 11.3 Webhook Integration

Register webhooks to receive real-time notifications:

```bash
curl -X POST http://localhost:8080/api/v1/webhooks \
  -H "Authorization: Bearer <api-key>" \
  -d '{
    "url": "https://your-service.com/n7-webhook",
    "events": ["alert.created", "incident.created", "action.completed"],
    "secret": "webhook-signing-secret"
  }'
```

Webhook payloads are signed with HMAC-SHA256. Verify the signature:

```python
import hmac, hashlib


def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

---

## 12. Plugin Development

### 12.1 Creating a Custom Sentinel Probe

```python
# my_custom_probe/probe.py
from n7.sentinel.framework import Probe, RawObservation


class MyCustomProbe(Probe):
    """Monitors a custom data source."""

    probe_type = "my_custom_source"

    async def initialize(self, config: dict) -> None:
        self.source_url = config["source_url"]
        self.poll_interval = config.get("poll_interval", 30)

    async def observe(self):
        while True:
            data = await self._fetch_data()
            for item in data:
                yield RawObservation(
                    source=self.probe_type,
                    data=item,
                    timestamp=datetime.utcnow(),
                )
            await asyncio.sleep(self.poll_interval)

    async def shutdown(self) -> None:
        pass  # Clean up resources

    async def _fetch_data(self) -> list[dict]:
        # Your custom data collection logic
        ...
```

Register via `pyproject.toml`:

```toml
[project.entry-points."n7.sentinel.probes"]
my_custom_probe = "my_custom_probe.probe:MyCustomProbe"
```

### 12.2 Creating a Custom Striker Action

```python
# my_custom_action/action.py
from n7.striker.framework import StrikerAction, ActionResult, RollbackInfo


class MyCustomAction(StrikerAction):
    """Performs a custom response action."""

    action_type = "my_custom_action"

    async def pre_flight(self, params: dict) -> bool:
        """Validate that the action can be performed."""
        # Return True if ready, False to abort
        return True

    async def execute(self, params: dict) -> ActionResult:
        """Execute the response action."""
        # Capture pre-action state for rollback
        pre_state = await self._capture_state(params)

        # Perform the action
        result = await self._do_action(params)

        return ActionResult(
            success=True,
            details={"result": result},
            rollback=RollbackInfo(
                action="my_custom_undo",
                params=pre_state,
            ),
        )

    async def rollback(self, params: dict) -> ActionResult:
        """Undo the action."""
        await self._undo_action(params)
        return ActionResult(success=True, details={"rolled_back": True})
```

### 12.3 Plugin Testing

```python
# tests/test_my_custom_probe.py
import pytest
from my_custom_probe.probe import MyCustomProbe


@pytest.mark.asyncio
async def test_probe_initialization():
    probe = MyCustomProbe()
    await probe.initialize({"source_url": "http://test"})
    assert probe.source_url == "http://test"


@pytest.mark.asyncio
async def test_probe_observation():
    probe = MyCustomProbe()
    await probe.initialize({"source_url": "http://test"})
    observations = []
    async for obs in probe.observe():
        observations.append(obs)
        if len(observations) >= 5:
            break
    assert len(observations) == 5
```

---

## 13. Administration

### 13.1 User Management

**Create User:**

```bash
n7-cli users create \
  --username analyst01 \
  --role analyst \
  --email analyst01@company.com
```

**Roles:**

```bash
n7-cli users set-role analyst01 operator  # Change role
n7-cli users disable analyst01            # Disable account
n7-cli users list                         # List all users
```

### 13.2 Certificate Management

**Rotate Root CA (requires downtime):**

```bash
n7-cli certs rotate-ca \
  --new-ca /path/to/new-ca.crt \
  --new-key /path/to/new-ca.key \
  --transition-period 24h  # Both old and new CA trusted during transition
```

**Agent Certificate Renewal:** Happens automatically. Agents request new certificates before expiry.

### 13.3 Backup and Restore

**Database Backup:**

```bash
# Automated daily backup (configured in core.yaml)
core:
  backup:
    schedule: "0 2 * * *"  # Daily at 2 AM
    destination: s3://n7-backups/
    retention_days: 30

# Manual backup
n7-cli backup create --output /backups/n7-backup-$(date +%Y%m%d).sql
```

**Restore:**

```bash
n7-cli backup restore --input /backups/n7-backup-20260217.sql
```

### 13.4 Log Management

**View Core Logs:**

```bash
# Docker Compose
docker compose logs n7-core --tail 100 -f

# Kubernetes
kubectl -n n7-system logs deployment/n7-core -f

# Filter by level
docker compose logs n7-core | jq 'select(.level == "ERROR")'
```

**Log Levels:** Configurable per component:

```yaml
core:
  logging:
    level: INFO           # Global default
    overrides:
      decision_engine: DEBUG   # More detail for decision engine
      event_pipeline: WARNING  # Less noise from pipeline
```

### 13.5 Monitoring N7 Itself

N7 exposes Prometheus metrics at `/metrics`:

```bash
# Check Core metrics
curl http://localhost:8080/metrics

# Key metrics to monitor:
# n7_events_ingested_total        — Event volume
# n7_alerts_generated_total       — Alert rate
# n7_actions_completed_total      — Response activity
# n7_pipeline_latency_seconds     — Processing latency
# n7_agents_unhealthy             — Unhealthy agent count
```

**Recommended Alert Rules (for monitoring N7 with Prometheus/Alertmanager):**

```yaml
# Alert if event ingestion drops to zero for 5 minutes
- alert: N7EventIngestionStopped
  expr: rate(n7_events_ingested_total[5m]) == 0
  for: 5m
  labels: { severity: critical }

# Alert if agents are unhealthy
- alert: N7UnhealthyAgents
  expr: n7_agents_unhealthy > 0
  for: 2m
  labels: { severity: warning }

# Alert if pipeline latency exceeds SLA
- alert: N7HighPipelineLatency
  expr: histogram_quantile(0.99, n7_pipeline_latency_seconds_bucket) > 5
  for: 5m
  labels: { severity: warning }
```

---

## 14. Troubleshooting

### 14.1 Common Issues

#### Sentinel Not Appearing in Dashboard

**Symptoms:** Deployed Sentinel, but it doesn't appear in the Agents page.

**Check:**

1. Verify Sentinel can reach NATS: `n7-sentinel --check-connectivity`
2. Check Sentinel logs for TLS errors: `journalctl -u n7-sentinel`
3. Verify certificate is valid: `openssl x509 -in /etc/n7/certs/sentinel.crt -text`
4. Ensure the correct NATS URL is configured in `sentinel.yaml`

#### Events Not Flowing

**Symptoms:** Sentinel is active but no events appear in the dashboard.

**Check:**

1. Sentinel is generating events: Check Sentinel logs for `events emitted` messages.
2. NATS is receiving events: `nats sub "n7.events.>" --count 5`
3. Core is consuming events: Check Core logs for pipeline activity.
4. Detection rules are enabled: Verify at least one rule matches your event type.

#### Auto-Response Not Triggering

**Symptoms:** Alerts are created but no automated response occurs.

**Check:**

1. Dry-run mode is disabled: `N7_CORE_DECISION_DRY_RUN=false`
2. Escalation policy has auto-respond rules for the alert severity.
3. Confidence threshold is met.
4. Blast radius limits are not exceeded.
5. Cool-down is not active for the target asset.
6. An appropriate Striker is active and healthy.

#### High CPU on Monitored Host

**Symptoms:** Endpoint Sentinel consuming too much CPU.

**Fix:**

1. Reduce probe frequency in `sentinel.yaml`.
2. Narrow file integrity monitoring paths.
3. Reduce YARA scan frequency.
4. Lower the resource limit: `resource_limits.max_cpu_percent: 3`

### 14.2 Diagnostic Commands

```bash
# System health overview
n7-cli status

# Check all agent connectivity
n7-cli agents health-check

# Test NATS connectivity
n7-cli test nats

# Test database connectivity
n7-cli test database

# Validate configuration
n7-cli config validate

# Export diagnostic bundle (for bug reports)
n7-cli diagnostics export --output /tmp/n7-diag.tar.gz
```

### 14.3 Getting Help

- **Documentation:** You're reading it.
- **GitHub Issues:** Report bugs and request features.
- **Community Chat:** Join our Discord/Slack for community support.
- **Security Issues:** Report security vulnerabilities via responsible disclosure (see SECURITY.md).

---

## 15. FAQ

**Q: Will N7 replace my SIEM?**
A: No. N7 integrates with your existing SIEM. Sentinels can ingest events from your SIEM (via syslog, API), and N7
alerts can be forwarded to your SIEM. N7 adds the autonomous detection-and-response layer that SIEMs lack.

**Q: Is it safe to let N7 automatically respond to threats?**
A: N7 has multiple safety layers: configurable escalation policies, blast-radius limits, cool-down periods, dry-run
mode, and mandatory human escalation for critical threats. Start with dry-run mode, observe the decisions N7 would make,
tune your policies, then gradually enable auto-response for low/medium severity threats.

**Q: What happens if N7 makes a mistake?**
A: Every automated action can be rolled back. N7 captures pre-action state and provides one-click rollback via the
dashboard or API. The full reasoning for every decision is logged for review.

**Q: Can I use N7 without the AI/ML features?**
A: Yes. The anomaly detection (ML-based) is optional. You can run N7 with signature-based and rule-based detection only.
The decision engine uses configurable rules, not opaque ML models.

**Q: What about performance impact on production systems?**
A: Endpoint Sentinels are designed for < 5% CPU and < 256 MB RAM overhead. They use kernel-level instrumentation (eBPF
on Linux) to minimize impact. Resource limits are enforced and configurable.

**Q: How does N7 handle encrypted traffic?**
A: Network Sentinels analyze traffic metadata (flow data, DNS, TLS handshakes) rather than decrypting content. For
deeper inspection, integrate with a TLS inspection proxy that exports decrypted traffic to N7.

**Q: Can I write custom Sentinels and Strikers?**
A: Yes. N7's plugin system supports custom probes, detection rules, response actions, enrichers, and notification
channels. See [Section 12](#12-plugin-development).

**Q: What license is N7 under?**
A: Apache 2.0. You can use, modify, and distribute N7 freely, including in commercial products.
