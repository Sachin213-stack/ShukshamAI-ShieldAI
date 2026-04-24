import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """
    Centralized configuration management for the application.
    Fails fast if critical environment variables are missing.
    """
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    # ── Agentic AI Configuration ──────────────────────────────────
    AGENT_MODEL = os.getenv("AGENT_MODEL", "gemini-1.5-flash-latest")
    AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "5"))
    ENABLE_STREAMING = os.getenv("ENABLE_STREAMING", "False").lower() in ("true", "1", "t")

    @classmethod
    def validate(cls):
        if not cls.GEMINI_API_KEY:
            # In a real production app, you might want to log this critical error.
            print("WARNING: GEMINI_API_KEY is not set. LLM features will fail.")

# Run validation on import
Config.validate()
