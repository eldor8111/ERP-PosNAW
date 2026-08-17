import sys, requests
sys.stdout.reconfigure(encoding='utf-8')
URL = 'https://savdo.e-code.uz'
session = requests.Session()
res = session.post(f'{URL}/api/auth/login', json={'phone': '933344602', 'password': '123456'})
if res.status_code != 200:
    print('Login failed:', res.text)
    sys.exit(1)
token = res.json().get('access_token')
headers = {'Authorization': f'Bearer {token}'}

res = session.get(f'{URL}/api/products?search=dumba&page=1&limit=10', headers=headers)
prods = res.json()
if not prods:
    print('Dumba not found')
else:
    dumba = prods[0]
    print(f'Dumba ID: {dumba.get("id")}, Type: {dumba.get("product_type", "unknown")}')
    
    res = session.get(f'{URL}/api/products/{dumba.get("id")}', headers=headers)
    dumba_detail = res.json()
    print('Raw Detail:', dumba_detail)

res = session.get(f'{URL}/api/products?search=butun&page=1&limit=10', headers=headers)
if res.json():
    bq = res.json()[0]
    print(f'Butun Qoy ID: {bq.get("id")}, Stock: {bq.get("stock_quantity")}, Type: {bq.get("product_type")}')
    print('WH Stocks:', bq.get('warehouse_stocks'))
