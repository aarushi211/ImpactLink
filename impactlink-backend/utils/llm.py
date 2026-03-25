import os
import random
import logging
import time
import asyncio
import groq  
from typing import Any, List, Optional
from langchain_groq import ChatGroq
from groq import Groq, AsyncGroq
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

# Parse keys once at module level
_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]

class RotatingGroq(ChatGroq):
    """
    A drop-in replacement for ChatGroq that rotates through multiple API keys
    and includes automatic retry logic for Rate Limit (429) errors.
    """

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if GROQ_KEYS:
                    new_key = random.choice(GROQ_KEYS)
                    object.__setattr__(self, "groq_api_key", new_key)
                    object.__setattr__(self, "client", Groq(api_key=new_key).chat.completions)  # ← fix
                    log.info(f"🔄 [Sync] Using Groq Key: {new_key[:7]}...")
                return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    log.warning(f"⚠️ Rate Limit hit. Retrying in 6s...")
                    time.sleep(6)
                    continue
                raise e

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if GROQ_KEYS:
                    new_key = random.choice(GROQ_KEYS)
                    object.__setattr__(self, "groq_api_key", new_key)
                    object.__setattr__(self, "async_client", AsyncGroq(api_key=new_key).chat.completions)  # ← fix
                    log.info(f"🔄 [Async] Using Groq Key: {new_key[:7]}...")
                return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    log.warning(f"⚠️ [Async] Rate Limit hit. Retrying in 6s...")
                    await asyncio.sleep(6)
                    continue
                raise e