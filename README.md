# 🌿 Sativus AI

> **Sativus AI** is your conversational plant doctor and nature explorer, powered entirely by Gemini 2.0. Whether you're trying to save a dying houseplant or identifying a weird bug on your hike, Sativus is right there with you, talking to you in real-time.

Built as a submission for the **Gemini Live Agent Challenge**, Sativus AI uses the bleeding-edge Gemini Live API to bring you completely native, uninterrupted voice conversations. It feels less like talking to a bot and more like having David Attenborough or an expert botanist standing right next to you!

## ✨ Features

- **🏥 Plant Doctor Mode:** Point your camera at any plant. Sativus instantly identifies it, diagnoses what's wrong (if anything), and gives you step-by-step treatment plans.
- **🔭 Nature Explorer Mode:** Identify birds, insects, and fungi while hiking. Sativus shares fun facts and conservation statuses.
- **🎙️ Real-Time Gemini Voice:** Engage in full, two-way voice conversations with the AI. You can even interrupt it mid-sentence (barge-in) if you need quick clarity!
- **🌤️ Context-Aware:** Sativus automatically fetches your local weather to give you accurate advice. It knows exactly what you scanned previously and naturally carries the conversation smoothly.
- **💧 Smart Reminders:** Tells you exactly when to water your plants.
- **📱 Gorgeous UI:** A lush, interactive interface wrapped in smooth glassmorphism, completely responsive and perfect for mobile edge-testing.

## 🚀 How to Run It Locally

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/sativus-ai.git
   cd sativus-ai
   ```

2. **Set up the backend:**
   Navigate into the repository and install the dependencies.
   ```bash
   pip install -r requirements.txt
   ```

3. **Add your Gemini API Key:**
   Rename `.env.example` to `.env` inside the `backend` folder and paste in your Gemini API Key. (You can grab your key from [Google AI Studio](https://aistudio.google.com/)).
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```

4. **Start the server:**
   Navigate into the `backend` folder and start the FastAPI server.
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

5. **Open the App!**
   Just double-click `frontend/index.html` in your browser (or serve it through VSCode Live Server) and you're good to go!

## 🛠️ Built With

- **Google GenAI SDK** (Gemini 2.0 Flash & Live API)
- **FastAPI** & **WebSockets** for lightning-fast audio streaming
- **Vanilla JS + CSS** (No heavy frontend frameworks needed for a stunning UI!)
- **Open-Meteo API** (Weather Context)

## 📜 License

This project is open-source and available under the **MIT License**. Build something awesome with it! Feel free to fork and improve the project!
