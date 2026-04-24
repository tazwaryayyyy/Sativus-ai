import json
import sys
from urllib import request, error

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"

# Tiny valid 1x1 JPEG
ONE_PIXEL_JPEG = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxAQEBUQEBAVFRUXFRUVFRUVFRUVFRUVFRUWFhUV"
    "FRUYHSggGBolHRUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OFQ8QFS0dFR0tLS0tLS0tLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMBIgACEQEDEQH/"
    "xAAcAAABBQEBAQAAAAAAAAAAAAAFAAMEBgcCAQj/xABDEAABAwIDBQQIBQcEAwAAAAABAAIDBBEF"
    "IQYSMUETIlFhcYEykaGxFEJSwdHwI1Lh8RZTgpKi0sPS4jRDU2Nzk7P/xAAZAQADAQEBAAAAAAAAAA"
    "AAAAABAgMABAX/xAAjEQEBAAICAgIDAQAAAAAAAAAAAQIRAyESMUEEEyJRYXGh/9oADAMBAAIRAxEA"
    "PwD9nREQEREBERAREQEREBERAREQf/Z"
)


def post_json(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=8) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(err_body)
        except json.JSONDecodeError:
            parsed = {"error": err_body[:200]}
        return exc.code, parsed


def get(path):
    req = request.Request(f"{BASE_URL}{path}", method="GET")
    with request.urlopen(req, timeout=8) as resp:
        text = resp.read().decode("utf-8", errors="ignore")
        return resp.status, text[:200]


if __name__ == "__main__":
    try:
        status, body = get("/")
        print(f"[OK] GET / -> {status}")

        status, body = post_json(
            "/reminder",
            {"plant_name": "Monstera",
                "watering_schedule": "every 7 days", "user_id": "smoke"},
        )
        assert "days_until_water" in body, "Missing days_until_water"
        assert "due_at" in body, "Missing due_at"
        print(
            f"[OK] POST /reminder -> {status}, days={body['days_until_water']}")

        status, body = post_json("/reminder/due", {"user_id": "smoke"})
        assert "count_due" in body and "count_upcoming" in body, "Missing reminder counts"
        print(f"[OK] POST /reminder/due -> {status}")

        status, body = post_json(
            "/analyze",
            {"image": f"data:image/jpeg;base64,{ONE_PIXEL_JPEG}", "mode": "doctor"},
        )
        assert "found" in body, "Analyze response missing found"
        if status in (200, 429, 502, 503):
            print(f"[OK] POST /analyze -> {status}, found={body.get('found')}")
        else:
            raise AssertionError(f"Unexpected analyze status: {status}")

        print("\nSmoke test passed.")
    except (AssertionError, error.URLError, TimeoutError) as exc:
        print(f"Smoke test failed: {exc}")
        sys.exit(1)
