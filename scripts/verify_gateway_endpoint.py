import httpx
import sys

def verify_gateway():
    print("Testing Gateway Vision Endpoint...")
    run_id = 'e28c6a52-a250-41f1-903c-ec43fb0903d3'
    
    url = "http://127.0.0.1:8000/api/v1/gateway/run"
    
    # We need a sample image
    try:
        with open("data/images/37783.jpg", "rb") as f:
            r = httpx.post(
                url, 
                data={"run_id": run_id, "top_k": 5, "model": "clip"}, 
                files={"image": ("37783.jpg", f, "image/jpeg")},
                timeout=60.0
            )
            print(f"Status Code: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print("Response JSON:")
                import json
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
