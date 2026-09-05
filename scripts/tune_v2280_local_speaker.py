#!/usr/bin/env python3
"""Tune the v2.28 local Visualizer speaker probe for Morphe's ducked original audio."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: tune_v2280_local_speaker.py <morphe-root>")

path = Path(sys.argv[1]).resolve() / "extensions/youtube/src/main/java/app/spanishstudy/vot/LocalSpeakerDiarizer.java"
text = path.read_text(encoding="utf-8")

replacements = [
    (
        "            v.setCaptureSize(wanted);\n",
        "            v.setCaptureSize(wanted);\n            v.setScalingMode(Visualizer.SCALING_MODE_NORMALIZED);\n",
        "Visualizer normalized scaling",
    ),
    (
        "        if (sr >= 8000 && lastRms > 0.02) {\n",
        "        if (sr >= 8000 && lastRms > 0.004) {\n",
        "pitch gate for ducked source audio",
    ),
    (
        "        if (lastRms < 0.018) return;\n",
        "        if (lastRms < 0.003) return;\n",
        "FFT voiced gate for ducked source audio",
    ),
]

for old, new, label in replacements:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    text = text.replace(old, new, 1)
    print("tuned:", label)

path.write_text(text, encoding="utf-8")
