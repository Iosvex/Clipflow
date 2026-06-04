"""
Parse YouTube Most Replayed heatmap from yt-dlp metadata.
The heatmap is an array of 100 floats (intensity 0..1) covering the video duration.
"""

from typing import Optional, List

def parse_heatmap(metadata: dict) -> Optional[List[float]]:
    """
    Extract heatmap data from yt-dlp JSON.
    Returns a list of 100 intensity values (0.0-1.0) or None if unavailable.
    """
    heatmap = metadata.get("heatmap")
    if not heatmap:
        return None
    # heatmap is a list of dicts: [{"start_time":..., "end_time":..., "value":...}, ...]
    # Convert to 100 evenly spaced points
    duration = metadata.get("duration", 0)
    if duration == 0:
        return None
    points = 100
    result = [0.0] * points
    for segment in heatmap:
        start = segment.get("start_time", 0)
        end = segment.get("end_time", 0)
        val = segment.get("value", 0)
        # Map time range to points
        start_idx = int(start / duration * points)
        end_idx = int(end / duration * points)
        for i in range(start_idx, min(end_idx, points)):
            result[i] = max(result[i], val)
    return result