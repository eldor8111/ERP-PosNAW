import urllib.request
import json
token = '8572484074:AAFMbjXaquRUz4ObVMGGI1AVK_9oO5V5MeQ'
req = urllib.request.Request(f'https://api.telegram.org/bot{token}/getUpdates')
try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode('utf-8')[:500])
except Exception as e:
    print('ERROR:', e)
