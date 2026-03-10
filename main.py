from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Any
from google import genai
from google.genai import types
import requests
import base64
import json
import os
import asyncio
import hashlib
import time
from dotenv import load_dotenv

load_dotenv()

# ── SETUP ──
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

FLASH_MODEL = "gemini-2.0-flash"
LIVE_MODEL  = "gemini-2.0-flash-live-001"  # upgrade to native-audio-dialog when quota available

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════
# CACHE
# ══════════════════════════════════════════
_cache = {}
CACHE_TTL = 3600

def get_cached(key):
    entry = _cache.get(key)
    if entry and (time.time() - entry["timestamp"]) < CACHE_TTL:
        return entry["response"]
    return None

def set_cache(key, response):
    _cache[key] = {"response": response, "timestamp": time.time()}
    if len(_cache) > 100:
        oldest = min(_cache, key=lambda k: _cache[k]["timestamp"])
        del _cache[oldest]

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
        data = requests.get(url, params={"q": scientific_name, "per_page": 1}, timeout=5).json()
        if data.get("results"):
            return f"{data['results'][0].get('observations_count', 0):,}"
    except:
        pass
    return "0"

def call_vision(image_bytes: bytes, prompt: str) -> str:
    response = client.models.generate_content(
        model=FLASH_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            prompt
        ]
    )
    return response.text.strip()

def call_text(prompt: str) -> str:
    response = client.models.generate_content(
        model=FLASH_MODEL,
        contents=prompt
    )
    return response.text.strip()

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

# ══════════════════════════════════════════
# REST ROUTES
# ══════════════════════════════════════════
@app.get("/")
def home():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    locations = [
        os.path.join(base_dir, '..', 'frontend', 'index.html'),
        os.path.join(base_dir, 'index.html'),
        os.path.join(base_dir, '..', 'index.html'),
        os.path.join(os.getcwd(), 'frontend', 'index.html'),
        os.path.join(os.getcwd(), 'index.html')
    ]
    for path in locations:
        if os.path.exists(path):
            return FileResponse(path)
    return {"status": "Sativus AI — Gemini powered", "cached_entries": len(_cache)}

@app.get("/manifest.json")
def manifest():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    locations = [
        os.path.join(base_dir, '..', 'frontend', 'manifest.json'),
        os.path.join(base_dir, 'manifest.json'),
        os.path.join(base_dir, '..', 'manifest.json'),
        os.path.join(os.getcwd(), 'frontend', 'manifest.json'),
        os.path.join(os.getcwd(), 'manifest.json')
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

@app.get("/clear-cache")
def clear_cache_route():
    _cache.clear()
    return {"status": "Cache cleared!"}

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        raw_b64 = req.image.split(',')[1] if ',' in req.image else req.image
        image_data = base64.b64decode(raw_b64)
    except Exception as e:
        return {"found": False, "error": "image decode failed"}

    safe_location = redact_location(req.location)

    if req.mode == "doctor":
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
  "fun_fact": "one interesting fact"
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
  "treatment_steps": []
}
If nothing living: {"found": false}"""

    try:
        print(f"[ANALYZE] Sending to {FLASH_MODEL}")
        text = call_vision(image_data, prompt)
        text = text.replace('```json', '').replace('```', '').strip()
        result = json.loads(text)

        if result.get('found') and 'unknown' in str(result.get('common_name', '')).lower():
            result['found'] = False
        if not result.get('found'):
            return {"found": False}

        observations = get_observations(result.get('scientific_name', ''))
        return {
            "found": True,
            "common_name":         result.get('common_name', ''),
            "scientific_name":     result.get('scientific_name', ''),
            "category":            result.get('category', ''),
            "health_status":       result.get('health_status', ''),
            "conservation_status": result.get('conservation_status', 'Least Concern'),
            "diagnosis":           result.get('diagnosis', ''),
            "story":               result.get('story', ''),
            "treatment_steps":     result.get('treatment_steps', []),
            "watering_schedule":   result.get('watering_schedule', ''),
            "fun_fact":            result.get('fun_fact', ''),
            "global_observations": observations,
            "location":            safe_location
        }
    except json.JSONDecodeError:
        return {"found": False, "error": "parse failed"}
    except Exception as e:
        print(f"[ANALYZE] Error: {e}")
        return {"found": False, "error": str(e)}



@app.post("/reminder")
async def create_reminder(req: ReminderRequest):
    prompt = f"Plant: {req.plant_name}\nSchedule: {req.watering_schedule}\nDays until next watering? Reply with ONE number only."
    try:
        cache_key = hashlib.md5(prompt.encode()).hexdigest()
        days_text = get_cached(cache_key)
        if not days_text:
            days_text = call_text(prompt)
            set_cache(cache_key, days_text)
        days = int(''.join(filter(str.isdigit, days_text))) or 7
    except:
        days = 7
    return {
        "plant_name": req.plant_name,
        "days_until_water": days,
        "message": f"Reminder set! Water your {req.plant_name} in {days} days."
    }



# ══════════════════════════════════════════
# GEMINI LIVE — BIDI STREAMING VOICE
# Features: affective dialog, proactive audio,
#           barge-in support, native audio output
# ══════════════════════════════════════════
@app.websocket("/ws/live")
async def live_voice(websocket: WebSocket):
    await websocket.accept()
    print("[LIVE] Client connected")

    try:
        # First message: plant context + optional camera frame
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        context = json.loads(raw)
        plant_name = context.get("plant_name", "a plant")
        health     = context.get("health_status", "unknown")
        diagnosis  = context.get("diagnosis", "")
        location   = context.get("location")
        history    = context.get("history", "")

        weather_txt = ""
        if location and isinstance(location, dict):
            lat = location.get("lat")
            lng = location.get("lng")
            if lat and lng:
                try:
                    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}&current_weather=true"
                    def get_w():
                        return requests.get(url, timeout=1.5).json()
                    w_data = await asyncio.wait_for(asyncio.to_thread(get_w), timeout=1.5)
                    cw = w_data.get("current_weather")
                    if cw:
                        weather_txt = f" Current weather in their area is {cw.get('temperature')}°C with {cw.get('windspeed')}km/h wind."
                except Exception as e:
                    print(f"[LIVE] Weather error (skipped): {e}")

        history_txt = f" User's Garden History (last 4 plants): {history}." if history else ""

        system_prompt = (
            f"You are Sativus, a warm and knowledgeable plant doctor. "
            f"You are currently helping with: {plant_name} (Health: {health}"
            + (f", Issue: {diagnosis}" if diagnosis else "")
            + ")."
            + weather_txt
            + history_txt
            + " Be direct — max 2 sentences. No markdown, no special characters. "
            + "Match the user's energy: if they sound worried, be reassuring; "
            + "if they sound curious, be enthusiastic."
        )

        # ── LiveConnectConfig — wrap experimental flags safely ──
        # enable_affective_dialog / ProactivityConfig added in newer SDK versions
        # gracefully falls back if not supported so the session still opens
        _base_config = dict(
            response_modalities=["AUDIO"], # Request native Gemini voice back
            system_instruction=types.Content(
                parts=[types.Part(text=system_prompt)],
                role="model"
            ),
        )
        try:
            live_config = types.LiveConnectConfig(
                **_base_config,
                enable_affective_dialog=True,
                proactivity=types.ProactivityConfig(proactive_audio=True),
            )
            print("[LIVE] Affective dialog + proactive audio enabled")
        except TypeError:
            # SDK version doesn't support these fields yet — use base config
            live_config = types.LiveConnectConfig(**_base_config)
            print("[LIVE] Affective dialog not supported by this SDK version — continuing without")

        async with client.aio.live.connect(
            model=LIVE_MODEL,
            config=live_config
        ) as session:
            print("[LIVE] Gemini session open — affective dialog + proactive audio active")
            stop        = asyncio.Event()
            accumulated = ""
            interrupted = False  # barge-in state
            has_audio   = False  # tracks if native audio was generated

            async def recv_from_client():
                nonlocal interrupted
                try:
                    while not stop.is_set():
                        msg = await websocket.receive()
                        if msg["type"] == "websocket.disconnect":
                            stop.set(); break

                        if "bytes" in msg and msg["bytes"]:
                            # PCM 16kHz 16-bit mono audio chunk from mic
                            try:
                                await session.send(
                                    input=types.LiveClientRealtimeInput(
                                        media_chunks=[
                                            types.Blob(
                                                data=msg["bytes"],
                                                mime_type="audio/pcm;rate=16000"
                                            )
                                        ]
                                    )
                                )
                            except Exception as e:
                                print(f"[LIVE] Failed to send audio chunk: {e}")

                        elif "text" in msg and msg["text"]:
                            try:
                                data = json.loads(msg["text"])
                            except json.JSONDecodeError:
                                continue

                            if data.get("type") == "end_of_turn":
                                interrupted = False
                                try:
                                    await session.send(input="", end_of_turn=True)
                                except Exception:
                                    pass

                            elif data.get("type") == "barge_in":
                                # User interrupted — signal Gemini to stop speaking
                                interrupted = True
                                print("[LIVE] Barge-in detected")
                                # Send interrupt signal via empty turn
                                try:
                                    await session.send(input="", end_of_turn=True)
                                except Exception:
                                    pass
                                await websocket.send_json({"type": "interrupted"})

                            elif data.get("type") == "camera_frame" and data.get("data"):
                                # Optional: send camera frame for proactive vision analysis
                                frame_bytes = base64.b64decode(data["data"])
                                try:
                                    await session.send(
                                        input=types.LiveClientRealtimeInput(
                                            media_chunks=[
                                                types.Blob(
                                                    data=frame_bytes,
                                                    mime_type="image/jpeg"
                                                )
                                            ]
                                        )
                                    )
                                except Exception as e:
                                    print(f"[LIVE] Failed to send camera frame: {e}")

                except WebSocketDisconnect:
                    stop.set()
                except Exception as e:
                    print(f"[LIVE] recv_client error: {e}")
                    stop.set()

            async def recv_from_gemini():
                nonlocal accumulated, interrupted, has_audio
                try:
                    async for response in session.receive():
                        if stop.is_set(): break

                        # Handle server-initiated interruption (proactive)
                        if hasattr(response, "interrupted") and response.interrupted:
                            await websocket.send_json({"type": "interrupted"})
                            accumulated = ""
                            interrupted = False
                            has_audio = False
                            continue

                        if not response.server_content:
                            continue

                        sc = response.server_content

                        if sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.text and not interrupted:
                                    accumulated += part.text
                                    await websocket.send_json({
                                        "type": "text_chunk",
                                        "text": part.text
                                    })
                                # NEW: Stream native audio chunks directly
                                if part.inline_data and not interrupted:
                                    has_audio = True
                                    await websocket.send_bytes(part.inline_data.data)

                        if sc.turn_complete:
                            if not interrupted:
                                await websocket.send_json({
                                    "type": "turn_complete",
                                    "full_text": accumulated,
                                    "has_audio": has_audio
                                })
                            accumulated = ""
                            interrupted = False
                            has_audio = False

                except WebSocketDisconnect:
                    stop.set()
                except Exception as e:
                    print(f"[LIVE] recv_gemini error: {e}")
                    stop.set()

            await asyncio.gather(recv_from_client(), recv_from_gemini())

    except asyncio.TimeoutError:
        print("[LIVE] Timeout waiting for context")
    except Exception as e:
        print(f"[LIVE] Session error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        print("[LIVE] Session closed")
