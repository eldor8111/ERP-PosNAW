import requests

url = "http://localhost:8010/api/mxik/barcode/4780068020047"
print(f"Testing URL: {url}")

try:
    # Get a token to make an authorized request if needed. Note: This route requires current_user.
    import sys
    sys.path.append("/home/nullcoder/Desktop/e-code/ERP-PosNAW")
    from app.core.security import create_access_token
    token = create_access_token({"sub": "1", "role": "admin", "company_id": 1})
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, timeout=5)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
