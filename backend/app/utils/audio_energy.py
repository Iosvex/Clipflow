"""
Get RMS loudness per second using FFmpeg.
Returns a list of average RMS dB values per second.
"""

import subprocess
import json
from pathlib import Path
from typing import List, Optional

def get_loudness_per_second(video_path: Path, duration: float) -> Optional[List[float]]:
    """
    Extract loudness (RMS dB) per second using ffmpeg astats filter.
    Returns list of per-second RMS values, or None on failure.
    """
    try:
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-af", f"astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
            "-f", "null", "-"
        ]
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        # Parse RMS values from output (look for "lavfi.astats.Overall.RMS_level=...")
        lines = process.stderr.split("\n")
        rms_values = []
        for line in lines:
            if "RMS_level=" in line:
                try:
                    val_str = line.split("=")[-1].strip()
                    if val_str != "-inf":
                        val = float(val_str)
                        rms_values.append(val)
                except ValueError:
                    continue
        if not rms_values:
            return None
        # Ensure length matches duration (1 per second)
        # If fewer, interpolate; if more, trim
        if len(rms_values) > int(duration):
            rms_values = rms_values[:int(duration)]
        elif len(rms_values) < int(duration):
            rms_values += [-60.0] * (int(duration) - len(rms_values))  # pad silence
        return rms_values
    except Exception:
        return None