from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from services.parser import parse_proposal
from agents.scoring_agent import score_proposal
from agents.similarity_agent import find_similar_grants

app = FastAPI(title="NGO Grant Intelligence Portal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health():
    return {"status": "running", "message": "NGO Grant Portal API"}


@app.post("/api/upload")
async def upload_proposal(file: UploadFile = File(...)):
    """
    Main endpoint. Accepts PDF/DOCX upload.
    Returns: extracted proposal JSON + scoring + funder matches.
    """
    # Validate file type
    if not file.filename.endswith((".pdf", ".docx", ".txt")):
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, or TXT files accepted.")

    file_bytes = await file.read()

    # Step 1: Parse proposal → structured JSON
    try:
        proposal = parse_proposal(file_bytes, file.filename)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse proposal: {str(e)}")

    # Step 2: Run scoring + similarity in parallel
    try:
        scoring_result, funder_matches = await asyncio.gather(
            asyncio.to_thread(score_proposal, proposal),
            asyncio.to_thread(find_similar_grants, proposal, 5)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    return {
        "proposal": proposal,
        "scoring": scoring_result,
        "funder_matches": funder_matches,
    }


@app.post("/api/score")
async def score_only(proposal: dict):
    """Score an already-parsed proposal JSON directly."""
    try:
        result = await asyncio.to_thread(score_proposal, proposal)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/match")
async def match_only(proposal: dict):
    """Find funder matches for an already-parsed proposal JSON."""
    try:
        result = await asyncio.to_thread(find_similar_grants, proposal, 5)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))