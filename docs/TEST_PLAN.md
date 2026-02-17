# Naga-7 (N7) — Test Plan and Test Cases

**Version:** 1.0.0
**Date:** 2026-02-17
**Status:** Draft
**Classification:** Open Source — Public

---

## Table of Contents

1. [Test Strategy Overview](#1-test-strategy-overview)
2. [Test Environment](#2-test-environment)
3. [Unit Test Cases](#3-unit-test-cases)
4. [Integration Test Cases](#4-integration-test-cases)
5. [End-to-End Test Cases](#5-end-to-end-test-cases)
6. [Security Test Cases](#6-security-test-cases)
7. [Performance Test Cases](#7-performance-test-cases)
8. [Failure and Recovery Test Cases](#8-failure-and-recovery-test-cases)
9. [Acceptance Test Cases](#9-acceptance-test-cases)
10. [Test Data and Fixtures](#10-test-data-and-fixtures)
11. [CI/CD Integration](#11-cicd-integration)

---

## 1. Test Strategy Overview

### 1.1 Testing Pyramid

```
         ┌───────────────┐
         │   E2E Tests   │  (< 20 tests)
         │   (Slow)      │  Full pipeline validation
         ├───────────────┤
         │  Integration  │  (50-100 tests)
         │   Tests       │  Component interactions
         ├───────────────┤
         │               │
         │  Unit Tests   │  (500+ tests)
         │  (Fast)       │  Business logic, parsers, models
         │               │
         └───────────────┘
```

### 1.2 Coverage Targets

| Component                | Line Coverage | Branch Coverage |
|--------------------------|---------------|-----------------|
| N7-Core (services)       | >= 85%        | >= 75%          |
| N7-Core (API)            | >= 80%        | >= 70%          |
| N7-Sentinels (framework) | >= 85%        | >= 75%          |
| N7-Sentinels (probes)    | >= 70%        | >= 60%          |
| N7-Strikers (framework)  | >= 85%        | >= 75%          |
| N7-Strikers (actions)    | >= 80%        | >= 70%          |

### 1.3 Test Tooling

| Tool              | Purpose                                     |
|-------------------|---------------------------------------------|
| `pytest`          | Python test runner                          |
| `pytest-asyncio`  | Async test support                          |
| `pytest-cov`      | Coverage reporting                          |
| `hypothesis`      | Property-based testing                      |
| `factory_boy`     | Test fixture generation                     |
| `testcontainers`  | Ephemeral database/service containers       |
| `locust`          | Load testing                                |
| `bandit`          | Python SAST                                 |
| `semgrep`         | Multi-language SAST                         |
| `trivy`           | Container/dependency vulnerability scanning |
| `cargo test`      | Rust test runner                            |
| `jest` / `vitest` | Dashboard tests                             |

### 1.4 Test Naming Convention

```
test_{component}_{function}_{scenario}_{expected_result}

Examples:
  test_event_pipeline_validate_event_missing_required_field_raises_validation_error
  test_decision_engine_evaluate_alert_high_severity_returns_escalate_verdict
  test_network_striker_block_ip_valid_ip_succeeds
```

---

## 2. Test Environment

### 2.1 Local Development

```yaml
# test/docker-compose.test.yml
services:
  test-postgres:
    image: timescale/timescaledb:latest-pg16
    ports: ["5433:5432"]
    environment:
      POSTGRES_DB: n7_test
      POSTGRES_PASSWORD: test

  test-redis:
    image: redis:7-alpine
    ports: ["6380:6379"]

  test-nats:
    image: nats:2.10-alpine
    ports: ["4223:4222"]
    command: ["--jetstream"]

  test-minio:
    image: minio/minio:latest
    ports: ["9001:9000"]
    command: ["server", "/data"]
```

### 2.2 CI Environment

- All test dependencies run as ephemeral containers via `testcontainers`.
- No shared state between test runs.
- Tests are parallelized per component (`n7-core`, `n7-sentinels`, `n7-strikers` run concurrently in CI).

---

## 3. Unit Test Cases

### 3.1 Event Pipeline

| TC-ID     | Test Case                                  | Input                                                | Expected Result                                       | Req Traced |
|-----------|--------------------------------------------|------------------------------------------------------|-------------------------------------------------------|------------|
| UT-EP-001 | Validate well-formed event                 | Valid OCSF event JSON                                | Event accepted, returns normalized event              | FR-C001    |
| UT-EP-002 | Reject event with missing required fields  | Event missing `event_id`                             | `ValidationError` raised, event rejected              | FR-C001    |
| UT-EP-003 | Reject event with invalid severity         | Event with `severity: "banana"`                      | `ValidationError` raised                              | FR-C001    |
| UT-EP-004 | Normalize timestamp formats                | Event with ISO-8601, Unix epoch, RFC 3339 timestamps | All normalized to UTC ISO-8601                        | FR-C002    |
| UT-EP-005 | Deduplicate identical events within window | Two events with same dedup key within 60s            | Second event dropped, dedup counter incremented       | FR-C003    |
| UT-EP-006 | Allow same dedup key after window expires  | Same dedup key, second event after 61s               | Both events accepted                                  | FR-C003    |
| UT-EP-007 | Enrich event with asset metadata           | Event with known source IP                           | Event enriched with hostname, OS, criticality         | FR-C002    |
| UT-EP-008 | Enrich event — unknown asset               | Event with unknown source IP                         | Event enriched with `asset: null`, flagged as unknown | FR-C002    |
| UT-EP-009 | Enrich event with threat intel match       | Event with IP matching known IOC                     | Event enriched with IOC reference and confidence      | FR-C002    |
| UT-EP-010 | Handle malformed JSON gracefully           | Binary garbage as event payload                      | `ParseError` raised, event dropped, error logged      | FR-C001    |

### 3.2 Threat Correlator

| TC-ID     | Test Case                                        | Input                                                   | Expected Result                                | Req Traced |
|-----------|--------------------------------------------------|---------------------------------------------------------|------------------------------------------------|------------|
| UT-TC-001 | Correlate events by source IP within time window | 5 events from same IP within 2 min                      | Single correlated alert created                | FR-C010    |
| UT-TC-002 | No correlation — events outside time window      | 2 events from same IP, 10 min apart                     | No correlation (2 separate events)             | FR-C010    |
| UT-TC-003 | Map event to MITRE technique                     | Process creation with encoded PowerShell                | Alert includes T1059.001 mapping               | FR-C011    |
| UT-TC-004 | Multi-stage correlation                          | Brute-force events → login success → lateral connection | Single high-severity correlated alert          | FR-C010    |
| UT-TC-005 | Calculate threat score — high indicators         | Multiple high-confidence IOC matches, critical asset    | Threat score >= 80                             | FR-C014    |
| UT-TC-006 | Calculate threat score — low indicators          | Single low-confidence anomaly, non-critical asset       | Threat score <= 30                             | FR-C014    |
| UT-TC-007 | Parse and apply YAML correlation rule            | Valid correlation rule YAML                             | Rule loaded, applicable to matching events     | FR-C013    |
| UT-TC-008 | Reject invalid correlation rule                  | Rule with missing `stages` field                        | `RuleValidationError` raised                   | FR-C013    |
| UT-TC-009 | Update threat graph with new alert               | New alert linking 3 assets                              | Threat graph updated with edges between assets | FR-C012    |

### 3.3 Decision Engine

| TC-ID     | Test Case                                          | Input                                                      | Expected Result                             | Req Traced |
|-----------|----------------------------------------------------|------------------------------------------------------------|---------------------------------------------|------------|
| UT-DE-001 | Critical severity — always escalate                | Alert with severity=critical                               | Verdict: `escalate`                         | FR-C021    |
| UT-DE-002 | High severity — always escalate                    | Alert with severity=high                                   | Verdict: `escalate`                         | FR-C021    |
| UT-DE-003 | Medium severity, high confidence — auto respond    | Alert: medium, confidence=0.92                             | Verdict: `auto_respond`, playbook selected  | FR-C022    |
| UT-DE-004 | Medium severity, low confidence — escalate         | Alert: medium, confidence=0.60                             | Verdict: `escalate`                         | FR-C021    |
| UT-DE-005 | Low severity, sufficient confidence — auto respond | Alert: low, confidence=0.75                                | Verdict: `auto_respond`                     | FR-C022    |
| UT-DE-006 | Informational — dismiss                            | Alert: severity=informational                              | Verdict: `dismiss`                          | FR-C020    |
| UT-DE-007 | Blast radius exceeded — escalate instead           | Auto-respond verdict but 15 hosts affected (limit: 10)     | Verdict changed to `escalate`               | FR-C024    |
| UT-DE-008 | Cool-down active — skip auto-respond               | Same asset had auto-response 5 min ago (cool-down: 15 min) | Verdict: `escalate` (cool-down override)    | FR-C024    |
| UT-DE-009 | Dry-run mode — log only                            | Dry-run enabled, auto-respond verdict                      | Action logged but NOT dispatched            | FR-C025    |
| UT-DE-010 | Verdict includes reasoning trace                   | Any alert                                                  | Verdict includes non-empty reasoning object | FR-C026    |
| UT-DE-011 | Parse escalation policy YAML                       | Valid policy YAML                                          | Policy loaded correctly                     | FR-C021    |
| UT-DE-012 | Reject invalid escalation policy                   | Policy with missing `rules`                                | `PolicyValidationError` raised              | FR-C021    |

### 3.4 Agent Manager

| TC-ID     | Test Case                                    | Input                                                      | Expected Result                                     | Req Traced |
|-----------|----------------------------------------------|------------------------------------------------------------|-----------------------------------------------------|------------|
| UT-AM-001 | Register new agent                           | Valid agent manifest                                       | Agent added to registry with status=active          | FR-C030    |
| UT-AM-002 | Reject duplicate agent registration          | Same agent_id registered twice                             | Second registration rejected                        | FR-C030    |
| UT-AM-003 | Mark agent unhealthy after missed heartbeats | Agent misses 3 consecutive heartbeats                      | Status changed to `unhealthy`, alert raised         | FR-C031    |
| UT-AM-004 | Recover agent on heartbeat resume            | Unhealthy agent sends heartbeat                            | Status changed back to `active`                     | FR-C031    |
| UT-AM-005 | Route action to capable Striker              | Action type `block_ip`, 3 Strikers with mixed capabilities | Action routed to Striker with `block_ip` capability | FR-C033    |
| UT-AM-006 | No available Striker                         | Action type `block_ip`, no active Strikers with capability | `NoAvailableStrikerError` raised                    | FR-C033    |
| UT-AM-007 | Zone-scoped routing                          | Action for zone "dmz", Strikers in "dmz" and "internal"    | Action routed to "dmz" Striker only                 | FR-C034    |
| UT-AM-008 | Push config update to agent                  | Updated detection rule                                     | Config version incremented, update published        | FR-C032    |

### 3.5 Striker Actions

| TC-ID     | Test Case                                  | Input                                                        | Expected Result                                                | Req Traced |
|-----------|--------------------------------------------|--------------------------------------------------------------|----------------------------------------------------------------|------------|
| UT-SA-001 | Validate action authorization token        | Valid signed token from Core                                 | Token accepted, action proceeds                                | FR-K006    |
| UT-SA-002 | Reject expired authorization token         | Token with `expires_at` in the past                          | Token rejected, action refused                                 | FR-K006    |
| UT-SA-003 | Reject token with invalid signature        | Token with tampered signature                                | Token rejected, security alert raised                          | FR-K006    |
| UT-SA-004 | Reject mismatched action type              | Token authorizes `block_ip`, Striker receives `kill_process` | Action rejected                                                | FR-K006    |
| UT-SA-005 | Action timeout enforcement                 | Action exceeds 5-minute timeout                              | Action killed, status reported as `failed` with timeout reason | FR-K005    |
| UT-SA-006 | Rollback entry creation                    | Successful `block_ip` action                                 | Rollback entry created with `unblock_ip` params                | FR-K004    |
| UT-SA-007 | Rollback execution                         | Rollback triggered for `block_ip`                            | IP unblocked, rollback status reported                         | FR-K004    |
| UT-SA-008 | Evidence capture before destructive action | `kill_process` action on target host                         | Process list and connection list captured before kill          | FR-K007    |

### 3.6 Audit Logger

| TC-ID     | Test Case                          | Input                             | Expected Result                                    | Req Traced |
|-----------|------------------------------------|-----------------------------------|----------------------------------------------------|------------|
| UT-AL-001 | Create audit entry with hash chain | New audit entry                   | Entry created, hash = SHA-256(content + prev_hash) | FR-C041    |
| UT-AL-002 | Verify hash chain integrity        | Sequence of 10 audit entries      | Chain validates (each hash matches recomputation)  | FR-C041    |
| UT-AL-003 | Detect tampered audit entry        | Modified entry in middle of chain | Chain validation fails at tampered entry           | FR-C041    |
| UT-AL-004 | Export audit log in OCSF format    | 100 audit entries                 | Valid OCSF JSON export                             | FR-C042    |
| UT-AL-005 | Export audit log in CEF format     | 100 audit entries                 | Valid CEF string export                            | FR-C042    |

### 3.7 Playbook Engine

| TC-ID     | Test Case                                | Input                                                         | Expected Result                          | Req Traced |
|-----------|------------------------------------------|---------------------------------------------------------------|------------------------------------------|------------|
| UT-PB-001 | Parse valid playbook YAML                | Well-formed playbook                                          | Playbook object with all steps loaded    | FR-K002    |
| UT-PB-002 | Reject playbook with invalid step action | Playbook with unknown `action_type`                           | `PlaybookValidationError` raised         | FR-K002    |
| UT-PB-003 | Template parameter substitution          | Playbook with `{{ target_ip }}` template                      | Parameters correctly substituted         | FR-K002    |
| UT-PB-004 | Conditional step — condition true        | Step with `condition: "{{ var is defined }}"`, var is defined | Step executes                            | FR-K002    |
| UT-PB-005 | Conditional step — condition false       | Step with `condition: "{{ var is defined }}"`, var undefined  | Step skipped                             | FR-K002    |
| UT-PB-006 | Step failure — on_failure: continue      | Step fails, `on_failure: continue`                            | Next step executes, failure logged       | FR-K002    |
| UT-PB-007 | Step failure — on_failure: abort         | Step fails, `on_failure: abort`                               | Playbook aborts, remaining steps skipped | FR-K002    |
| UT-PB-008 | Playbook max duration enforcement        | Playbook exceeds `max_duration`                               | Playbook aborted, timeout reported       | FR-K005    |

---

## 4. Integration Test Cases

### 4.1 Event Flow (Sentinel → Core)

| TC-ID     | Test Case                                  | Setup                          | Steps                        | Expected Result                                    | Req Traced       |
|-----------|--------------------------------------------|--------------------------------|------------------------------|----------------------------------------------------|------------------|
| IT-EF-001 | Event flows from Sentinel to Core pipeline | Core + NATS + Sentinel running | Sentinel emits event to NATS | Core receives, validates, enriches, persists event | FR-C001, FR-S002 |
| IT-EF-002 | Event persists to TimescaleDB              | Core + PostgreSQL/TimescaleDB  | Emit 100 events              | All 100 events queryable in TimescaleDB            | FR-C004          |
| IT-EF-003 | Event dedup across Core instances          | 2 Core instances, shared Redis | Same event published twice   | Only one event persisted                           | FR-C003          |
| IT-EF-004 | Sentinel offline cache and replay          | Sentinel running, NATS stopped | Emit 50 events, restart NATS | All 50 events replayed and received by Core        | FR-S006          |

### 4.2 Alert and Decision Flow

| TC-ID     | Test Case                           | Setup                                    | Steps                                                 | Expected Result                                              | Req Traced       |
|-----------|-------------------------------------|------------------------------------------|-------------------------------------------------------|--------------------------------------------------------------|------------------|
| IT-AD-001 | Correlated events produce alert     | Core + DB                                | Emit 10 auth failure events from same IP within 5 min | Alert created with threat_score and severity                 | FR-C010, FR-C014 |
| IT-AD-002 | Alert triggers auto-respond verdict | Core + escalation policy (medium → auto) | Create medium-severity alert with confidence 0.9      | Verdict: `auto_respond`, playbook dispatched                 | FR-C022          |
| IT-AD-003 | Alert triggers escalation           | Core + notification config               | Create critical-severity alert                        | Verdict: `escalate`, notification sent to configured channel | FR-C023          |
| IT-AD-004 | Verdict persists in audit log       | Core + DB                                | Any alert processed                                   | Audit entry with verdict, reasoning, and valid hash chain    | FR-C040          |

### 4.3 Action Dispatch and Execution

| TC-ID     | Test Case                         | Setup                       | Steps                                  | Expected Result                                        | Req Traced       |
|-----------|-----------------------------------|-----------------------------|----------------------------------------|--------------------------------------------------------|------------------|
| IT-AE-001 | Core dispatches action to Striker | Core + NATS + Striker       | Create auto-respond verdict            | Striker receives action with valid authorization token | FR-C022, FR-K002 |
| IT-AE-002 | Striker reports action status     | Core + NATS + Striker       | Striker executes action                | Core receives status updates (executing → succeeded)   | FR-K003          |
| IT-AE-003 | Striker action rollback via API   | Core + NATS + Striker + API | Execute action, then call rollback API | Striker executes rollback, status: `rolled_back`       | FR-K004          |
| IT-AE-004 | Action rejected — unauthorized    | Core + NATS + Striker       | Send action with tampered token        | Striker rejects action, security alert raised          | FR-K006          |

### 4.4 Agent Lifecycle

| TC-ID     | Test Case                     | Setup                  | Steps                                     | Expected Result                                       | Req Traced |
|-----------|-------------------------------|------------------------|-------------------------------------------|-------------------------------------------------------|------------|
| IT-AL-001 | Agent registration on startup | Core + NATS            | Start new Sentinel                        | Sentinel appears in agent registry with status=active | FR-C030    |
| IT-AL-002 | Heartbeat monitoring          | Core + NATS + Sentinel | Sentinel sends heartbeats for 2 min       | Agent record shows updated `last_heartbeat`           | FR-C031    |
| IT-AL-003 | Agent marked unhealthy        | Core + NATS + Sentinel | Stop Sentinel, wait 3x heartbeat interval | Agent status changes to `unhealthy`                   | FR-C031    |
| IT-AL-004 | Config push to agent          | Core + NATS + Sentinel | Update detection rule via API             | Sentinel receives and applies new config              | FR-C032    |

### 4.5 API Integration

| TC-ID      | Test Case                       | Setup                              | Steps                               | Expected Result                                         | Req Traced |
|------------|---------------------------------|------------------------------------|-------------------------------------|---------------------------------------------------------|------------|
| IT-API-001 | Authenticate with API key       | Core API running                   | Send request with valid API key     | 200 OK, response returned                               | FR-A003    |
| IT-API-002 | Reject invalid API key          | Core API running                   | Send request with invalid key       | 401 Unauthorized                                        | FR-A003    |
| IT-API-003 | RBAC enforcement — Analyst role | Core API, authenticated as Analyst | Attempt to modify escalation policy | 403 Forbidden                                           | FR-A004    |
| IT-API-004 | List alerts with pagination     | Core API + 50 alerts in DB         | GET /api/v1/alerts?page=1&size=10   | 10 alerts returned, pagination metadata present         | FR-A005    |
| IT-API-005 | Rate limiting                   | Core API running                   | Send 1100 requests in 1 minute      | First 1000 succeed, remaining get 429 Too Many Requests | FR-A008    |
| IT-API-006 | OpenAPI spec endpoint           | Core API running                   | GET /api/v1/openapi.json            | Valid OpenAPI 3.1 spec returned                         | FR-A007    |

---

## 5. End-to-End Test Cases

### 5.1 Full Pipeline Tests

| TC-ID   | Test Case                                 | Scenario                                                                                | Expected Result                                                                                                   | Req Traced             |
|---------|-------------------------------------------|-----------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|------------------------|
| E2E-001 | Brute-force detection to auto-containment | Simulate 20 failed SSH logins from external IP → successful login → outbound connection | Alert generated → auto-respond verdict → Network Striker blocks IP → audit trail complete                         | BR-D01, BR-R01, BR-O05 |
| E2E-002 | Malware detection to process kill         | Drop EICAR test file on monitored endpoint                                              | Endpoint Sentinel detects via YARA → alert → auto-respond → Endpoint Striker quarantines file → audit trail       | BR-D02, BR-R01         |
| E2E-003 | Cloud misconfiguration to remediation     | Create public S3 bucket in test account                                                 | Cloud Sentinel detects public bucket → alert → auto-respond → Cloud Striker sets bucket to private → audit trail  | BR-D03, BR-R01         |
| E2E-004 | High severity — human escalation          | Simulate data exfiltration pattern (large outbound transfer to unknown IP)              | Alert with severity=high → escalate verdict → Slack notification sent → incident created in dashboard             | BR-R02, FR-C023        |
| E2E-005 | Multi-stage attack correlation            | Simulate: port scan → exploit attempt → reverse shell → lateral movement                | Events correlated into single multi-stage alert → MITRE mapping includes multiple tactics → escalated to operator | FR-C010, FR-C011       |
| E2E-006 | Rollback after false positive             | Trigger auto-containment → operator identifies false positive → initiates rollback      | Striker rolls back all actions → IP unblocked → rollback logged in audit                                          | BR-R04, FR-K004        |
| E2E-007 | Dry-run mode validation                   | Enable dry-run, trigger medium severity alert                                           | Decision engine selects playbook → action logged as "dry_run" → NO actual Striker action executed                 | FR-C025                |
| E2E-008 | Sentinel offline resilience               | Stop NATS, generate 100 events, restart NATS                                            | Sentinel caches events locally → on reconnect, all 100 events replayed → Core processes all                       | FR-S006, BR-OP04       |

---

## 6. Security Test Cases

### 6.1 Authentication and Authorization

| TC-ID     | Test Case                               | Attack Vector                               | Expected Result                           |
|-----------|-----------------------------------------|---------------------------------------------|-------------------------------------------|
| ST-AA-001 | API access without credentials          | Unauthenticated request to any API endpoint | 401 Unauthorized                          |
| ST-AA-002 | Expired API key                         | Request with revoked/expired API key        | 401 Unauthorized                          |
| ST-AA-003 | Privilege escalation — Analyst to Admin | Analyst token used on admin-only endpoint   | 403 Forbidden                             |
| ST-AA-004 | RBAC bypass via parameter manipulation  | Modify request body to include admin fields | Fields ignored, RBAC enforced server-side |

### 6.2 Inter-Agent Security

| TC-ID     | Test Case                            | Attack Vector                                      | Expected Result                               |
|-----------|--------------------------------------|----------------------------------------------------|-----------------------------------------------|
| ST-IA-001 | Rogue agent registration             | Agent attempts to register with forged certificate | Registration rejected, security alert raised  |
| ST-IA-002 | Message replay attack                | Replay captured NATS message                       | Message rejected (nonce/timestamp validation) |
| ST-IA-003 | Striker action without authorization | Directly send action to Striker bypassing Core     | Striker rejects — invalid authorization token |
| ST-IA-004 | Tampered action authorization        | Modify action parameters after signing             | Signature verification fails, action rejected |
| ST-IA-005 | mTLS certificate validation          | Connect to NATS without valid client certificate   | Connection rejected                           |

### 6.3 Input Validation

| TC-ID     | Test Case                             | Attack Vector                                                   | Expected Result                                    |
|-----------|---------------------------------------|-----------------------------------------------------------------|----------------------------------------------------|
| ST-IV-001 | SQL injection via API                 | `GET /api/v1/alerts?filter='; DROP TABLE alerts;--`             | Input sanitized, no SQL execution, 400 Bad Request |
| ST-IV-002 | XSS via event data in dashboard       | Event with `<script>` tag in description                        | Content escaped in dashboard rendering             |
| ST-IV-003 | Command injection via playbook params | Playbook parameter containing shell metacharacters `; rm -rf /` | Parameters sanitized, no shell execution           |
| ST-IV-004 | YAML deserialization attack           | Malicious YAML in detection rule upload                         | Safe YAML loader used, no code execution           |
| ST-IV-005 | Oversized event payload               | 100 MB event payload                                            | Request rejected with 413 Payload Too Large        |
| ST-IV-006 | Path traversal in file operations     | Striker action with `../../etc/passwd` as path                  | Path normalized, traversal blocked                 |

### 6.4 Agent Integrity

| TC-ID     | Test Case              | Attack Vector                    | Expected Result                                                           |
|-----------|------------------------|----------------------------------|---------------------------------------------------------------------------|
| ST-AI-001 | Modified agent binary  | Agent binary with altered hash   | Core detects hash mismatch, quarantines agent                             |
| ST-AI-002 | Agent config tampering | Locally modify agent config file | Agent detects config integrity violation, requests fresh config from Core |

### 6.5 Static Analysis (SAST)

| TC-ID     | Tool                            | Target                     | Pass Criteria                                 |
|-----------|---------------------------------|----------------------------|-----------------------------------------------|
| ST-SA-001 | Bandit                          | All Python code            | No High or Critical findings                  |
| ST-SA-002 | Semgrep (security ruleset)      | All Python/TypeScript code | No findings matching security rules           |
| ST-SA-003 | `cargo clippy` (security lints) | All Rust code              | No warnings                                   |
| ST-SA-004 | Trivy                           | All container images       | No Critical CVEs, no High CVEs without waiver |
| ST-SA-005 | Safety / pip-audit              | Python dependencies        | No known vulnerabilities                      |

---

## 7. Performance Test Cases

### 7.1 Throughput Tests

| TC-ID    | Test Case                    | Scenario                                       | Target                                     | Tool                               |
|----------|------------------------------|------------------------------------------------|--------------------------------------------|------------------------------------|
| PT-T-001 | Event ingestion throughput   | Sustained event generation at increasing rates | >= 10,000 events/sec on reference hardware | Locust + synthetic events          |
| PT-T-002 | Alert correlation throughput | Sustained correlated event streams             | >= 1,000 correlations/sec                  | Locust + correlated event patterns |
| PT-T-003 | API read throughput          | Concurrent GET requests to /api/v1/alerts      | >= 5,000 req/sec (200 OK)                  | Locust                             |

### 7.2 Latency Tests

| TC-ID    | Test Case               | Measurement                                           | Target        | Tool                                   |
|----------|-------------------------|-------------------------------------------------------|---------------|----------------------------------------|
| PT-L-001 | Event pipeline latency  | Time from NATS receive to TimescaleDB persist         | < 5 sec (p99) | Embedded timing + Prometheus histogram |
| PT-L-002 | Decision engine latency | Time from alert creation to verdict                   | < 3 sec (p99) | Embedded timing                        |
| PT-L-003 | Action dispatch latency | Time from verdict to Striker receives action          | < 2 sec (p99) | Embedded timing                        |
| PT-L-004 | Dashboard load time     | Time to render main dashboard with 1000 active alerts | < 2 sec (p95) | Lighthouse / Playwright                |
| PT-L-005 | API response time       | GET /api/v1/alerts (10,000 alerts in DB)              | < 200ms (p95) | Locust                                 |

### 7.3 Resource Utilization Tests

| TC-ID    | Test Case                          | Scenario                                          | Target                                      |
|----------|------------------------------------|---------------------------------------------------|---------------------------------------------|
| PT-R-001 | Endpoint Sentinel CPU overhead     | Sentinel running on host with normal workload     | < 5% additional CPU usage                   |
| PT-R-002 | Endpoint Sentinel memory footprint | Sentinel running for 24h                          | < 256 MB RSS (no memory leak)               |
| PT-R-003 | Core memory under sustained load   | 10,000 events/sec for 1 hour                      | No memory leak (RSS stable within 10%)      |
| PT-R-004 | Offline cache growth               | Sentinel disconnected from NATS, 1,000 events/sec | Cache grows linearly, respects 500 MB limit |

### 7.4 Scalability Tests

| TC-ID    | Test Case                | Scenario                                       | Target                                      |
|----------|--------------------------|------------------------------------------------|---------------------------------------------|
| PT-S-001 | Horizontal Core scaling  | Add 2nd Core instance under load               | Throughput increases by >= 80%              |
| PT-S-002 | 100 concurrent Sentinels | Register 100 Sentinels sending events          | Core handles all events without degradation |
| PT-S-003 | 10 concurrent Strikers   | Dispatch actions to 10 Strikers simultaneously | All actions dispatched and executed         |

---

## 8. Failure and Recovery Test Cases

| TC-ID  | Test Case                           | Failure Injected                         | Expected Behavior                                                 | Recovery Verification                                       |
|--------|-------------------------------------|------------------------------------------|-------------------------------------------------------------------|-------------------------------------------------------------|
| FR-001 | Core process crash                  | Kill Core process                        | K8s restarts Core                                                 | Core resumes processing, no event loss (NATS persistence)   |
| FR-002 | Database failover                   | Stop primary PostgreSQL                  | Core fails over to replica                                        | Reads continue, writes resume on promotion                  |
| FR-003 | NATS broker crash                   | Stop NATS process                        | Sentinels cache locally, Strikers idle                            | On NATS restart, events replayed, Strikers reconnect        |
| FR-004 | Redis outage                        | Stop Redis                               | Dedup falls back to in-memory (degraded), dashboard updates stall | On Redis restart, full functionality resumes                |
| FR-005 | Network partition (Sentinel ↔ Core) | iptables block between Sentinel and NATS | Sentinel caches events, Core marks Sentinel unhealthy             | On network restore, events replayed, Sentinel marked active |
| FR-006 | Striker crash mid-action            | Kill Striker during action execution     | Action reported as `failed` (timeout)                             | Core reassigns action to another Striker                    |
| FR-007 | Disk full on Sentinel               | Fill Sentinel host disk                  | Sentinel drops new cache entries, emits warning                   | On disk space recovery, caching resumes                     |
| FR-008 | Concurrent Core failover            | Kill active Core, standby takes over     | < 30 second recovery, no duplicate actions                        | Verify no duplicate verdicts or actions dispatched          |

---

## 9. Acceptance Test Cases

These tests validate business requirements from the BRD and map to success criteria.

| TC-ID  | Acceptance Criterion           | Test Scenario                                                       | Pass Criteria                                              | SC Traced |
|--------|--------------------------------|---------------------------------------------------------------------|------------------------------------------------------------|-----------|
| AT-001 | MTTD < 60 seconds              | Inject known malware signature, measure time to alert               | Alert generated within 60 seconds of event                 | SC-01     |
| AT-002 | MTTR < 5 minutes (auto)        | Trigger auto-containment scenario, measure end-to-end               | Containment action completed within 5 minutes of detection | SC-02     |
| AT-003 | False positive rate < 2%       | Run 1,000 mixed benign/malicious events, count false auto-responses | < 20 false positive auto-responses                         | SC-03     |
| AT-004 | System availability 99.9%      | 7-day soak test with injected failures                              | Total downtime < 10 minutes                                | SC-04     |
| AT-005 | Endpoint overhead < 5% CPU     | Run Sentinel on host under benchmark workload                       | CPU overhead measured < 5%                                 | SC-05     |
| AT-006 | Audit completeness 100%        | Run 50 end-to-end scenarios, verify audit trail for each            | Every event, verdict, and action has audit entry           | SC-06     |
| AT-007 | Blast radius controls work     | Attempt auto-response affecting 15 hosts (limit: 10)                | Auto-response blocked, escalated to human                  | BR-R05    |
| AT-008 | Manual override works          | During auto-response, operator cancels via dashboard                | Action stopped, rollback offered, state consistent         | BR-R06    |
| AT-009 | Human-in-the-loop for critical | Generate critical severity threat                                   | System escalates, does NOT auto-respond, waits for human   | BR-R02    |
| AT-010 | Rollback functionality         | Auto-contain, then rollback                                         | All containment actions reversed, systems restored         | BR-R04    |

---

## 10. Test Data and Fixtures

### 10.1 Synthetic Event Generators

| Generator             | Description                                                             | Output                                |
|-----------------------|-------------------------------------------------------------------------|---------------------------------------|
| `gen_network_events`  | Simulates network traffic patterns (normal + attack)                    | OCSF network events                   |
| `gen_endpoint_events` | Simulates process creation, file changes, auth events                   | OCSF endpoint events                  |
| `gen_cloud_events`    | Simulates cloud API audit logs                                          | OCSF cloud events                     |
| `gen_attack_sequence` | Generates a multi-stage attack pattern (brute-force → access → lateral) | Ordered sequence of correlated events |
| `gen_benign_noise`    | High-volume normal activity for false-positive testing                  | Mixed benign events                   |

### 10.2 Fixture Data

| Fixture                          | Description                                              |
|----------------------------------|----------------------------------------------------------|
| `asset_inventory.json`           | 100 test assets (servers, workstations, cloud instances) |
| `threat_intel_feed.json`         | 500 test IOCs (IPs, domains, file hashes)                |
| `escalation_policy_default.yaml` | Standard test escalation policy                          |
| `playbook_contain_medium.yaml`   | Test containment playbook                                |
| `correlation_rules_test.yaml`    | Test correlation rules                                   |
| `detection_rules_test.yaml`      | Test detection rules                                     |
| `yara_rules_test/`               | Test YARA rules with EICAR samples                       |

### 10.3 Attack Simulation Datasets

| Dataset                        | MITRE Techniques                  | Events | Description                                                  |
|--------------------------------|-----------------------------------|--------|--------------------------------------------------------------|
| `attack_bruteforce.json`       | T1110                             | 25     | SSH brute-force attempt                                      |
| `attack_malware_exec.json`     | T1059, T1055                      | 15     | Malware download and execution                               |
| `attack_lateral_movement.json` | T1021, T1071                      | 30     | Post-compromise lateral movement                             |
| `attack_data_exfil.json`       | T1041, T1048                      | 20     | Data exfiltration via DNS tunneling                          |
| `attack_full_chain.json`       | T1190, T1059, T1003, T1021, T1041 | 80     | Full kill chain: exploit → execute → creds → lateral → exfil |

---

## 11. CI/CD Integration

### 11.1 Pipeline Stages

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐
│  Lint &  │   │  Unit    │   │Integration│   │ Security  │   │  Build   │
│  Format  │──▶│  Tests   │──▶│  Tests   │──▶│  Scans    │──▶│  Images  │
│          │   │          │   │          │   │           │   │          │
│  ruff    │   │  pytest  │   │ testcont.│   │  bandit   │   │  docker  │
│  clippy  │   │  cargo   │   │          │   │  semgrep  │   │  build   │
│  eslint  │   │  vitest  │   │          │   │  trivy    │   │          │
└──────────┘   └──────────┘   └──────────┘   └───────────┘   └──────────┘
     │              │              │               │               │
     ▼              ▼              ▼               ▼               ▼
   Block on       Block on      Block on       Block on       Artifacts
   failure        failure       failure        High/Critical   published
                  + coverage                   findings
                  < threshold
```

### 11.2 PR Checks (Required to Merge)

| Check                              | Gate                            |
|------------------------------------|---------------------------------|
| Lint passes (ruff, clippy, eslint) | Must pass                       |
| Unit tests pass                    | Must pass                       |
| Coverage >= threshold              | Must meet per-component targets |
| Integration tests pass             | Must pass                       |
| SAST (Bandit, Semgrep)             | No High/Critical findings       |
| Dependency scan (Trivy, Safety)    | No Critical CVEs                |
| Docker image builds                | Must succeed                    |

### 11.3 Nightly / Weekly Runs

| Schedule | Tests                                                                |
|----------|----------------------------------------------------------------------|
| Nightly  | Full E2E test suite, performance benchmarks                          |
| Weekly   | Soak test (24h sustained load), full security scan, dependency audit |
