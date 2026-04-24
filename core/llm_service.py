# core/llm_service.py
# What it contains: The main entry point for fraud analysis — invokes the agentic pipeline.
# Why it is important: This is the bridge between the API routes and the LangGraph agent system.
#   It initializes the graph, feeds in the user's message, and returns structured results.
# Connectivity: Called by api/routes.py. Invokes the agent graph from core/graph.py.

import json
import logging

from core.config import Config
from core.graph import fraud_detection_graph

logger = logging.getLogger(__name__)


async def analyze_text_for_fraud(text: str, sender_id: str | None = None) -> dict:
    """
    Run the full agentic fraud analysis pipeline.

    This invokes the LangGraph multi-agent system:
      Scanner Agent → [conditional] → Researcher Agent → Reasoner Agent

    Args:
        text: The suspicious message text to analyze.
        sender_id: Optional phone number or email of the sender.

    Returns:
        A dictionary containing the fraud verdict, confidence, reasoning,
        evidence summary, agent trace, and tools used.
    """
    if not Config.GEMINI_API_KEY:
        logger.error("Attempted to analyze fraud but GEMINI_API_KEY is missing.")
        raise ValueError("AI configuration is missing. Cannot perform fraud check.")

    logger.info(f"🚀 Starting agentic fraud analysis pipeline...")

    # Build the initial state for the graph
    initial_state = {
        "message_text": text,
        "sender_id": sender_id,
        "urls_found": [],
        "known_scam_matches": [],
        "pattern_flags": [],
        "scanner_risk_score": 0.0,
        "url_safety_results": [],
        "web_search_results": [],
        "sender_reputation": None,
        "is_fraud": False,
        "confidence": 0.0,
        "reasoning": "",
        "evidence_summary": "",
        "messages": [],
        "next_agent": "researcher",
        "audit_log": [],
        "tools_used": [],
    }

    try:
        # Invoke the compiled LangGraph
        final_state = await fraud_detection_graph.ainvoke(initial_state)

        # Build the URL risk level from safety results
        url_risk_level = None
        url_safety = final_state.get("url_safety_results", [])
        if url_safety:
            risk_levels = [r.get("risk_level", "safe") for r in url_safety]
            if "malicious" in risk_levels:
                url_risk_level = "malicious"
            elif "suspicious" in risk_levels:
                url_risk_level = "suspicious"
            else:
                url_risk_level = "safe"

        # Build agent trace for the response (excluding raw LLM messages)
        agent_trace = final_state.get("audit_log", [])

        result = {
            "text_analyzed": text,
            "sender_id": sender_id,
            "is_fraud": bool(final_state.get("is_fraud", False)),
            "confidence": float(final_state.get("confidence", 0.0)),
            "reasoning": str(final_state.get("reasoning", "Analysis failed.")),
            "evidence_summary": str(final_state.get("evidence_summary", "")),
            "urls_found": final_state.get("urls_found", []),
            "url_risk_level": url_risk_level,
            "agent_trace": agent_trace,
            "tools_used": list(set(final_state.get("tools_used", []))),
        }

        verdict = "🚨 FRAUD" if result["is_fraud"] else "✅ SAFE"
        logger.info(
            f"🏁 Pipeline complete: {verdict} "
            f"(confidence: {result['confidence']:.2f}, "
            f"tools: {len(result['tools_used'])}, "
            f"steps: {len(agent_trace)})"
        )

        return result

    except Exception as e:
        logger.error(f"Error in agentic fraud analysis pipeline: {str(e)}")
        raise
