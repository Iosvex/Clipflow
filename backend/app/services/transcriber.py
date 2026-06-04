"""
Transcribes audio using Hugging Face's free Inference API (Whisper).
No credit card required – just a free Hugging Face account & API token.
"""
import requests
from pathlib import Path
from typing import List, Dict, Optional
from ..config import settings
import ffmpeg

HF_API_URL = "https://api-inference.huggingface.co/models/openai/whisper-small"

def transcribe(video_path: Path, language: Optional[str] = None) -> List[Dict]:
    headers = {"Authorization": f"Bearer {settings.HF_API_TOKEN}"}

    # If file is larger than 25 MB, extract first 2 minutes of audio as low‑size mp3
    file_size = video_path.stat().st_size
    if file_size > 25 * 1024 * 1024:
        audio_path = video_path.with_suffix(".mp3")
        (
            ffmpeg
            .input(str(video_path), ss=0, t=120)
            .output(str(audio_path), acodec="libmp3lame", ac=1, ar="16000")
            .overwrite_output()
            .run(quiet=True)
        )
        with open(audio_path, "rb") as af:
            audio_data = af.read()
        audio_path.unlink(missing_ok=True)
    else:
        with open(video_path, "rb") as f:
            audio_data = f.read()

    params = {"word_timestamps": "true"}
    if language:
        params["language"] = language

    response = requests.post(HF_API_URL, headers=headers, data=audio_data, params=params)
    if response.status_code != 200:
        raise Exception(f"Hugging Face API error: {response.text}")

    data = response.json()

    # HF returns chunks, each with 'text' and 'timestamp' (start, end) in milliseconds
    words_output = []
    for chunk in data.get("chunks", []):
        text = chunk["text"]
        timestamps = chunk.get("timestamp", (0, 0))
        start = timestamps[0] / 1000.0 if timestamps[0] else 0
        end = timestamps[1] / 1000.0 if timestamps[1] else 0
        # Split text into words (basic split; fine for our captioner)
        for word in text.split():
            words_output.append({
                "word": word,
                "start": start,
                "end": end,
                "score": 0.9   # HF doesn't give per‑word confidence; high default works
            })
    return words_output