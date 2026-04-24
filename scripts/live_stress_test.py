import asyncio
import json
import os
import time

import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

BASE_URL = os.environ.get("SATIVUS_WS_URL", "ws://localhost:8080/ws/live")
TOTAL = int(os.environ.get("SATIVUS_LIVE_TOTAL", "12"))
CONCURRENCY = int(os.environ.get("SATIVUS_LIVE_CONCURRENCY", "4"))


async def run_one():
    payload = {
        "plant_name": "Monstera",
        "health_status": "Sick",
        "diagnosis": "Yellowing leaves",
        "location": {"lat": 0, "lng": 0},
        "history": "Monstera (Sick), Basil (Healthy)",
        "user_id": "stress",
    }

    started = time.perf_counter()
    try:
        async with websockets.connect(BASE_URL, max_size=2_000_000) as ws:
            await ws.send(json.dumps(payload))
            try:
                first_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                if isinstance(first_msg, str):
                    parsed = json.loads(first_msg)
                    if parsed.get("type") == "error" and "disabled" in str(parsed.get("message", "")).lower():
                        elapsed = time.perf_counter() - started
                        return True, elapsed, "skipped"
            except (asyncio.TimeoutError, json.JSONDecodeError):
                pass

            # Trigger minimal control flow paths without streaming audio.
            await ws.send(json.dumps({"type": "barge_in"}))
            await ws.send(json.dumps({"type": "end_of_turn"}))
            await ws.send(json.dumps({"type": "tool_call", "name": "get_due_reminders", "args": {}}))

            # Collect a few server messages and then close.
            for _ in range(3):
                try:
                    await asyncio.wait_for(ws.recv(), timeout=3.0)
                except asyncio.TimeoutError:
                    break

        elapsed = time.perf_counter() - started
        return True, elapsed, ""
    except ConnectionClosedOK:
        elapsed = time.perf_counter() - started
        return True, elapsed, ""
    except (ConnectionClosedError, OSError, asyncio.TimeoutError, RuntimeError, ValueError) as exc:
        elapsed = time.perf_counter() - started
        return False, elapsed, str(exc)


async def main():
    sem = asyncio.Semaphore(CONCURRENCY)

    async def wrapped(_i: int):
        async with sem:
            return await run_one()

    tasks = [asyncio.create_task(wrapped(i)) for i in range(TOTAL)]
    results = await asyncio.gather(*tasks)

    failures = [r for r in results if not r[0]]
    skipped = [r for r in results if r[2] == "skipped"]
    avg_ms = (sum(r[1] for r in results) / len(results)) * 1000

    print(f"Live stress total={TOTAL} concurrency={CONCURRENCY}")
    print(f"Live stress skipped={len(skipped)}")
    print(f"Live stress failures={len(failures)}")
    print(f"Live stress avg_ms={avg_ms:.1f}")
    if len(skipped) == len(results):
        print("Live endpoint disabled; stress test skipped.")
        return
    if failures:
        print(f"First error: {failures[0][2]}")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
