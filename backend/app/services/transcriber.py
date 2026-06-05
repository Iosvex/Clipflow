import os
import wave
import json
import subprocess
import tempfile
import requests
import zipfile
from pathlib import Path
from typing import List, Dict, Optional
from vosk import Model, KaldiRecognizer
from ..config import settings

MODEL_DIR = os.path.join(settings.DOWNLOAD_DIR, "vosk-model-small-en-us-0.15")
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

def _ensure_model():
    """Download and unzip the Vosk model if not already present (uses Python only)."""
    if not os.path.exists(MODEL_DIR):
        print(f"Downloading Vosk model (40 MB) to {MODEL_DIR} ...", flush=True)
        os.makedirs(settings.DOWNLOAD_DIR, exist_ok=True)
        zip_path = MODEL_DIR + ".zip"
        
        # Download with requests
        resp = requests.get(MODEL_URL, stream=True, timeout=120)
        resp.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Unzip
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(settings.DOWNLOAD_DIR)
        os.unlink(zip_path)
        print("Model downloaded and extracted.", flush=True)
    return Model(MODEL_DIR)

def transcribe(video_path: Path, language: Optional[str] = None) -> List[Dict]:
    # Convert video to 16kHz mono WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        subprocess.run([
            "ffmpeg", "-i", str(video_path), "-vn",
            "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000",
            wav_path
        ], check=True, capture_output=True)

        model = _ensure_model()
        wf = wave.open(wav_path, "rb")
        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True)

        words_output = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                for w in res.get("result", []):
                    words_output.append({
                        "word": w["word"],
                        "start": w["start"],
                        "end": w["end"],
                        "score": w["conf"]
                    })
        # Final result
        res = json.loads(rec.FinalResult())
        for w in res.get("result", []):
            words_output.append({
                "word": w["word"],
                "start": w["start"],
                "end": w["end"],
                "score": w["conf"]
            })
        return words_output
    finally:
        os.unlink(wav_path)