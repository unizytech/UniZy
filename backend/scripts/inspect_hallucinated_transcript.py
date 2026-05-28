#!/usr/bin/env python3
"""
Inspect Hallucinated Transcript

One-off diagnostic: downloads the stored audio for failed recording sessions,
re-transcribes via Gemini, and prints/saves the transcript so we can see what
the model actually produced (e.g. a 65K-token hallucination loop).

Usage (from repo root):
    cd backend && source venv/bin/activate
    SUPABASE_URL=https://xyhzvokuxzwcmdefbhcn.supabase.co \\
    SUPABASE_SERVICE_KEY=<main_service_key> \\
    python scripts/inspect_hallucinated_transcript.py \\
        af7ae287-8b32-4249-be07-b6cc0c466fdb \\
        e1faf0dc-f709-47f6-955e-713b20b1df74

Notes:
- GEMINI_API_KEY must be set (backend/.env already exports it).
- Transcripts are saved to /tmp/transcript_{session_id}.txt.
- Reads audio directly from the public storage URL stored on the row.
"""

import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

import base64

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.supabase_service import supabase, get_session_full_audio
from services.gemini_service import transcribe_audio, _parse_language_tag
from google.genai import types as genai_types

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def _raw_transcribe(audio: bytes, mime: str) -> tuple[str, str | None]:
    """Raw Gemini transcription that bypasses transcribe_audio's hallucination guard.

    Used only by this diagnostic script to see the actual text Gemini produced
    even when the production guard would reject it."""
    from services.gemini_client_factory import get_gemini_client
    client = get_gemini_client()
    audio_part = genai_types.Part.from_bytes(data=audio, mime_type=mime)
    user_prompt = "Transcribe the audio verbatim."
    resp = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=[{"role": "user", "parts": [{"text": user_prompt}, audio_part]}],
        config=genai_types.GenerateContentConfig(temperature=0.1),
    )
    out_tokens = getattr(resp.usage_metadata, "candidates_token_count", 0) or 0
    print(f"[RAW] candidates_token_count = {out_tokens}")
    raw = (resp.text or "").strip()
    return _parse_language_tag(raw)


async def inspect(session_id: str, bypass_guard: bool) -> None:
    import uuid as uuid_lib

    row = (
        supabase.table("recording_sessions")
        .select("id, total_duration_seconds, doctor_id")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not row.data:
        print(f"[{session_id[:8]}] not found")
        return

    duration = float(row.data["total_duration_seconds"] or 0)
    doctor_id = row.data["doctor_id"]

    print(f"\n========== {session_id} ==========")
    print(f"Duration: {duration:.1f}s  bypass_guard={bypass_guard}")

    # Uses the same inline-then-storage fallback the backend uses.
    result = get_session_full_audio(uuid_lib.UUID(session_id))
    if not result:
        print(f"[{session_id[:8]}] get_session_full_audio returned None")
        return

    audio_b64, mime = result
    audio = base64.b64decode(audio_b64)
    print(f"MIME: {mime}  Downloaded audio: {len(audio)} bytes")

    if bypass_guard:
        transcript, detected_language = await _raw_transcribe(audio, mime)
    else:
        transcript, detected_language = await transcribe_audio(
            audio_content=audio,
            mime_type=mime,
            session_id=session_id,
            doctor_id=doctor_id,
            audio_duration_seconds=duration,
        )

    out_path = f"/tmp/transcript_{session_id}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(transcript or "")

    t = transcript or ""
    print(f"Detected language: {detected_language}")
    print(f"Transcript length: {len(t)} chars")
    print(f"Saved to: {out_path}")
    print("--- HEAD (first 800 chars) ---")
    print(t[:800])
    print("--- TAIL (last 800 chars) ---")
    print(t[-800:] if len(t) > 800 else "")


async def main(session_ids: list[str], bypass_guard: bool) -> None:
    for sid in session_ids:
        try:
            await inspect(sid, bypass_guard)
        except Exception as e:
            print(f"[{sid[:8]}] FAILED: {e}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("session_ids", nargs="+")
    p.add_argument("--bypass-guard", action="store_true",
                   help="Bypass transcribe_audio's hallucination guard; call Gemini directly")
    args = p.parse_args()

    for var in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "GEMINI_API_KEY"):
        if not os.getenv(var):
            print(f"ERROR: {var} env var is required")
            sys.exit(1)

    asyncio.run(main(args.session_ids, args.bypass_guard))
