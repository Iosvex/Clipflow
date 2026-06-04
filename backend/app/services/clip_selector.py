"""
Selects the best segment (30–90s) from a video using:
1. YouTube 'Most Replayed' heatmap (if available)
2. Transcript sentiment / excitement
3. Audio energy (RMS loudness)
Scoring is combined into a sliding window, and the highest-scoring window is returned.
"""

import json
import math
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ..utils.heatmap import parse_heatmap
from ..utils.audio_energy import get_loudness_per_second
import ffmpeg

def select_best_clip(
    video_path: Path,
    metadata: dict,
    words: List[Dict],
    min_duration: int = 30,
    max_duration: int = 90,
) -> Tuple[float, float]:
    """
    Returns (start_time, end_time) in seconds for the best clip.
    """
    duration = metadata.get("duration", 0)
    if duration == 0:
        # Fallback: get duration from ffmpeg probe
        probe = ffmpeg.probe(str(video_path))
        duration = float(probe["format"]["duration"])

    if duration <= max_duration:
        return 0.0, duration  # whole video is short enough

    # Build per-second scores array
    scores = [0.0] * int(duration)

    # 1. Heatmap score (from yt-dlp JSON)
    heatmap = parse_heatmap(metadata)
    if heatmap:
        for i, val in enumerate(heatmap):
            if i < len(scores):
                scores[i] += val * 0.4  # weight 40%

    # 2. Transcript-based excitement score (word confidence * heuristics)
    for w in words:
        sec = int(w["start"])
        if sec < len(scores):
            word_score = w.get("score", 0.5)
            # Boost for capital letters, punctuation, length
            if w["word"].isupper() and len(w["word"]) > 1:
                word_score *= 1.5
            if "!" in w["word"] or "?" in w["word"]:
                word_score *= 1.3
            scores[sec] += word_score * 0.3  # weight 30%

    # 3. Audio energy score (loudness)
    energy = get_loudness_per_second(video_path, duration)
    if energy:
        for i, val in enumerate(energy):
            if i < len(scores):
                # Normalize: energy values are usually -50 to 0 dB, shift to positive
                normalized = (val + 50) / 50  # approx 0..1
                scores[i] += normalized * 0.3  # weight 30%

    # Sliding window: find window with max average score
    best_start = 0
    best_avg = 0
    window_frames = max_duration  # window size in seconds

    for start in range(0, int(duration) - min_duration):
        end = start + window_frames
        if end > len(scores):
            end = len(scores)
        window_scores = scores[start:end]
        avg = sum(window_scores) / len(window_scores) if window_scores else 0
        if avg > best_avg:
            best_avg = avg
            best_start = start

    # Fine-tune end: trim to max_duration or end of video
    best_end = min(best_start + max_duration, duration)
    # Ensure minimum clip length
    if best_end - best_start < min_duration:
        best_end = best_start + min_duration
        if best_end > duration:
            best_end = duration
            best_start = max(0, best_end - min_duration)

    return float(best_start), float(best_end)