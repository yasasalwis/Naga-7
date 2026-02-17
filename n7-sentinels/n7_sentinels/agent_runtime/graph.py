import logging
from typing import Dict, List, Any

from langgraph.graph import StateGraph, END

logger = logging.getLogger("n7-sentinel.agent-runtime.graph")


class AgentState(Dict):
    """
    Represents the state of the Sentinel Agent.
    """
    messages: List[str]
    metrics: Dict[str, Any]
    anomalies: List[str]
    status: str


def monitor_node(state: AgentState) -> AgentState:
    """
    Simulates monitoring system resources or events.
    """
    logger.info("Sentinel: Monitoring system state...")
    # In a real implementation, this would read from sources.
    # For now, we mock some metrics.
    current_metrics = state.get("metrics", {})
    # Mocking a simple CPU check
    import psutil
    cpu_percent = psutil.cpu_percent(interval=0.1)

    current_metrics["cpu_usage"] = cpu_percent
    state["metrics"] = current_metrics
    state["messages"].append(f"Monitored CPU: {cpu_percent}%")

    return state


def analyze_node(state: AgentState) -> AgentState:
    """
    Analyzes collected metrics for anomalies.
    """
    logger.info("Sentinel: Analyzing metrics...")
    metrics = state.get("metrics", {})
    cpu = metrics.get("cpu_usage", 0)

    anomalies = state.get("anomalies", [])
    if cpu > 80:
        anomalies.append(f"High CPU usage detected: {cpu}%")
        state["status"] = "alert"
    else:
        state["status"] = "normal"

    state["anomalies"] = anomalies
    state["messages"].append(f"Analysis complete. Status: {state['status']}")

    return state


def build_sentinel_graph():
    """
    Builds the LangGraph for the Sentinel Agent.
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("monitor", monitor_node)
    workflow.add_node("analyze", analyze_node)

    workflow.set_entry_point("monitor")
    workflow.add_edge("monitor", "analyze")
    workflow.add_edge("analyze", END)

    return workflow.compile()
