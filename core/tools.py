# core/tools.py
# What it contains: All tool functions that agents can invoke during fraud analysis.
# Why it is important: Tools are the "hands" of the agents — they perform concrete actions
#   like extracting URLs, querying the scam database, or checking URL safety.
# Connectivity: Imported by core/agents.py and bound to specific agents.

import re
import json
import logging
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy import select

from core.database import SessionLocal
from models.db_models import KnownScam

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  SCANNER AGENT TOOLS — Fast, deterministic first-pass checks
# ═══════════════════════════════════════════════════════════════════

@tool
def extract_urls(text: str) -> str:
    """
    Extract all URLs from a text message.
    Returns a JSON list of URLs found in the text.
    Use this to identify any links that need safety verification.
    """
    url_pattern = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+|'
        r'www\.[^\s<>"{}|\\^`\[\]]+|'
        r'[a-zA-Z0-9][-a-zA-Z0-9]*\.(com|org|net|in|co\.in|io|xyz|info|biz|tk|ml|ga|cf|gq|top|loan|click|link|win|bid|racing|review|trade|party|science|cricket|download|accountant|date|faith|stream|gdn|men|work)/[^\s]*',
        re.IGNORECASE,
    )
    urls = url_pattern.findall(text) if not url_pattern.groups else [m.group() for m in url_pattern.finditer(text)]
    # Flatten tuples from capture groups
    if urls and isinstance(urls[0], tuple):
        urls = [u[0] for u in urls]

    # Re-extract cleanly
    full_urls = [m.group() for m in re.finditer(
        r'https?://[^\s<>"{}|\\^`\[\]]+|www\.[^\s<>"{}|\\^`\[\]]+',
        text, re.IGNORECASE
    )]
    logger.info(f"Extracted {len(full_urls)} URLs from message")
    return json.dumps(full_urls)


@tool
def lookup_known_scams(text: str) -> str:
    """
    Check the known scam database for patterns matching this text.
    Returns a JSON list of matching scam records with category and severity.
    Use this to identify if the message matches any previously reported scams.
    """
    db = SessionLocal()
    try:
        stmt = select(KnownScam)
        known_scams = db.execute(stmt).scalars().all()

        matches = []
        text_lower = text.lower()
        for scam in known_scams:
            if scam.pattern_text.lower() in text_lower:
                matches.append({
                    "pattern": scam.pattern_text,
                    "category": scam.category,
                    "severity": scam.severity,
                    "source": scam.source,
                })
        logger.info(f"Found {len(matches)} known scam matches")
        return json.dumps(matches)
    except Exception as e:
        logger.error(f"Error querying known scams: {e}")
        return json.dumps([])
    finally:
        db.close()


@tool
def pattern_match(text: str) -> str:
    """
    Analyze text for common fraud/scam linguistic patterns using rule-based detection.
    Returns a JSON list of pattern flags found (e.g., urgency language, money requests).
    Use this for quick heuristic analysis of the message.
    """
    flags = []
    text_lower = text.lower()

    # Urgency indicators
    urgency_phrases = [
        "act now", "urgent", "immediately", "last chance", "expires today",
        "limited time", "don't delay", "hurry", "right away", "asap",
        "within 24 hours", "within 2 hours", "time is running out",
    ]
    for phrase in urgency_phrases:
        if phrase in text_lower:
            flags.append(f"URGENCY: '{phrase}' detected")

    # Money / financial pressure
    money_phrases = [
        "send money", "transfer funds", "pay now", "payment required",
        "bank account", "credit card", "bitcoin", "crypto", "upi",
        "google pay", "phonepe", "paytm", "wire transfer", "western union",
        "gift card", "itunes card", "amazon card",
    ]
    for phrase in money_phrases:
        if phrase in text_lower:
            flags.append(f"FINANCIAL_PRESSURE: '{phrase}' detected")

    # Impersonation indicators
    impersonation_phrases = [
        "from your bank", "rbi", "income tax", "aadhaar", "pan card",
        "government", "police", "customs", "court order", "legal action",
        "account suspended", "account blocked", "kyc update", "kyc verification",
        "sbi", "hdfc", "icici", "axis bank",
    ]
    for phrase in impersonation_phrases:
        if phrase in text_lower:
            flags.append(f"IMPERSONATION: '{phrase}' detected — possible authority impersonation")

    # Suspicious link patterns
    if re.search(r'bit\.ly|tinyurl|t\.co|goo\.gl|short\.link|cutt\.ly', text_lower):
        flags.append("SUSPICIOUS_LINK: URL shortener detected — may be hiding malicious destination")

    # Prize / lottery scams
    prize_phrases = [
        "congratulations", "you have won", "you've won", "lottery", "prize",
        "lucky winner", "selected winner", "claim your", "free gift",
    ]
    for phrase in prize_phrases:
        if phrase in text_lower:
            flags.append(f"PRIZE_SCAM: '{phrase}' detected — possible lottery/prize scam")

    # OTP / credential harvesting
    otp_phrases = [
        "share otp", "send otp", "verify otp", "enter otp", "share your pin",
        "share password", "confirm password", "verify your identity",
    ]
    for phrase in otp_phrases:
        if phrase in text_lower:
            flags.append(f"CREDENTIAL_HARVEST: '{phrase}' detected — possible OTP/credential theft")

    logger.info(f"Pattern matching found {len(flags)} flags")
    return json.dumps(flags)


# ═══════════════════════════════════════════════════════════════════
#  RESEARCHER AGENT TOOLS — Deep investigation
# ═══════════════════════════════════════════════════════════════════

@tool
def check_url_safety(url: str) -> str:
    """
    Check if a URL is safe, suspicious, or malicious.
    Returns a JSON object with the URL, risk_level, and reason.
    Use this to investigate URLs extracted from a message.

    NOTE: This is currently a heuristic-based check. In production,
    integrate Google Safe Browsing API or VirusTotal for real lookups.
    """
    risk_level = "safe"
    reasons = []

    url_lower = url.lower()

    # Check for URL shorteners
    shorteners = ["bit.ly", "tinyurl", "t.co", "goo.gl", "short.link", "cutt.ly", "is.gd", "v.gd"]
    if any(s in url_lower for s in shorteners):
        risk_level = "suspicious"
        reasons.append("URL shortener detected — may hide malicious destination")

    # Check for suspicious TLDs
    suspicious_tlds = [".tk", ".ml", ".ga", ".cf", ".gq", ".top", ".xyz", ".loan", ".click",
                       ".link", ".win", ".bid", ".racing", ".review", ".trade", ".party",
                       ".science", ".cricket", ".download", ".accountant", ".date", ".faith",
                       ".stream", ".gdn", ".men", ".work"]
    if any(url_lower.endswith(tld) or tld + "/" in url_lower for tld in suspicious_tlds):
        risk_level = "malicious"
        reasons.append(f"Suspicious TLD commonly used in scam websites")

    # Check for IP address URLs
    if re.search(r'https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', url_lower):
        risk_level = "suspicious"
        reasons.append("URL uses raw IP address instead of domain — suspicious")

    # Check for homograph / typosquatting patterns
    known_brands = ["google", "facebook", "amazon", "apple", "microsoft", "paypal",
                    "netflix", "instagram", "whatsapp", "paytm", "phonepe", "gpay"]
    for brand in known_brands:
        # Check for close-but-not-exact matches (e.g., go0gle, amaz0n)
        if brand not in url_lower and re.search(
            brand.replace("o", "[o0]").replace("l", "[l1]").replace("a", "[a@]"),
            url_lower
        ):
            risk_level = "malicious"
            reasons.append(f"Possible typosquatting of '{brand}'")

    if not reasons:
        reasons.append("No immediate red flags detected")

    result = {"url": url, "risk_level": risk_level, "reasons": reasons}
    logger.info(f"URL safety check for {url}: {risk_level}")
    return json.dumps(result)


@tool
def search_web_for_scam_reports(query: str) -> str:
    """
    Search the web for scam reports related to a phone number, URL, or message pattern.
    Returns a JSON list of relevant findings.
    Use this to check if other people have reported similar scam attempts.

    NOTE: This is currently a stub. In production, integrate a real search API
    like Tavily, SerpAPI, or Google Custom Search.
    """
    # Stub implementation — returns a realistic-looking empty result
    logger.info(f"Web search stub called for query: {query}")
    return json.dumps({
        "query": query,
        "results": [],
        "note": "Web search is currently in stub mode. Integrate Tavily or SerpAPI for real results.",
    })


@tool
def check_sender_reputation(sender_id: str) -> str:
    """
    Check the reputation of a sender (phone number or email) against known bad actors.
    Returns a JSON object with reputation score and any past reports.
    Use this when a sender_id is provided to check if they are a known scammer.

    NOTE: This is currently a heuristic check. In production, integrate with
    telecom APIs or crowd-sourced scam databases like Truecaller API.
    """
    if not sender_id:
        return json.dumps({"sender_id": None, "reputation": "unknown", "reason": "No sender ID provided"})

    # Check against DB for past fraud from this sender
    db = SessionLocal()
    try:
        from models.db_models import ScanRecord
        stmt = select(ScanRecord).where(
            ScanRecord.sender_id == sender_id,
            ScanRecord.is_fraud == True,
        )
        past_frauds = db.execute(stmt).scalars().all()

        if len(past_frauds) >= 3:
            reputation = "known_scammer"
            reason = f"This sender has {len(past_frauds)} previous fraud reports in our database"
        elif len(past_frauds) >= 1:
            reputation = "suspicious"
            reason = f"This sender has {len(past_frauds)} previous fraud report(s) in our database"
        else:
            reputation = "unknown"
            reason = "No prior fraud reports found for this sender"

        result = {
            "sender_id": sender_id,
            "reputation": reputation,
            "past_fraud_count": len(past_frauds),
            "reason": reason,
        }
        logger.info(f"Sender reputation check for {sender_id}: {reputation}")
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error checking sender reputation: {e}")
        return json.dumps({"sender_id": sender_id, "reputation": "unknown", "reason": str(e)})
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
#  Tool Collections — grouped for binding to agents
# ═══════════════════════════════════════════════════════════════════

SCANNER_TOOLS = [extract_urls, lookup_known_scams, pattern_match]
RESEARCHER_TOOLS = [check_url_safety, search_web_for_scam_reports, check_sender_reputation]
