import logging
from typing import Dict, List, Any

from langgraph.graph import StateGraph, END

logger = logging.getLogger("n7-striker.agent-runtime.graph")


class AgentState(Dict):
    """
    Represents the state of the Striker Agent.
    """
    command: Dict[str, Any]
    action_plan: List[str]
    execution_result: Dict[str, Any]
    status: str


def receive_command_node(state: AgentState) -> AgentState:
    """
    Simulates receiving or processing a command queue.
    """
    logger.info("Striker: Checking for commands...")
    # In a real app, this might pull from NATS or an internal queue
    # For simulation, we check if a command is already present or mock one occasionally

    current_command = state.get("command", {})
    if not current_command:
        # Mock receiving a command
        import random
        if random.random() < 0.1:  # 10% chance to get a command
            state["command"] = {"type": "restart_service", "service": "web-server"}
            state["status"] = "command_received"
            state["messages"] = ["Command received: restart_service"]
        else:
            state["status"] = "idle"

    return state


def execute_action_node(state: AgentState) -> AgentState:
    """
    Executes the action if a command exists.
    """
    if state.get("status") == "command_received":
        command = state.get("command")
        logger.info(f"Striker: Executing command {command}")

        # Simulate execution
        state["execution_result"] = {"success": True, "details": "Service restarted"}
        state["status"] = "executed"

        # Clear command
        state["command"] = {}

    return state


def build_striker_graph():
    """
    Builds the LangGraph for the Striker Agent.
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("receive_command", receive_command_node)
    workflow.add_node("execute_action", execute_action_node)

    workflow.set_entry_point("receive_command")

    # Conditional edge could be used here, but for simplicity:
    workflow.add_edge("receive_command", "execute_action")
    workflow.add_edge("execute_action", END)

    return workflow.compile()
