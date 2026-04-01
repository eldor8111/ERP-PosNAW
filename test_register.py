import sys
import httpx
import time

sys.stdout.reconfigure(encoding='utf-8')

def test_register():
    url = "http://localhost:8000/api/auth/register"
    phone_suffix = str(int(time.time()))[-8:]
    payload = {
        "company_name": f"Test Company {phone_suffix}",
        "name": "Test User",
        "phone": f"+99890{phone_suffix}",
        "region": "Toshkent shahri",
        "district": "Yunusobod",
        "password": "password123",
        "agent_code": ""
    }
    
    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_register()
