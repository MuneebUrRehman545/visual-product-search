import sys
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from fastapi.testclient import TestClient
from app.main import app

def verify_gateway():
    print("Testing Gateway Vision Endpoint using TestClient...")
    run_id = 'e28c6a52-a250-41f1-903c-ec43fb0903d3'
    
    with TestClient(app) as client:
        url = "/api/v1/gateway/run"
        try:
            with open("data/images/37783.jpg", "rb") as f:
                r = client.post(
                    url, 
                    data={"run_id": run_id, "top_k": 5, "model": "clip"}, 
                    files={"image": ("37783.jpg", f, "image/jpeg")}
                )
                print(f"Status Code: {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    print("Response JSON:")
                    print(json.dumps(data, indent=2))
                    if data.get("status") == "vision_complete":
                        print("SUCCESS: status is vision_complete")
                    else:
                        print(f"FAILED: expected status vision_complete, got {data.get('status')}")
                else:
                    print(f"FAILED: {r.text}")
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    verify_gateway()
