import urllib.request
import json
import sys

payload = {
    "proposal": {
        "organization_name": "EcoTech Youth",
        "budget_breakdown": ["Personnel", "Equipment"],
        "total_budget": 50000
    },
    "grant": {
        "title": "CA STEM Grant",
        "agency": "State Dept"
    }
}

data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request("http://localhost:8000/api/draft/stream", data=data, headers={"Content-Type": "application/json"})

try:
    response = urllib.request.urlopen(req)
    for line in response:
        print(line.decode().strip())
except Exception as e:
    print("ERROR:", e)
