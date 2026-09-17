import requests

email = "supergeroy2580@gmail.com"
password = "ou1aBMPH3p9cSG4L"
url = "https://notify.eskiz.uz/api/auth/login"

try:
    response = requests.post(url, data={"email": email, "password": password})
    print("Status Code:", response.status_code)
    print("Response:", response.text)
except Exception as e:
    print("Error:", e)
