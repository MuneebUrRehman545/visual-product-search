"""Automated End-to-End Search Application Verification Script."""

from pathlib import Path
import sys
import urllib.request
import urllib.parse
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://localhost:5173"


def main():
    print("=" * 80)
    print("WEEK 2 VISUAL PRODUCT SEARCH - END-TO-END VERIFICATION")
    print("=" * 80)

    # 1. Verify Servers
    print("\n--- SERVER STATUS CHECKS ---")
    try:
        f_req = urllib.request.urlopen(FRONTEND_URL + "/")
        print(f"Frontend ({FRONTEND_URL}): HTTP {f_req.status} OK")
    except Exception as e:
        print(f"Frontend failed: {e}")

    try:
        b_req = urllib.request.urlopen(BACKEND_URL + "/health")
        b_data = json.loads(b_req.read().decode())
        print(f"Backend ({BACKEND_URL}/health): HTTP {b_req.status} OK | Response: {b_data}")
    except Exception as e:
        print(f"Backend failed: {e}")

    print("=" * 80)


if __name__ == "__main__":
    main()
