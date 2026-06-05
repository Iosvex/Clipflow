import os
import wave
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional
from vosk import Model, KaldiRecognizer
from ..config import settings

# Small English model (40 MB) – downloaded once, cached permanently
MODEL_DIR = os.path.join(settings.DOWNLOAD_DIR, "vosk-model-small-en-us-0.15")
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

def _ensure_model():
    """Download the Vosk model if not already present."""
    if not os.path.exists(MODEL_DIR):
        print(f"Downloading Vosk model to {MODEL_DIR} ...", flush=True)
        os.makedirs(settings.DOWNLOAD_DIR, exist_ok=True)
        zip_path = MODEL_DIR + ".zip"
        subprocess.run(["wget", "-O", zip_path, MODEL_URL], check=True)
        subprocess.run(["unzip", "-q", zip_path, "-d", settings.DOWNLOAD_DIR], check=True)
        os.unlink(zip_path)
    return Model(MODEL_DIR)

def transcribe(video_path: Path, language: Optional[str] = None) -> List[Dict]:
    # Convert video to 16kHz mono WAV (Vosk requirement)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video_path), "-vn",
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
                result = json.loads(rec.Result())
                if "result" in result:
                    for w in result["result"]:
                        words_output.append({
                            "word": w["word"],
                            "start": w["start"],
                            "end": w["end"],
                            "score": w["conf"]
                        })
        # Final part
        result = json.loads(rec.FinalResult())
        if "result" in result:
            for w in result["result"]:
                words_output.append({
                    "word": w["word"],
                    "start": w["start"],
                    "end": w["end"],
                    "score": w["conf"]
                })
        return words_output
    finally:
        # Always remove the temporary WAV file
        try:
            os.unlink(wav_path)
        except OSError:
            pass