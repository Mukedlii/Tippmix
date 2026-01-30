from __future__ import annotations

import os
from openai import OpenAI


def make_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    return OpenAI(api_key=api_key)


def make_grok_client() -> OpenAI:
    """
    xAI Grok OpenAI-kompatibilis végpont: base_url=https://api.x.ai/v1
    """
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing XAI_API_KEY")
    return OpenAI(base_url="https://api.x.ai/v1", api_key=api_key)
