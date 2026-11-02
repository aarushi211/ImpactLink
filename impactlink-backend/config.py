import os
from dotenv import load_dotenv

load_dotenv()

LOCAL_LLM_MODEL = "qwen2.5-3B-Instruct-Q4_K_M"

# Other Constants
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "grants"