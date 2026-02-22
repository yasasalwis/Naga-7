"""
Correlation Rules Configuration.
Defines multi-stage attack patterns and detection logic.
"""

# Correlation Rule Definitions
CORRELATION_RULES = {
    # Rule 1: Brute Force Detection
    "brute_force": {
        "name": "Brute Force Attack Detection",
        "description": "Detects multiple failed authentication attempts from the same source",
        "pattern": {
            "event_class": "authentication",
            "outcome": "failure"
        },
        "threshold": 5,
        "time_window": 60,  # seconds
        "severity": "high",
        "mitre_tactics": ["TA0001"],  # Initial Access
        "mitre_techniques": ["T1110"]  # Brute Force
    },

    # Rule 2: Lateral Movement Detection
    "lateral_movement": {
        "name": "Lateral Movement Detection",
        "description": "Detects suspicious lateral movement patterns",
        "multi_stage": [
            {
                "event_class": "authentication",
                "outcome": "success",
                "min_occurrences": 1
            },
            {
                "event_class": "process",
                "process_name_contains": ["psexec", "wmic", "powershell"],
                "min_occurrences": 1,
                "within_seconds": 300
            }
        ],
        "severity": "critical",
        "mitre_tactics": ["TA0008"],  # Lateral Movement
        "mitre_techniques": ["T1021"]  # Remote Services
    },

    # Rule 3: Data Exfiltration Detection
    "data_exfiltration": {
        "name": "Data Exfiltration Detection",
        "description": "Detects large outbound data transfers",
        "pattern": {
            "event_class": "network",
            "direction": "outbound",
            "bytes_threshold": 1048576  # 1MB
        },
        "threshold": 3,
        "time_window": 120,
        "severity": "critical",
        "mitre_tactics": ["TA0010"],  # Exfiltration
        "mitre_techniques": ["T1041"]  # Exfiltration Over C2 Channel
    },

    # Rule 4: Credential Dumping
    "credential_dumping": {
        "name": "Credential Dumping Detection",
        "description": "Detects tools commonly used for credential theft",
        "pattern": {
            "event_class": "process",
            "process_name_regex": "(mimikatz|procdump|lsass|pwdump)"
        },
        "threshold": 1,
        "time_window": 60,
        "severity": "critical",
        "mitre_tactics": ["TA0006"],  # Credential Access
        "mitre_techniques": ["T1003"]  # OS Credential Dumping
    },

    # Rule 5: Ransomware Behavior
    "ransomware_behavior": {
        "name": "Ransomware Behavior Detection",
        "description": "Detects file encryption patterns typical of ransomware",
        "multi_stage": [
            {
                "event_class": "file",
                "action_contains": ["modify", "rename"],
                "min_occurrences": 10,
                "within_seconds": 60
            },
            {
                "event_class": "process",
                "process_name_contains": ["vssadmin", "wbadmin", "bcdedit"],
                "action_contains": ["delete", "shadows"],
                "min_occurrences": 1,
                "within_seconds": 120
            }
        ],
        "severity": "critical",
        "mitre_tactics": ["TA0040"],  # Impact
        "mitre_techniques": ["T1486"]  # Data Encrypted for Impact
    },

    # Rule 6: IOC Match — event was enriched with a known-malicious indicator
    # Triggered by EventPipeline when ThreatIntelService finds an IOC match in raw_data.
    # The pipeline sets ioc_matched=True in raw_data before forwarding.
    "ioc_match": {
        "name": "Threat Intel IOC Match",
        "description": (
            "An event's raw data matched a known-malicious Indicator of Compromise "
            "(IP, domain, URL, or file hash) from the threat intelligence feed."
        ),
        "pattern": {
            "ioc_matched": True
        },
        "threshold": 1,
        "time_window": 300,
        "severity": "critical",
        "mitre_tactics": ["TA0043"],   # Reconnaissance
        "mitre_techniques": ["T1595"]  # Active Scanning
    },

    # Rule 7: High CPU Usage — endpoint resource anomaly from SystemProbe
    # Sentinel emits event_class="endpoint" with description containing "High CPU Usage"
    "high_cpu_usage": {
        "name": "Sustained High CPU Usage",
        "description": (
            "A monitored endpoint is reporting sustained high CPU utilisation, "
            "which may indicate a crypto-miner, denial-of-service, or runaway process."
        ),
        "pattern": {
            "event_class": "endpoint",
            "description_regex": r"High CPU Usage"
        },
        "threshold": 1,
        "time_window": 120,
        "severity": "high",
        "mitre_tactics": ["TA0040"],   # Impact
        "mitre_techniques": ["T1496"]  # Resource Hijacking
    },

    # Rule 8: High Memory Usage — endpoint resource anomaly from SystemProbe
    "high_memory_usage": {
        "name": "Sustained High Memory Usage",
        "description": (
            "A monitored endpoint is reporting sustained high memory utilisation."
        ),
        "pattern": {
            "event_class": "endpoint",
            "description_regex": r"High Memory Usage"
        },
        "threshold": 1,
        "time_window": 120,
        "severity": "high",
        "mitre_tactics": ["TA0040"],
        "mitre_techniques": ["T1496"]
    },

    # Rule 9: Honeytoken File Access — Active Deception / Endpoint Deception Engine
    # Threshold=1: any single access to a decoy file is 100% confidence.
    # Legitimate users will never see or interact with honeytoken files.
    "honeytoken_access": {
        "name": "Honeytoken File Access",
        "description": (
            "A deception honeytoken file was accessed. Legitimate users never interact "
            "with these files, so any access indicates an active attacker or malicious "
            "insider performing reconnaissance."
        ),
        "pattern": {
            "event_class": "honeytoken_access"
        },
        "threshold": 1,
        "time_window": 3600,  # seconds (effectively: first event always fires alert)
        "severity": "critical",
        "mitre_tactics": ["TA0009"],   # Collection
        "mitre_techniques": ["T1083"]  # File and Directory Discovery
    }
}
