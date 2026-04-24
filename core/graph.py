# core/graph.py
# What it contains: The LangGraph StateGraph definition — the "brain wiring" of the agentic pipeline.
# Why it is important: This defines HOW agents are connected, the order they execute, and the
#   conditional routing logic (e.g., skip Researcher if Scanner is already confident).
# Connectivity: Called by core/llm_service.py to run the full pipeline. Uses agents from core/agents.py.

import logging

from langgraph.graph import StateGraph, END

from core.agent_state import FraudAnalysisState
from core.agents import scanner_agent, researcher_agent, reasoner_agent

logger = logging.getLogger(__name__)


def _route_after_scanner(state: FraudAnalysisState) -> str:
    """
    Conditional routing after Scanner Agent:
    - If Scanner is highly confident (very high or very low risk) → skip to Reasoner
    - If Scanner found things worth investigating → route to Researcher
    """
    next_agent = state.get("next_agent", "researcher")
    logger.info(f"📡 Router: Scanner recommends → {next_agent}")
    return next_agent


def build_fraud_detection_graph() -> StateGraph:
    """
    Build and compile the fraud detection agent graph.

    Flow:
        START → Scanner → [Router] → Researcher → Reasoner → END
                                   ↘ Reasoner → END  (fast path)
    """
    # Create the graph with our shared state
    graph = StateGraph(FraudAnalysisState)

    # ── Add agent nodes ────────────────────────────────────────────
    graph.add_node("scanner", scanner_agent)
    graph.add_node("researcher", researcher_agent)
    graph.add_node("reasoner", reasoner_agent)

    # ── Define edges ───────────────────────────────────────────────

    # Always start with the Scanner
    graph.set_entry_point("scanner")

    # After Scanner → conditional routing
    graph.add_conditional_edges(
        "scanner",
        _route_after_scanner,
        {
            "researcher": "researcher",
            "reasoner": "reasoner",
        },
    )

    # After Researcher → always go to Reasoner
    graph.add_edge("researcher", "reasoner")

    # After Reasoner → done
    graph.add_edge("reasoner", END)

    # ── Compile ────────────────────────────────────────────────────
    compiled = graph.compile()
    logger.info("✅ Fraud detection agent graph compiled successfully")

    return compiled


# Pre-compile the graph at module level for reuse
fraud_detection_graph = build_fraud_detection_graph()
