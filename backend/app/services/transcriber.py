import requests
import time
from pathlib import Path
from typing import List, Dict, Optional
from ..config import settings

# Try the primary first, then fallback to a mirror (same API, different DNS)
HF_API_URLS = [
    "https://api-inference.huggingface.co/models/openai/whisper-small",
    "https://whisper.s4s.tech",  # community mirror (may not support word_timestamps exactly)
]

def transcribe(video_path: Path, language: Optional[str] = None) -> List[Dict]:
    headers = {"Authorization": f"Bearer {settings.HF_API_TOKEN}"}
    file_size = video_path.stat().st_size

    # If file is larger than 25 MB, extract first 2 minutes of audio as low‑size mp3
    if file_size > 25 * 1024 * 1024:
        import ffmpeg
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

    last_exception = None
    for attempt in range(3):  # up to 3 retries
        for api_url in HF_API_URLS:
            try:
                response = requests.post(api_url, headers=headers, data=audio_data,
                                         params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    # Parse word timestamps (HF returns chunks)
                    words_output = []
                    for chunk in data.get("chunks", []):
                        text = chunk["text"]
                        timestamps = chunk.get("timestamp", (0, 0))
                        start = timestamps[0] / 1000.0 if timestamps[0] else 0
                        end = timestamps[1] / 1000.0 if timestamps[1] else 0
                        for word in text.split():
                            words_output.append({
                                "word": word,
                                "start": start,
                                "end": end,
                                "score": 0.9
                            })
                    return words_output
                else:
                    last_exception = Exception(f"HF API status {response.status_code}: {response.text}")
            except Exception as e:
                last_exception = e
                time.sleep(2 ** attempt)   # wait 2, 4, 8 seconds before next retry
    raise last_exception or RuntimeError("All transcription attempts failed")