"""
Quick smoke-test for the /api/upload endpoint.
Finds the first PDF in the Data/ folder, posts it, and prints the result.
"""
import requests
import os
import json

PDF_FOLDER = os.path.join(os.path.dirname(__file__), "Data")
pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.endswith(".pdf")]

if not pdf_files:
    print("❌ No PDF files found in Data/. Place a test PDF there first.")
    raise SystemExit(1)

pdf_path = os.path.join(PDF_FOLDER, pdf_files[0])
print(f"📄 Uploading: {pdf_path}")

try:
    with open(pdf_path, "rb") as f:
        response = requests.post(
            "http://localhost:8000/api/upload",
            files={"file": (pdf_files[0], f, "application/pdf")},
            timeout=120,
        )
    print(f"HTTP status: {response.status_code}")
    try:
        data = response.json()
        # Pretty print without the full description to keep it readable
        summary = {
            "proposal_keys": list((data.get("proposal") or {}).keys()),
            "scoring_keys": list((data.get("scoring") or {}).keys()),
            "num_matches": len(data.get("matches") or []),
            "error": data.get("detail") or data.get("error"),
        }
        print(json.dumps(summary, indent=2))
        if data.get("matches"):
            print("First match:", json.dumps(data["matches"][0], indent=2, default=str)[:600])
    except Exception:
        print("Raw response:", response.text[:2000])
except Exception as e:
    print(f"❌ Request failed: {e}")
