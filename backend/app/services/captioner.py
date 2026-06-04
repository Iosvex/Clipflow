"""
Generates a dynamic ASS subtitle file with word-by-word karaoke highlighting
and burns it onto the video using FFmpeg.
"""

import ffmpeg
from pathlib import Path
from typing import List, Dict
import uuid
import os
from ..config import settings

# Basic ASS style template
ASS_HEADER = """[Script Info]
Title: ClipFlow Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,1,2,30,30,60,1
Style: Highlight,Montserrat,72,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,1,2,30,30,60,1
Style: Emoji,Arial,56,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,30,30,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

EMOJI_MAP = {
    "love": "❤️", "laugh": "😂", "funny": "🤣", "amazing": "🤯",
    "wow": "😲", "omg": "😱", "crazy": "🤪", "fire": "🔥",
    "money": "💰", "win": "🏆", "yay": "🎉", "happy": "😊",
    "sad": "😢", "angry": "😡", "shock": "💥", "genius": "🧠"
}

def generate_ass(words: List[Dict], duration: float) -> str:
    """
    Build ASS file content from word-level timestamps.
    Uses karaoke effect: current word highlighted, rest white.
    Inserts emojis on high-confidence exciting words.
    """
    lines = [ASS_HEADER]

    # Group words into lines (max 4 words per subtitle line, split on pauses)
    subtitle_groups = []
    current_group = []
    for w in words:
        current_group.append(w)
        # Start a new line if pause > 0.3 seconds or 4 words reached
        if len(current_group) >= 4 or (w == words[-1]) or (
            current_group[-1]["end"] - current_group[-1]["start"] > 0.3 and len(current_group) > 2
        ):
            subtitle_groups.append(current_group)
            current_group = []
    if current_group:
        subtitle_groups.append(current_group)

    for idx, group in enumerate(subtitle_groups):
        if not group:
            continue
        start = group[0]["start"]
        end = group[-1]["end"]

        # Build karaoke text: {\kf<duration_ms>}word{\kf0}
        karaoke_parts = []
        for w in group:
            dur_ms = int((w["end"] - w["start"]) * 1000) + 50  # slight padding
            clean_word = w["word"].strip()
            karaoke_parts.append(f"{{\\kf{dur_ms}}}{clean_word}")
        karaoke_text = " ".join(karaoke_parts)

        # Default style (white word, later highlight)
        line = f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{karaoke_text}"
        lines.append(line)

        # Emoji insertions: if a word is exciting and confidence high, insert emoji near it
        for w in group:
            if w.get("score", 0) > 0.85:
                word_lower = w["word"].strip().lower().rstrip(",.!?")
                if word_lower in EMOJI_MAP:
                    emoji = EMOJI_MAP[word_lower]
                    emoji_start = w["start"] - 0.2
                    emoji_end = w["start"] + 2.0
                    emoji_line = f"Dialogue: 0,{_ass_time(emoji_start)},{_ass_time(emoji_end)},Emoji,,0,0,0,,{emoji}"
                    lines.append(emoji_line)

    return "\n".join(lines)

def _ass_time(seconds: float) -> str:
    """Convert float seconds to ASS time format: H:MM:SS.CC"""
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int((seconds * 100) % 100)
    return f"{hours}:{mins:02d}:{secs:02d}.{centiseconds:02d}"

def burn_captions(
    input_video: Path,
    words: List[Dict],
    output_dir: str = None,
    font_path: str = None
) -> Path:
    """
    Creates an ASS subtitle file, burns it onto the video, returns final clip path.
    """
    if output_dir is None:
        output_dir = settings.CLIP_DIR
    os.makedirs(output_dir, exist_ok=True)

    job_id = uuid.uuid4().hex[:8]
    ass_path = Path(output_dir) / f"subs_{job_id}.ass"
    output_video = Path(output_dir) / f"captioned_{job_id}.mp4"

    # Get video duration via ffprobe
    probe = ffmpeg.probe(str(input_video))
    duration = float(probe["format"]["duration"])

    ass_content = generate_ass(words, duration)
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    # Burn subtitles
    (
        ffmpeg
        .input(str(input_video))
        .filter("ass", filename=str(ass_path))
        .output(str(output_video), vcodec="libx264", acodec="aac", preset="fast", crf=22)
        .overwrite_output()
        .run(quiet=True)
    )
    return output_video