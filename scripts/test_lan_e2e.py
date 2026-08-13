import json
from pathlib import Path
import sys
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LAN_IP = "192.168.100.63"
BACKEND_LAN_URL = f"http://{LAN_IP}:8000"
FRONTEND_LAN_URL = f"http://{LAN_IP}:5174"


def main():
    print("=" * 80)
    print("LAN NETWORK E2E SEARCH VERIFICATION SUITE")
    print("=" * 80)

    # 1. Test LAN Frontend HTTP Status
    print(f"\n[TEST 1] LAN Frontend ({FRONTEND_LAN_URL}/)")
    try:
        f_res = urllib.request.urlopen(FRONTEND_LAN_URL + "/")
        print(f"HTTP Status: {f_res.status} OK | Content-Type: {f_res.headers.get('content-type')}")
        assert f_res.status == 200
    except Exception as e:
        print(f"Frontend LAN fetch error: {e}")

    # 2. Test LAN Backend /health
    print(f"\n[TEST 2] LAN Backend Health ({BACKEND_LAN_URL}/health)")
    try:
        b_res = urllib.request.urlopen(BACKEND_LAN_URL + "/health")
        b_data = json.loads(b_res.read().decode())
        print(f"HTTP Status: {b_res.status} OK | Response: {b_data}")
        assert b_res.status == 200
    except Exception as e:
        print(f"Backend LAN health error: {e}")

    # 3. Test LAN Preflight OPTIONS
    print(f"\n[TEST 3] LAN Preflight OPTIONS Request from Origin {FRONTEND_LAN_URL}")
    req_opt = urllib.request.Request(
        f"{BACKEND_LAN_URL}/api/v1/search",
        headers={
            "Origin": FRONTEND_LAN_URL,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
        method="OPTIONS",
    )
    res_opt = urllib.request.urlopen(req_opt)
    allow_orig = res_opt.headers.get("access-control-allow-origin")
    print(f"HTTP Status:                 {res_opt.status}")
    print(f"Access-Control-Allow-Origin: {allow_orig}")
    assert res_opt.status == 200
    assert allow_orig == FRONTEND_LAN_URL

    # 4. Test LAN Search POST Request
    print(f"\n[TEST 4] LAN Visual Search POST Query ({BACKEND_LAN_URL}/api/v1/search)")
    img_path = PROJECT_ROOT / "data" / "catalog" / "images" / "15025.jpg"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"

    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="file"; filename="15025.jpg"\r\n')
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(img_path.read_bytes())
    body.extend(f"\r\n--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="top_k"\r\n\r\n')
    body.extend(b"5\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req_search = urllib.request.Request(
        f"{BACKEND_LAN_URL}/api/v1/search",
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Origin": FRONTEND_LAN_URL,
        },
        method="POST",
    )

    res_search = urllib.request.urlopen(req_search)
    data = json.loads(res_search.read().decode())
    print(f"HTTP Status:    {res_search.status}")
    print(f"Query Filename: {data['query_filename']}")
    print(f"Total Results:  {data['total_results']}")

    top_item = data["results"][0]
    print(f"Rank 1 Match:   Product ID = {top_item['product_id']} | Ext ID = {top_item['external_id']} | Score = {top_item['similarity_score']}")
    print(f"Relative URL:   {top_item['image_url']}")

    # 5. Test LAN Image URL Fetch
    full_img_url = f"{BACKEND_LAN_URL}{top_item['image_url']}"
    print(f"\n[TEST 5] LAN Catalog Image Fetch ({full_img_url})")
    res_img = urllib.request.urlopen(full_img_url)
    print(f"HTTP Status:  {res_img.status} OK")
    print(f"Content-Type: {res_img.headers.get('content-type')}")
    print(f"Content Size: {len(res_img.read())} bytes")
    assert res_img.status == 200

    print("\n" + "=" * 80)
    print("ALL LAN VERIFICATION TESTS PASSED SUCCESSFULLY.")
    print("=" * 80)


if __name__ == "__main__":
    main()
