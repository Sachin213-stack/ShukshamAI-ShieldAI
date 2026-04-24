# core/agent_state.py
# What it contains: The shared state definition that flows between all agents in the graph.
# Why it is important: This TypedDict is the "memory" of the agentic pipeline — every agent
#   reads from it and writes back to it as the investigation progresses.
# Connectivity: Used by core/agents.py (agent nodes), core/graph.py (graph definition),
#   and core/llm_service.py (graph invocation).

from __future__ import annotations

from typing import TypedDict, Annotated
from datetime import datetime, timezone

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentStepLog(TypedDict):
    """A single logged step in the agent pipeline for audit/explainability."""
    agent_name: str
    action: str
    observation: str
    timestamp: str


def merge_lists(left: list, right: list) -> list:
    """Reducer that merges two lists (used by Annotated fields)."""
    return left + right


class FraudAnalysisState(TypedDict):
    """
    Shared state for the fraud analysis agentic pipeline.

    Every key here is accessible by all agent nodes. LangGraph manages
    state transitions automatically — agents only need to return the
    keys they want to update.
    """

    # ── Input ──────────────────────────────────────────────────────
    message_text: str
    sender_id: str | None

    # ── Scanner Agent outputs ──────────────────────────────────────
    urls_found: list[str]
    known_scam_matches: list[dict]
    pattern_flags: list[str]
    scanner_risk_score: float  # 0.0 – 1.0, quick heuristic score

    # ── Researcher Agent outputs ───────────────────────────────────
    url_safety_results: list[dict]
    web_search_results: list[dict]
    sender_reputation: dict | None

    # ── Reasoner Agent outputs ─────────────────────────────────────
    is_fraud: bool
    confidence: float
    reasoning: str
    evidence_summary: str

    # ── Orchestration ──────────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]
    next_agent: str  # routing decision: "researcher" | "reasoner"

    # ── Audit Trail ────────────────────────────────────────────────
    audit_log: Annotated[list[AgentStepLog], merge_lists]
    tools_used: Annotated[list[str], merge_lists]
