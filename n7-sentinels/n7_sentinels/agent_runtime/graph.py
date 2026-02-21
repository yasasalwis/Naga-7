import logging
import os
import socket
from typing import Dict, List, Any

import psutil
from langgraph.graph import StateGraph, END

logger = logging.getLogger("n7-sentinel.agent-runtime.graph")


class AgentState(Dict):
    """
    Represents the state of the Sentinel Agent.
    """
    messages: List[str]
    metrics: Dict[str, Any]
    anomalies: List[str]
    severity: str
    status: str


def monitor_node(state: AgentState) -> AgentState:
    """
    Collects full system metrics: CPU, memory, disk, network I/O, and load average.
    """
    logger.info("Sentinel: Monitoring system state...")

    cpu_percent = psutil.cpu_percent(interval=0.1)
    mem         = psutil.virtual_memory()
    disk        = psutil.disk_usage('/')
    net         = psutil.net_io_counters()
    load        = os.getloadavg() if hasattr(os, 'getloadavg') else (0.0, 0.0, 0.0)

    metrics = {
        "cpu_percent":         cpu_percent,
        "memory_percent":      mem.percent,
        "memory_available_mb": mem.available // (1024 * 1024),
        "disk_percent":        disk.percent,
        "disk_free_gb":        disk.free // (1024 ** 3),
        "net_bytes_sent":      net.bytes_sent,
        "net_bytes_recv":      net.bytes_recv,
        "load_avg_1m":         load[0],
    }

    state["metrics"] = metrics
    state["messages"].append(
        f"Monitored: CPU={cpu_percent:.1f}% MEM={mem.percent:.1f}% "
        f"DISK={disk.percent:.1f}% LOAD={load[0]:.2f}"
    )
    return state


def analyze_node(state: AgentState) -> AgentState:
    """
    Applies local threshold rules to detect anomalies across all system metrics.
    Sets state["status"] to "alert" or "normal" and records anomaly descriptions.
    """
    logger.info("Sentinel: Analyzing metrics...")
    metrics   = state.get("metrics", {})
    anomalies = state.get("anomalies", [])

    cpu   = metrics.get("cpu_percent", 0)
    mem   = metrics.get("memory_percent", 0)
    disk  = metrics.get("disk_percent", 0)
    load  = metrics.get("load_avg_1m", 0.0)
    cores = psutil.cpu_count(logical=True) or 1

    checks = [
        (cpu  > 80,         "high",   f"High CPU usage: {cpu:.1f}%"),
        (mem  > 85,         "high",   f"High memory usage: {mem:.1f}%"),
        (disk > 90,         "high",   f"High disk usage: {disk:.1f}%"),
        (load > cores * 2,  "medium", f"High load average: {load:.2f} (cores={cores})"),
    ]

    triggered = [(sev, desc) for condition, sev, desc in checks if condition]

    if triggered:
        severity = "high" if any(s == "high" for s, _ in triggered) else "medium"
        new_anomalies = [desc for _, desc in triggered]
        anomalies.extend(new_anomalies)
        state["status"]    = "alert"
        state["severity"]  = severity
        logger.warning(f"Anomalies detected: {new_anomalies}")
    else:
        state["status"]   = "normal"
        state["severity"] = "informational"

    state["anomalies"] = anomalies
    state["messages"].append(
        f"Analysis complete. Status: {state['status']} Severity: {state.get('severity')}"
    )
    return state


def build_emit_node(event_emitter_service):
    """
    Factory that returns an emit_node coroutine bound to the given EventEmitterService.
    Only invoked when state["status"] == "alert".
    Core's existing pipeline (EventPipeline → ThreatCorrelator → LLMAnalyzer → DecisionEngine)
    handles all LLM analysis and Striker dispatch downstream.
    """
    async def emit_node(state: AgentState) -> AgentState:
        logger.info("Sentinel: Emitting anomaly event to Core...")
        anomalies = state.get("anomalies", [])
        metrics   = state.get("metrics", {})
        severity  = state.get("severity", "medium")

        try:
            source_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            source_ip = "unknown"

        event = {
            "event_class": "endpoint",
            "severity":    severity,
            "raw_data": {
                "description": "; ".join(anomalies),
                "source_ip":   source_ip,
                **metrics,
            },
        }

        try:
            await event_emitter_service.emit(event)
            state["messages"].append(f"Emitted {severity} endpoint event to Core.")
        except Exception as e:
            logger.error(f"Failed to emit anomaly event: {e}")

        return state

    return emit_node


def _should_emit(state: AgentState) -> str:
    """Conditional router: emit only when an alert was detected."""
    return "emit" if state.get("status") == "alert" else END


def build_sentinel_graph(event_emitter_service=None):
    """
    Builds the LangGraph for the Sentinel Agent.
    Pass an EventEmitterService instance to enable anomaly event emission to Core.
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("monitor", monitor_node)
    workflow.add_node("analyze", analyze_node)

    workflow.set_entry_point("monitor")
    workflow.add_edge("monitor", "analyze")

    if event_emitter_service is not None:
        emit_node = build_emit_node(event_emitter_service)
        workflow.add_node("emit", emit_node)
        workflow.add_conditional_edges(
            "analyze",
            _should_emit,
            {"emit": "emit", END: END}
        )
        workflow.add_edge("emit", END)
    else:
        workflow.add_edge("analyze", END)

    return workflow.compile()
