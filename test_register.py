import urllib.request
import json

data = json.dumps({"email": "patch2@example.com", "password": "password123", "org_name": "Test NGO"}).encode("utf-8")
req = urllib.request.Request("http://localhost:8000/api/auth/register", data=data, headers={"Content-Type": "application/json"})

try:
    response = urllib.request.urlopen(req)
    profile = json.loads(response.read().decode())["profile"]
    print("REGISTRATION SUCCESS", profile["id"])
    
    patch_data = json.dumps({"ngo_id": profile["id"], "updates": {"mission": "Test"}}).encode("utf-8")
    patch_req = urllib.request.Request("http://localhost:8000/api/profile", data=patch_data, headers={"Content-Type": "application/json"}, method="PATCH")
    patch_resp = urllib.request.urlopen(patch_req)
    print("PATCH SUCCESS", patch_resp.read().decode())
    
except urllib.error.HTTPError as e:
    print(f"HTTP ERROR {e.code}:", e.read().decode())
except Exception as e:
    print("GENERIC ERROR:", e)
