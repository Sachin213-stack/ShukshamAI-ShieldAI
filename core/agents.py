# core/agents.py
# What it contains: Agent node definitions for the LangGraph fraud analysis pipeline.
# Why it is important: Each agent is a specialized LLM-powered node with its own system prompt
#   and tool set. Together they form a multi-agent investigation team.
# Connectivity: Called by core/graph.py as graph nodes. Uses tools from core/tools.py.

import json
import logging
from datetime import datetime, timezone

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from core.config import Config
from core.agent_state import FraudAnalysisState, AgentStepLog
from core.tools import SCANNER_TOOLS, RESEARCHER_TOOLS

logger = logging.getLogger(__name__)


def _extract_text(content) -> str:
    """Helper to extract string content from LangChain response (handles strings or lists of parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Extract text from parts (often dicts with 'text' key or just objects)
        text_parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
            elif isinstance(part, str):
                text_parts.append(part)
            else:
                # Fallback for other part types (like images or tool calls)
                pass
        return " ".join(text_parts)
    return str(content)


def _get_llm(tools: list | None = None) -> ChatGoogleGenerativeAI:
    """Create a Gemini LLM instance, optionally with tools bound."""
    llm = ChatGoogleGenerativeAI(
        model=Config.AGENT_MODEL,
        google_api_key=Config.GEMINI_API_KEY,
        temperature=0.1,  # Low temperature for consistent, analytical responses
        convert_system_message_to_human=True,
    )
    if tools:
        llm = llm.bind_tools(tools)
    return llm


# ═══════════════════════════════════════════════════════════════════
#  SCANNER AGENT — Fast first-pass analysis
# ═══════════════════════════════════════════════════════════════════

SCANNER_SYSTEM_PROMPT = """You are the **Scanner Agent** in a fraud detection pipeline.

Your job is to perform a FAST first-pass analysis of a suspicious message. You have access to
three tools — USE ALL OF THEM on every message:

1. **extract_urls** — Extract any URLs from the message
2. **lookup_known_scams** — Check if the message matches known scam patterns in our database
3. **pattern_match** — Run rule-based pattern detection for fraud indicators

After using all tools, provide a quick risk assessment:
- Summarize what you found
- Assign a preliminary risk score (0.0 = safe, 1.0 = definitely fraud)
- Recommend whether the **Researcher Agent** should investigate further, or if the evidence
  is already conclusive enough to go straight to the **Reasoner Agent**

Format your final summary as JSON:
{
    "scanner_risk_score": <float>,
    "needs_research": <boolean>,
    "summary": "<your analysis summary>"
}
"""


async def scanner_agent(state: FraudAnalysisState) -> dict:
    """
    Scanner Agent node — performs fast first-pass analysis using deterministic tools.
    """
    logger.info("🔍 Scanner Agent starting analysis...")
    llm = _get_llm(tools=SCANNER_TOOLS)

    messages = [
        SystemMessage(content=SCANNER_SYSTEM_PROMPT),
        HumanMessage(content=f"Analyze this message for fraud:\n\n\"{state['message_text']}\""),
    ]

    # Let the agent use tools iteratively
    urls_found = []
    known_scam_matches = []
    pattern_flags = []
    tools_used = []
    audit_entries = []

    # Run the tool-calling loop (max 5 iterations for safety)
    for i in range(Config.AGENT_MAX_ITERATIONS):
        response = await llm.ainvoke(messages)
        messages.append(response)

        # Check if the LLM wants to call tools
        if response.tool_calls:
            from langchain_core.messages import ToolMessage

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tools_used.append(tool_name)

                logger.info(f"  Scanner calling tool: {tool_name}({tool_args})")

                # Execute the tool
                tool_fn = {t.name: t for t in SCANNER_TOOLS}.get(tool_name)
                if tool_fn:
                    result = await tool_fn.ainvoke(tool_args)
                    messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

                    # Parse and store tool results
                    try:
                        parsed = json.loads(result)
                        if tool_name == "extract_urls":
                            urls_found = parsed if isinstance(parsed, list) else []
                        elif tool_name == "lookup_known_scams":
                            known_scam_matches = parsed if isinstance(parsed, list) else []
                        elif tool_name == "pattern_match":
                            pattern_flags = parsed if isinstance(parsed, list) else []
                    except json.JSONDecodeError:
                        pass

                    audit_entries.append({
                        "agent_name": "Scanner",
                        "action": f"Called {tool_name}",
                        "observation": str(result)[:500],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
        else:
            # No more tool calls — agent is done
            break

    # Parse the final response for routing decision
    final_text = _extract_text(response.content)
    scanner_risk_score = 0.5
    needs_research = True

    try:
        # Try to extract JSON from the response
        json_match = final_text
        if "```json" in json_match:
            json_match = json_match.split("```json")[1].split("```")[0]
        elif "```" in json_match:
            json_match = json_match.split("```")[1].split("```")[0]

        parsed_response = json.loads(json_match.strip())
        scanner_risk_score = float(parsed_response.get("scanner_risk_score", 0.5))
        needs_research = bool(parsed_response.get("needs_research", True))
    except (json.JSONDecodeError, IndexError, ValueError):
        logger.warning("Scanner agent didn't return valid JSON summary, using defaults")

    # Determine next agent based on scanner analysis
    if not needs_research or scanner_risk_score >= 0.9 or scanner_risk_score <= 0.1:
        next_agent = "reasoner"
    else:
        next_agent = "researcher"

    audit_entries.append({
        "agent_name": "Scanner",
        "action": f"Completed analysis → routing to {next_agent}",
        "observation": f"Risk score: {scanner_risk_score}, URLs: {len(urls_found)}, "
                       f"Known matches: {len(known_scam_matches)}, Pattern flags: {len(pattern_flags)}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"🔍 Scanner Agent done. Risk: {scanner_risk_score}, Next: {next_agent}")

    return {
        "urls_found": urls_found,
        "known_scam_matches": known_scam_matches,
        "pattern_flags": pattern_flags,
        "scanner_risk_score": scanner_risk_score,
        "next_agent": next_agent,
        "messages": messages,
        "audit_log": audit_entries,
        "tools_used": tools_used,
    }


# ═══════════════════════════════════════════════════════════════════
#  RESEARCHER AGENT — Deep investigation
# ═══════════════════════════════════════════════════════════════════

RESEARCHER_SYSTEM_PROMPT = """You are the **Researcher Agent** in a fraud detection pipeline.

The Scanner Agent has already done an initial analysis and found things worth investigating.
Your job is to perform DEEP INVESTIGATION using your specialized tools:

1. **check_url_safety** — Check if URLs are safe, suspicious, or malicious (call once per URL)
2. **search_web_for_scam_reports** — Search the web for scam reports matching this message
3. **check_sender_reputation** — Look up the sender in our fraud database

You will receive the Scanner's findings as context. Focus your investigation on:
- Any URLs that were extracted (check each one)
- The sender ID if provided
- Search for similar scam reports online

After investigation, provide your findings as JSON:
{
    "investigation_summary": "<detailed findings>",
    "risk_escalation": <boolean — true if investigation found MORE risk than scanner estimated>,
    "key_evidence": ["<evidence point 1>", "<evidence point 2>"]
}
"""


async def researcher_agent(state: FraudAnalysisState) -> dict:
    """
    Researcher Agent node — performs deep investigation on flagged messages.
    """
    logger.info("🔬 Researcher Agent starting deep investigation...")
    llm = _get_llm(tools=RESEARCHER_TOOLS)

    # Build context from Scanner's findings
    context = (
        f"Original message: \"{state['message_text']}\"\n\n"
        f"Scanner found these URLs: {json.dumps(state.get('urls_found', []))}\n"
        f"Scanner found these known scam matches: {json.dumps(state.get('known_scam_matches', []))}\n"
        f"Scanner found these pattern flags: {json.dumps(state.get('pattern_flags', []))}\n"
        f"Scanner risk score: {state.get('scanner_risk_score', 0.5)}\n"
        f"Sender ID: {state.get('sender_id', 'Not provided')}"
    )

    messages = [
        SystemMessage(content=RESEARCHER_SYSTEM_PROMPT),
        HumanMessage(content=f"Investigate this flagged message:\n\n{context}"),
    ]

    url_safety_results = []
    web_search_results = []
    sender_reputation = None
    tools_used = []
    audit_entries = []

    # Run the tool-calling loop
    for i in range(Config.AGENT_MAX_ITERATIONS):
        response = await llm.ainvoke(messages)
        messages.append(response)

        if response.tool_calls:
            from langchain_core.messages import ToolMessage

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tools_used.append(tool_name)

                logger.info(f"  Researcher calling tool: {tool_name}({tool_args})")

                tool_fn = {t.name: t for t in RESEARCHER_TOOLS}.get(tool_name)
                if tool_fn:
                    result = await tool_fn.ainvoke(tool_args)
                    messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

                    try:
                        parsed = json.loads(result)
                        if tool_name == "check_url_safety":
                            url_safety_results.append(parsed)
                        elif tool_name == "search_web_for_scam_reports":
                            web_search_results.append(parsed)
                        elif tool_name == "check_sender_reputation":
                            sender_reputation = parsed
                    except json.JSONDecodeError:
                        pass

                    audit_entries.append({
                        "agent_name": "Researcher",
                        "action": f"Called {tool_name}",
                        "observation": str(result)[:500],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
        else:
            break

    audit_entries.append({
        "agent_name": "Researcher",
        "action": "Completed deep investigation → routing to Reasoner",
        "observation": f"URL checks: {len(url_safety_results)}, "
                       f"Web searches: {len(web_search_results)}, "
                       f"Sender checked: {sender_reputation is not None}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"🔬 Researcher Agent done. URL checks: {len(url_safety_results)}")

    return {
        "url_safety_results": url_safety_results,
        "web_search_results": web_search_results,
        "sender_reputation": sender_reputation,
        "messages": messages,
        "audit_log": audit_entries,
        "tools_used": tools_used,
    }


# ═══════════════════════════════════════════════════════════════════
#  REASONER AGENT — Final verdict synthesis
# ═══════════════════════════════════════════════════════════════════

REASONER_SYSTEM_PROMPT = """You are the **Reasoner Agent** — the final decision-maker in a fraud detection pipeline.

You receive ALL evidence collected by the Scanner and Researcher agents. Your job is to:
1. Synthesize all evidence into a coherent analysis
2. Make a FINAL determination: is this message fraudulent or legitimate?
3. Provide a clear, human-readable explanation of your reasoning
4. Assign a confidence score (0.0 = definitely safe, 1.0 = definitely fraud)

You must respond with ONLY a valid JSON object:
{
    "is_fraud": <boolean>,
    "confidence": <float between 0.0 and 1.0>,
    "reasoning": "<detailed human-readable explanation>",
    "evidence_summary": "<bullet-point summary of key evidence>"
}

Be PRECISE and BALANCED. Avoid both false positives (flagging legitimate messages) and
false negatives (missing actual scams). When in doubt, lean toward caution but explain
your uncertainty.
"""


async def reasoner_agent(state: FraudAnalysisState) -> dict:
    """
    Reasoner Agent node — synthesizes all evidence into a final verdict.
    No tools — pure LLM reasoning on the collected evidence.
    """
    logger.info("⚖️  Reasoner Agent synthesizing verdict...")
    llm = _get_llm()  # No tools — pure reasoning

    # Build comprehensive evidence brief
    evidence_brief = f"""
## Original Message
"{state['message_text']}"

## Sender
{state.get('sender_id', 'Unknown')}

## Scanner Agent Findings
- **Risk Score:** {state.get('scanner_risk_score', 'N/A')}
- **URLs Found:** {json.dumps(state.get('urls_found', []))}
- **Known Scam Matches:** {json.dumps(state.get('known_scam_matches', []))}
- **Pattern Flags:** {json.dumps(state.get('pattern_flags', []))}

## Researcher Agent Findings
- **URL Safety Results:** {json.dumps(state.get('url_safety_results', []))}
- **Web Search Results:** {json.dumps(state.get('web_search_results', []))}
- **Sender Reputation:** {json.dumps(state.get('sender_reputation'))}
"""

    messages = [
        SystemMessage(content=REASONER_SYSTEM_PROMPT),
        HumanMessage(content=f"Review all evidence and deliver your final verdict:\n\n{evidence_brief}"),
    ]

    audit_entries = []

    response = await llm.ainvoke(messages)
    final_text = _extract_text(response.content)

    # Parse the verdict
    is_fraud = False
    confidence = 0.0
    reasoning = "Analysis could not produce a clear determination."
    evidence_summary = ""

    try:
        clean_text = final_text
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0]
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].split("```")[0]

        parsed = json.loads(clean_text.strip())
        is_fraud = bool(parsed.get("is_fraud", False))
        confidence = float(parsed.get("confidence", 0.0))
        reasoning = str(parsed.get("reasoning", reasoning))
        evidence_summary = str(parsed.get("evidence_summary", ""))
    except (json.JSONDecodeError, IndexError, ValueError) as e:
        logger.warning(f"Reasoner didn't return valid JSON: {e}. Using raw response as reasoning.")
        reasoning = final_text
        # Fallback: use scanner risk score
        confidence = state.get("scanner_risk_score", 0.5)
        is_fraud = confidence >= 0.6

    audit_entries.append({
        "agent_name": "Reasoner",
        "action": "Delivered final verdict",
        "observation": f"is_fraud={is_fraud}, confidence={confidence}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    verdict = "🚨 FRAUD DETECTED" if is_fraud else "✅ LEGITIMATE"
    logger.info(f"⚖️  Reasoner Agent verdict: {verdict} (confidence: {confidence})")

    return {
        "is_fraud": is_fraud,
        "confidence": confidence,
        "reasoning": reasoning,
        "evidence_summary": evidence_summary,
        "messages": messages,
        "audit_log": audit_entries,
    }
