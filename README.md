# Sativus AI 🌿

**Sativus AI** is a state-of-the-art multimodal plant doctor and nature explorer. Powered by Groq's high-speed vision models, it provides instant identification and health assessment of plants, animals, and fungi through a sleek, bento-style interface.

Now featuring **Real-time Voice Interaction** for a hands-free, conversational experience.

---

## ✨ Key Features

- **🏥 Plant Doctor Mode**: Deep analysis of plant health, providing instant diagnoses and step-by-step treatment plans.
- **🔭 Nature Explorer Mode**: Learn about the wild—identify birds, insects, and fungi with a focus on conservation and natural history.
- **🎙️ Live Voice (New)**: Low-latency voice interaction powered by **Deepgram** (STT), **Groq** (LLM), and **ElevenLabs** (TTS).
- **💧 Smart Reminders**: Deterministic parsing of watering schedules with persistent local storage.
- **📔 Field Journal**: A historical log of your discoveries, cached locally for fast retrieval.
- **📱 PWA Ready**: Install Sativus as a standalone app on your mobile device for outdoor use.

## 🛠️ Technology Stack

- **Backend**: Python / FastAPI / WebSockets
- **Intelligence**: Groq Llama 3.3 70B (Vision & Text)
- **Voice**: Deepgram (Streaming STT) & ElevenLabs (Streaming TTS)
- **Frontend**: Vanilla JavaScript / HTML5 / CSS3 (No heavy frameworks, maximum speed)
- **Ecosystem**: iNaturalist API (Global Observations), Open-Meteo (Contextual weather)

---

## 🚀 Quick Start

### 1. Prerequisites
Ensure you have Python 3.10+ installed.

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/tazwaryayyyy/Sativus-ai.git
cd Sativus-ai

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Copy the template and add your API keys:
```bash
cp .env.example backend/.env
```
Edit `backend/.env` with your credentials for Groq, Deepgram, and ElevenLabs.

### 4. Running Locally
```bash
# Start the FastAPI server
uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```
Open [http://localhost:8080](http://localhost:8080) in your browser.

---

## 🏗️ Architecture

```text
├── backend/
│   ├── main.py          # FastAPI application & Voice Orchestrator
│   └── reminders.json   # Local database for plant care
├── frontend/
│   ├── index.html       # Monolithic UI & Client-side logic
│   ├── manifest.json    # PWA configuration
│   └── sw.js            # Service worker for offline caching
└── scripts/             # Utility and testing scripts
```

## 🔒 Security & Performance

- **Production Middleware**: Includes restricted CORS, request size limits (10MB), and robust security headers (HSTS, CSP-ready).
- **Efficiency**: Optimized image resizing to prevent OOM errors in memory-constrained environments (e.g., free tier deployments).
- **Observability**: Built-in `/metrics` endpoint tracking API latency and session success rates.

## 📜 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---
*Made with ❤️ by Tazwar Ahnaf Enan*
