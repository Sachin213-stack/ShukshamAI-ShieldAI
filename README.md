# 🛡️ Fraud Detection Agentic API

A production-ready, multi-agent AI system designed to detect fraud, scams, and phishing attempts with high precision. Built using **LangGraph**, **FastAPI**, and **Google Gemini**, this system mimics human analysis by orchestrating specialized agents to scan, research, and reason through suspicious activities.

## 🚀 Key Features

- **Agentic Intelligence**: Uses a multi-agent pipeline (Scanner → Researcher → Reasoner) for explainable fraud analysis.
- **Real-Time Mobile Protection**: Includes a Native Android App that actively monitors system notifications (SMS, WhatsApp) in the background to catch fraud before you click.
- **Tool-Augmented**: Agents can perform real-time web searches and database lookups to verify claims.
- **Explainable AI**: Provides detailed reasoning for why a particular event was flagged as fraudulent.
- **Modern Tech Stack**: Built with FastAPI for high performance, LangGraph for complex workflows, and Capacitor for native mobile delivery.
- **Flexible Deployment**: Supports local development with Uvicorn and is structured for production scalability.

## 🛠️ Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Backend)
- **Frontend & Mobile**: HTML5/Vanilla JS Mobile UI, wrapped in native Android with [Capacitor](https://capacitorjs.com/).
- **Agent Orchestration**: [LangGraph](https://langchain-ai.github.io/langgraph/)
- **LLM**: [Google Gemini](https://ai.google.dev/) (via `langchain-google-genai`)
- **Database**: SQLAlchemy (SQLite for local, extensible to PostgreSQL)
- **Utilities**: Pandas, Scikit-learn, BeautifulSoup4

## 📂 Project Structure

```text
fraud_detection_app/
├── android/         # Native Android project (Capacitor)
├── api/             # API routes and request/response schemas
├── core/            # The "brain" - Agent logic, LLM services, and database config
│   ├── graph.py     # LangGraph workflow definition
│   ├── agents.py    # Individual agent logic (Scanner, Researcher, Reasoner)
│   ├── tools.py     # Custom tools for agents (Search, Database)
│   ├── database.py  # Database initialization and sessions
│   └── config.py    # Configuration and environment variable management
├── data/            # Local data storage (SQLite db, CSVs)
├── frontend/        # Mobile-first Web UI (HTML, CSS, JS)
├── models/          # Pydantic and SQLAlchemy models
├── tests/           # Automated test suite
├── main.py          # Application entry point
├── requirements.txt # Python dependencies
└── .env             # Environment secrets (API keys)
```

## ⚙️ Setup & Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd fraud_detection_app
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```
Add your **Google Gemini API Key** and any other required keys.

### 5. Run the Application
```bash
python main.py
```
The server will start at `http://127.0.0.1:8000`.

## 📖 API Documentation

Once the server is running, you can access the interactive Swagger documentation at:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## 📱 Mobile App Setup (Android)

To use the real-time notification scanner on your Android phone:
1. Ensure the Python backend is running locally and your phone is on the same Wi-Fi.
2. Build the APK using Android Studio by opening the `android/` directory and selecting **Build > Build APK(s)**.
3. Install `app-debug.apk` on your phone.
4. Open the app, grant **Notification Access**, and set your API Base URL to your PC's IP address (e.g., `http://192.168.1.100:8000/api`).

## 🤖 Agentic Pipeline

1. **Scanner**: Identifies potential red flags in the input data (SMS, Email, Call transcript).
2. **Researcher**: Uses external tools (web search, historical data) to verify the suspicious elements.
3. **Reasoner**: Aggregates findings from the Scanner and Researcher to produce a final risk score and a detailed explanation.

---

Built with ❤️ for a safer digital world.
