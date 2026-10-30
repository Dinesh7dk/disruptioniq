import requests
import json

# 1. Login as alice
login_res = requests.post("http://127.0.0.1:8000/auth/login", json={"username": "alice", "password": "pass123"})
token = login_res.json()["access_token"]

# 2. Call GET /disruptions/1/options
headers = {"Authorization": f"Bearer {token}"}
r = requests.get("http://127.0.0.1:8000/disruptions/1/options", headers=headers)
print("HTTP Status Code:", r.status_code)

data = r.json()
print("Total Feasible Options Count:", data.get("options_count"))

print("\n=== FEASIBLE OPTIONS RETURNED BY GET /disruptions/1/options ===")
for opt in data.get("options", []):
    print(f"Type: {opt['type']}")
    print(f"  Description:    {opt['details'].get('description')}")
    print(f"  Cost:           Rs. {opt['cost']}")
    print(f"  Delivery Date:  {opt['new_delivery_date']}")
    print(f"  Meets Deadline: {opt['meets_deadline']}")
    if "order" in opt:
        print(f"  Target Order:   {opt['order']['code']} - {opt['order']['customer']}")
    print("-" * 70)
