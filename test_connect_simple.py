import requests
import time

url = "https://fapi.binance.com/fapi/v1/time"
print(f"Testing connection to {url}...")
try:
    response = requests.get(url, timeout=5)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Connection failed: {e}")

url_info = "https://fapi.binance.com/fapi/v1/exchangeInfo"
print(f"\nTesting connection to {url_info}...")
try:
    response = requests.get(url_info, timeout=5)
    print(f"Status Code: {response.status_code}")
    print(f"Response length: {len(response.text)}")
except Exception as e:
    print(f"Connection failed: {e}")
