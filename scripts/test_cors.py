"""CORS configuration test script."""

from pathlib import Path
import sys
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app

def main():
    client = TestClient(app)

    print("=" * 80)
    print("FASTAPI CORS CONFIGURATION TEST SUITE")
    print("=" * 80)

    # 1. Test /health
    h_res = client.get("/health")
    print(f"[TEST 1] GET /health -> HTTP {h_res.status_code} | {h_res.json()}")
    assert h_res.status_code == 200

    # 2. Test preflight OPTIONS from approved origin: http://localhost:5173
    print("\n[TEST 2] Preflight OPTIONS from approved origin (http://localhost:5173)")
    preflight_res = client.options(
        "/api/v1/search",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    allow_origin = preflight_res.headers.get("access-control-allow-origin")
    allow_credentials = preflight_res.headers.get("access-control-allow-credentials")
    print(f"HTTP Status:                      {preflight_res.status_code}")
    print(f"Access-Control-Allow-Origin:      {allow_origin}")
    print(f"Access-Control-Allow-Credentials: {allow_credentials}")
    assert preflight_res.status_code == 200
    assert allow_origin == "http://localhost:5173"
    assert allow_credentials == "true"

    # 3. Test preflight OPTIONS from approved origin: http://127.0.0.1:5173
    print("\n[TEST 3] Preflight OPTIONS from approved origin (http://127.0.0.1:5173)")
    preflight_ip_res = client.options(
        "/api/v1/search",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    allow_origin_ip = preflight_ip_res.headers.get("access-control-allow-origin")
    print(f"HTTP Status:                      {preflight_ip_res.status_code}")
    print(f"Access-Control-Allow-Origin:      {allow_origin_ip}")
    assert preflight_ip_res.status_code == 200
    assert allow_origin_ip == "http://127.0.0.1:5173"

    # 4. Test preflight OPTIONS from unapproved origin: http://example.com
    print("\n[TEST 4] Preflight OPTIONS from unapproved origin (http://example.com)")
    unapproved_res = client.options(
        "/api/v1/search",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    unapproved_origin = unapproved_res.headers.get("access-control-allow-origin")
    print(f"HTTP Status:                      {unapproved_res.status_code}")
    print(f"Access-Control-Allow-Origin:      {unapproved_origin}")
    assert unapproved_origin is None or unapproved_origin != "http://example.com"

    print("\n" + "=" * 80)
    print("ALL CORS VERIFICATION TESTS PASSED SUCCESSFULLY.")
    print("=" * 80)

if __name__ == "__main__":
    main()
