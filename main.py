import logging
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router
from core.database import init_db

# Configure structured logging for production
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Modern lifespan handler (replaces deprecated @app.on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    logger.info("Fraud Detection Agentic API Server has started successfully.")
    logger.info("Architecture: Multi-Agent (Scanner → Researcher → Reasoner)")
    yield
    # Shutdown
    logger.info("Fraud Detection API Server is shutting down.")


# Initialize the main FastAPI application
app = FastAPI(
    title="Fraud Detection Agentic API",
    description=(
        "Production-ready agentic API for detecting fraud, scams, and phishing attempts. "
        "Uses a multi-agent pipeline (Scanner → Researcher → Reasoner) powered by "
        "LangGraph + Google Gemini for explainable, tool-augmented fraud analysis."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# Add CORS Middleware so frontends (React, Mobile Apps) can connect securely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, change this to your specific frontend domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect the routes from our api/ folder
app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    """Redirect to documentation or show a welcome message."""
    return {
        "message": "Welcome to the Fraud Detection Agentic API",
        "documentation": "/docs",
        "api_root": "/api"
    }

if __name__ == "__main__":
    logger.info("Starting Fraud Detection Agentic Server...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
