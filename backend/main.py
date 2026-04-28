from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Any
import logging
import requests
import base64
import binascii
import json
import os
import time
import threading
import re
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import httpx
import asyncio
import websockets
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

load_dotenv()

# ── SETUP ──
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.2-11b-vision-preview")
LIVE_VOICE_ENABLED = os.getenv("LIVE_VOICE_ENABLED", "false").lower() == "true"
LIVE_VOICE_PROVIDER = os.getenv("LIVE_VOICE_PROVIDER", "none").strip().lower()
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

logger = logging.getLogger("sativus")

app = FastAPI()

# ── SECURITY: RESTRICTED CORS ──
# Update these to your actual production domains for maximum safety
ALLOWED_ORIGINS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:3000",
    "https://sativus-ai.web.app",  # Example production origin
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if os.getenv("PROD") else ["*"],
    allow_methods=["GET", "POST"],  # Restrict methods
    allow_headers=["*"],
)

# ── SECURITY/OOM: REQUEST SIZE LIMIT ──


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    if request.method == "POST":
        cl = request.headers.get("content-length")
        if cl and int(cl) > 10 * 1024 * 1024:  # 10MB Limit
            return JSONResponse(status_code=413, content={"found": False, "error": "payload too large (max 10MB)"})
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(self), camera=(self)"
    if os.getenv("PROD"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _record_metric(name: str, delta: float = 1.0):
    with _metrics_lock:
        _metrics[name] = _metrics.get(name, 0) + delta


def _analyze_error(message: str, status_code: int, started_at: float):
    _record_metric("analyze_fail")
    _record_metric("analyze_latency_ms_sum",
                   (time.perf_counter() - started_at) * 1000)
    return JSONResponse(status_code=status_code, content={"found": False, "error": message})


# ══════════════════════════════════════════
# CACHE
# ══════════════════════════════════════════
_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 3600
REMINDERS_FILE = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "reminders.json")
_reminder_lock = threading.Lock()
_metrics_lock = threading.Lock()
_metrics = {
    "analyze_requests": 0,
    "analyze_success": 0,
    "analyze_fail": 0,
    "analyze_latency_ms_sum": 0.0,
    "live_sessions_started": 0,
    "live_sessions_completed": 0,
    "live_sessions_failed": 0,
}


def get_cached(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["timestamp"]) < CACHE_TTL:
            return entry["response"]
    return None


def set_cache(key, response):
    with _cache_lock:
        _cache[key] = {"response": response, "timestamp": time.time()}
        if len(_cache) > 100:
            oldest = min(_cache, key=lambda k: _cache[k]["timestamp"])
            del _cache[oldest]


def _load_reminders():
    if not os.path.exists(REMINDERS_FILE):
        return {}
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _save_reminders(reminders):
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, ensure_ascii=True, indent=2)


def schedule_to_days(schedule: str) -> int:
    if not schedule:
        return 7
    s = schedule.lower().strip()

    patterns = [
        (r"every\s+(\d+)\s*day", 1),
        (r"(\d+)\s*day", 1),
        (r"every\s+(\d+)\s*week", 7),
        (r"(\d+)\s*week", 7),
        (r"every\s+(\d+)\s*month", 30),
        (r"(\d+)\s*month", 30),
    ]
    for pat, factor in patterns:
        m = re.search(pat, s)
        if m:
            try:
                return max(1, min(60, int(m.group(1)) * factor))
            except ValueError:
                pass

    keyword_map = {
        "daily": 1,
        "every day": 1,
        "twice a week": 3,
        "weekly": 7,
        "every week": 7,
        "biweekly": 14,
        "every two weeks": 14,
        "fortnight": 14,
        "monthly": 30,
        "every month": 30,
    }
    for key, val in keyword_map.items():
        if key in s:
            return val
    return 7


def create_reminder_entry(user_id: str, plant_name: str, schedule: str):
    safe_user = (user_id or "default")[:64]
    clean_plant = "".join(
        ch for ch in plant_name[:50] if ch.isalnum() or ch in " -")
    clean_schedule = "".join(
        ch for ch in schedule[:50] if ch.isalnum() or ch in " -")
    days = schedule_to_days(clean_schedule)
    now = datetime.now(timezone.utc)
    due_dt = now + timedelta(days=days)
    record = {
        "plant_name": clean_plant,
        "watering_schedule": clean_schedule,
        "days_until_water": days,
        "created_at": now.isoformat(),
        "due_at": due_dt.isoformat(),
    }

    with _reminder_lock:
        reminders = _load_reminders()
        user_reminders = reminders.get(safe_user, [])
        user_reminders.append(record)
        reminders[safe_user] = user_reminders[-200:]
        _save_reminders(reminders)

    return record


def get_due_for_user(user_id: str):
    safe_user = (user_id or "default")[:64]
    now = datetime.now(timezone.utc)
    with _reminder_lock:
        reminders = _load_reminders().get(safe_user, [])

    due = []
    upcoming = []
    for entry in reminders:
        due_at_str = entry.get("due_at")
        if not due_at_str:
            continue
        try:
            due_at = datetime.fromisoformat(due_at_str)
        except ValueError:
            continue

        if due_at <= now:
            due.append(entry)
        elif due_at <= now + timedelta(days=2):
            upcoming.append(entry)

    return due, upcoming

# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════


def redact_location(location):
    if not location or not isinstance(location, dict):
        return None
    return {
        "lat": round(location.get("lat", 0), 2),
        "lng": round(location.get("lng", 0), 2)
    }


def get_observations(scientific_name):
    try:
        url = "https://api.inaturalist.org/v1/taxa"
        data = requests.get(
            url, params={"q": scientific_name, "per_page": 1}, timeout=5).json()
        if data.get("results"):
            return f"{data['results'][0].get('observations_count', 0):,}"
    except (requests.RequestException, json.JSONDecodeError, ValueError, TypeError, KeyError):
        pass
    return "0"


def call_groq_vision(image_bytes: bytes, prompt: str) -> str:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured")

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        },
                    },
                ],
            }
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=18,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"Invalid Groq response format: {e}") from e


def _extract_first_json_object(text: str):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return json.loads(text[start:end + 1])


def _parse_analysis_json(raw_text: str):
    cleaned = raw_text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return _extract_first_json_object(cleaned)


def _normalize_analysis_result(result: dict, mode: str):
    if not isinstance(result, dict):
        return {"found": False}
    found = bool(result.get("found"))
    common_name = str(result.get("common_name", "")).strip()
    if found and "unknown" in common_name.lower():
        found = False
    if not found:
        return {"found": False}

    category = str(result.get("category", "")).strip().lower()
    if mode == "doctor":
        allowed_categories = {"houseplant",
                              "succulent", "tree", "herb", "flower"}
        allowed_health = {"Healthy", "Sick", "Critical"}
        health_status = str(result.get(
            "health_status", "Healthy")).strip().title()
        if health_status not in allowed_health:
            health_status = "Healthy"
        if category not in allowed_categories:
            category = "houseplant"
        conservation = "Least Concern"
    else:
        allowed_categories = {"plant", "bird",
                              "insect", "fungi", "mammal", "reptile"}
        allowed_conservation = {"Least Concern",
                                "Vulnerable", "Endangered", "Invasive"}
        conservation = str(result.get("conservation_status",
                           "Least Concern")).strip().title()
        if conservation not in allowed_conservation:
            conservation = "Least Concern"
        health_status = ""
        if category not in allowed_categories:
            category = "plant"

    treatment_steps = result.get("treatment_steps") or []
    if not isinstance(treatment_steps, list):
        treatment_steps = []
    treatment_steps = [str(step).strip()
                       for step in treatment_steps if str(step).strip()][:6]

    confidence = result.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.75 if mode == "doctor" else 0.7
    confidence = max(0.0, min(1.0, confidence))

    alternatives = result.get("alternatives") or []
    if not isinstance(alternatives, list):
        alternatives = []
    alternatives = [str(x).strip()
                    for x in alternatives if str(x).strip()][:3]

    evidence_source = str(result.get(
        "evidence_source", "Groq + iNaturalist")).strip()[:80]

    return {
        "found": True,
        "common_name": common_name,
        "scientific_name": str(result.get("scientific_name", "")).strip(),
        "category": category,
        "health_status": health_status,
        "conservation_status": conservation,
        "diagnosis": str(result.get("diagnosis", "")).strip(),
        "story": str(result.get("story", "")).strip(),
        "treatment_steps": treatment_steps,
        "watering_schedule": str(result.get("watering_schedule", "")).strip(),
        "fun_fact": str(result.get("fun_fact", "")).strip(),
        "confidence": confidence,
        "alternatives": alternatives,
        "evidence_source": evidence_source,
    }

# ══════════════════════════════════════════
# REQUEST MODELS
# ══════════════════════════════════════════


class AnalyzeRequest(BaseModel):
    image: str
    mode: Optional[str] = "doctor"
    location: Optional[Any] = None


class ReminderRequest(BaseModel):
    plant_name: str
    watering_schedule: str
    user_id: str = "default"


class DueReminderRequest(BaseModel):
    user_id: str = "default"

# ══════════════════════════════════════════
# REST ROUTES
# ══════════════════════════════════════════


@app.get("/")
def home():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    locations = [
        os.path.join(base_dir, '..', 'frontend', 'index.html'),
        os.path.join(base_dir, 'index.html'),
        os.path.join(base_dir, '..', 'index.html')
    ]
    for path in locations:
        if os.path.exists(path):
            return FileResponse(path)
    return {"status": "Sativus AI — Groq powered", "cached_entries": len(_cache)}


@app.get("/health")
def health():
    return {"ok": True, "service": "sativus-ai"}


@app.get("/metrics")
def metrics():
    with _metrics_lock:
        snap = dict(_metrics)
    avg_latency = 0.0
    if snap["analyze_requests"] > 0:
        avg_latency = snap["analyze_latency_ms_sum"] / snap["analyze_requests"]
    return {
        "analyze_requests": snap["analyze_requests"],
        "analyze_success": snap["analyze_success"],
        "analyze_fail": snap["analyze_fail"],
        "analyze_avg_latency_ms": round(avg_latency, 2),
        "live_sessions_started": snap["live_sessions_started"],
        "live_sessions_completed": snap["live_sessions_completed"],
        "live_sessions_failed": snap["live_sessions_failed"],
    }


@app.get("/manifest.json")
def manifest():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    locations = [
        os.path.join(base_dir, '..', 'frontend', 'manifest.json'),
        os.path.join(base_dir, 'manifest.json'),
        os.path.join(base_dir, '..', 'manifest.json')
    ]
    for path in locations:
        if os.path.exists(path):
            return FileResponse(path)
    return {
        "name": "Sativus AI",
        "short_name": "Sativus",
        "start_url": ".",
        "display": "standalone",
        "background_color": "#120f09",
        "theme_color": "#120f09",
        "description": "Plant Doctor & Nature Explorer"
    }


@app.get("/sw.js")
def service_worker():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    locations = [
        os.path.join(base_dir, '..', 'frontend', 'sw.js'),
        os.path.join(base_dir, 'sw.js'),
        os.path.join(base_dir, '..', 'sw.js')
    ]
    for path in locations:
        if os.path.exists(path):
            return FileResponse(path, media_type="application/javascript")
    return JSONResponse(status_code=404, content={"error": "service worker not found"})


@app.get("/clear-cache")
def clear_cache_route():
    with _cache_lock:
        _cache.clear()
    return {"status": "Cache cleared!"}


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    _record_metric("analyze_requests")
    _start = time.perf_counter()
    # Basic sanitization and OOM protection
    if not req.image or len(req.image) > 15 * 1024 * 1024:
        return _analyze_error("invalid or too large image string (max 15MB base64)", 413, _start)

    try:
        raw_b64 = req.image.split(',')[1] if ',' in req.image else req.image
        padded_b64 = raw_b64 + "=" * (-len(raw_b64) % 4)
        image_data = base64.b64decode(padded_b64)
    except (ValueError, TypeError, binascii.Error):
        return _analyze_error("image decode failed", 422, _start)

    safe_location = redact_location(req.location)
    mode = "doctor" if req.mode == "doctor" else "explorer"

    if mode == "doctor":
        prompt = """You are an expert botanist. Examine this image carefully.
Identify any plant — even partial or dark images. Never say "Unknown Plant".

Respond ONLY with valid JSON (no markdown):
{
  "found": true,
  "common_name": "plant common name",
  "scientific_name": "scientific name",
  "category": "houseplant OR succulent OR tree OR herb OR flower",
  "health_status": "Healthy OR Sick OR Critical",
  "diagnosis": "one sentence on what is wrong, or null if healthy",
  "story": "2 sentences describing the plant and its condition.",
  "treatment_steps": ["Step 1", "Step 2", "Step 3"],
  "watering_schedule": "watering frequency",
    "fun_fact": "one interesting fact",
    "confidence": 0.0,
    "alternatives": ["possible alternative 1", "possible alternative 2"],
    "evidence_source": "Groq + iNaturalist"
}
If no plant is visible at all: {"found": false}"""
    else:
        prompt = """You are a field naturalist like David Attenborough. Examine this image.
Identify any living thing — plant, animal, insect, fungi.

Respond ONLY with valid JSON (no markdown):
{
  "found": true,
  "common_name": "common name",
  "scientific_name": "scientific name",
  "category": "plant OR bird OR insect OR fungi OR mammal OR reptile",
  "conservation_status": "Least Concern OR Vulnerable OR Endangered OR Invasive",
  "story": "2 exciting sentences about this species.",
  "fun_fact": "one surprising fact",
    "treatment_steps": [],
    "confidence": 0.0,
    "alternatives": ["possible alternative 1", "possible alternative 2"],
    "evidence_source": "Groq + iNaturalist"
}
If nothing living: {"found": false}"""

    try:
        if not GROQ_API_KEY:
            return _analyze_error("ai provider not configured", 503, _start)

        print(f"[ANALYZE] Sending to {GROQ_MODEL}")
        provider = "groq"
        result = None
        parse_error = None
        for _ in range(2):
            text = call_groq_vision(image_data, prompt)
            try:
                result = _parse_analysis_json(text)
                break
            except json.JSONDecodeError as e:
                parse_error = e
        if result is None:
            raise parse_error if parse_error else json.JSONDecodeError(
                "parse failed", "", 0)

        normalized = _normalize_analysis_result(result, mode)
        if not normalized.get("found"):
            _record_metric("analyze_fail")
            _record_metric("analyze_latency_ms_sum",
                           (time.perf_counter() - _start) * 1000)
            return {"found": False}

        observations = get_observations(normalized.get('scientific_name', ''))
        _record_metric("analyze_success")
        _record_metric("analyze_latency_ms_sum",
                       (time.perf_counter() - _start) * 1000)
        return {
            "found": True,
            "provider":            provider,
            "common_name":         normalized.get('common_name', ''),
            "scientific_name":     normalized.get('scientific_name', ''),
            "category":            normalized.get('category', ''),
            "health_status":       normalized.get('health_status', ''),
            "conservation_status": normalized.get('conservation_status', 'Least Concern'),
            "diagnosis":           normalized.get('diagnosis', ''),
            "story":               normalized.get('story', ''),
            "treatment_steps":     normalized.get('treatment_steps', []),
            "watering_schedule":   normalized.get('watering_schedule', ''),
            "fun_fact":            normalized.get('fun_fact', ''),
            "confidence":          normalized.get('confidence', 0.0),
            "alternatives":        normalized.get('alternatives', []),
            "evidence_source":     normalized.get('evidence_source', 'Groq + iNaturalist'),
            "global_observations": observations,
            "location":            safe_location
        }
    except json.JSONDecodeError:
        logger.warning("Analyze parsing failed")
        return _analyze_error("model response parse failed", 502, _start)
    except requests.HTTPError as e:
        status = 502
        if e.response is not None and e.response.status_code == 429:
            status = 429
        logger.warning("Groq HTTP error during analyze: %s", e)
        return _analyze_error("upstream ai request failed", status, _start)
    except requests.RequestException as e:
        logger.warning("Network error during analyze: %s", e)
        return _analyze_error("upstream ai unavailable", 502, _start)
    except (RuntimeError, ValueError, TypeError, OSError) as e:
        logger.warning("Analyze runtime error: %s", e)
        return _analyze_error("analysis failed", 500, _start)


@app.post("/reminder")
async def create_reminder(req: ReminderRequest):
    record = create_reminder_entry(
        req.user_id, req.plant_name, req.watering_schedule)

    return {
        "plant_name": record["plant_name"],
        "days_until_water": record["days_until_water"],
        "due_at": record["due_at"],
        "message": f"Reminder set! Water your {record['plant_name']} in {record['days_until_water']} days."
    }


@app.post("/reminder/due")
async def get_due_reminders(req: DueReminderRequest):
    due, upcoming = get_due_for_user(req.user_id)
    return {
        "user_id": req.user_id,
        "due": due,
        "upcoming": upcoming,
        "count_due": len(due),
        "count_upcoming": len(upcoming),
    }


# ══════════════════════════════════════════
# LIVE VOICE IMPLEMENTATION
# ══════════════════════════════════════════

async def get_groq_response_stream(transcript: str, mode: str):
    """Streams text response from Groq based on user transcript."""
    system_prompt = (
        "You are Sativus, a helpful plant doctor and nature explorer. "
        "Keep your responses concise, friendly, and suitable for voice conversation. "
        "Do not use markdown formatting like bold or bullet points, as this will be read aloud."
    )
    if mode == "explorer":
        system_prompt += " You are in Explorer mode, focusing on wildlife and nature."
    else:
        system_prompt += " You are in Doctor mode, focusing on plant health and care."

    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                "POST",
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-specdec",  # Fast & smart
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": transcript}
                    ],
                    "stream": True,
                    "temperature": 0.7,
                    "max_tokens": 150,
                },
                timeout=10.0
            ) as response:
                if response.status_code != 200:
                    yield f"Error: Groq returned {response.status_code}"
                    return

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content = data["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError):
                            continue
        except Exception as e:
            logger.error(f"Groq stream error: {e}")
            yield "I'm having trouble thinking right now."

@app.websocket("/ws/live")
async def live_voice(websocket: WebSocket):
    await websocket.accept()
    _record_metric("live_sessions_started")
    
    if not LIVE_VOICE_ENABLED or not DEEPGRAM_API_KEY or not ELEVENLABS_API_KEY:
        await websocket.send_json({"type": "error", "message": "Live voice services not fully configured."})
        await websocket.close()
        return

    # 1. Setup Deepgram
    dg_client = DeepgramClient(DEEPGRAM_API_KEY)
    dg_connection = dg_client.listen.live.v("1")
    
    # 2. Setup ElevenLabs WebSocket for streaming input
    # We'll open this when we start getting text from Groq
    el_ws_url = f"wss://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream-input?model_id=eleven_turbo_v2_5"
    
    user_mode = "doctor"
    is_processing = False

    async def on_message(self, result, **kwargs):
        nonlocal is_processing
        sentence = result.channel.alternatives[0].transcript
        if not sentence or not result.is_final:
            return
        
        if is_processing:
            return # Simple debounce
            
        is_processing = True
        logger.info(f"[LIVE] Transcript: {sentence}")
        await websocket.send_json({"type": "transcript", "text": sentence})
        await websocket.send_json({"type": "state", "state": "thinking"})

        # Start ElevenLabs streaming
        async with httpx.AsyncClient() as client:
            try:
                async with websockets.connect(el_ws_url) as el_ws:
                    # Initial ElevenLabs config
                    await el_ws.send(json.dumps({
                        "text": " ", # Start with space
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
                        "xi_api_key": ELEVENLABS_API_KEY,
                    }))

                    await websocket.send_json({"type": "state", "state": "speaking"})
                    
                    # Stream from Groq to ElevenLabs
                    full_response = ""
                    async for chunk in get_groq_response_stream(sentence, user_mode):
                        full_response += chunk
                        await el_ws.send(json.dumps({"text": chunk, "try_trigger_generation": True}))
                        
                        # Check for audio from ElevenLabs while sending text
                        # This part is tricky with simple loops, usually done with a listener task
                        # But for now we'll do sequential chunks for stability
                        try:
                            # Try to receive audio chunks from ElevenLabs
                            # We set a tiny timeout to keep the Groq stream moving
                            while True:
                                el_resp_raw = await asyncio.wait_for(el_ws.recv(), timeout=0.01)
                                el_resp = json.loads(el_resp_raw)
                                if el_resp.get("audio"):
                                    await websocket.send_bytes(base64.b64decode(el_resp["audio"]))
                                if el_resp.get("isFinal"):
                                    break
                        except asyncio.TimeoutError:
                            pass

                    # Finish ElevenLabs stream
                    await el_ws.send(json.dumps({"text": ""}))
                    
                    # Flush remaining audio
                    try:
                        while True:
                            el_resp_raw = await asyncio.wait_for(el_ws.recv(), timeout=1.0)
                            el_resp = json.loads(el_resp_raw)
                            if el_resp.get("audio"):
                                await websocket.send_bytes(base64.b64decode(el_resp["audio"]))
                            if el_resp.get("isFinal"):
                                break
                    except asyncio.TimeoutError:
                        pass
                    
                    await websocket.send_json({"type": "state", "state": "idle"})
                    logger.info(f"[LIVE] Full Response: {full_response}")

            except Exception as e:
                logger.error(f"Voice orchestration error: {e}")
                await websocket.send_json({"type": "error", "message": "Voice synthesis failed."})
            finally:
                is_processing = False

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    
    options = LiveOptions(
        model="nova-2",
        language="en-US",
        smart_format=True,
        encoding="linear16",
        channels=1,
        sample_rate=16000,
    )

    if not dg_connection.start(options):
        await websocket.send_json({"type": "error", "message": "Failed to connect to STT provider."})
        return

    try:
        while True:
            data = await websocket.receive()
            if "bytes" in data:
                dg_connection.send(data["bytes"])
            elif "text" in data:
                msg = json.loads(data["text"])
                if msg.get("type") == "mode":
                    user_mode = msg.get("mode", "doctor")
            elif data.get("type") == "websocket.disconnect":
                break
    except Exception as e:
        logger.error(f"WebSocket loop error: {e}")
    finally:
        dg_connection.finish()
        _record_metric("live_sessions_completed")
        logger.info("[LIVE] Session closed")
