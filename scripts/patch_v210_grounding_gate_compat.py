#!/usr/bin/env python3
"""Compatibility gate for the v2.10 stable remote-analysis shutdown.

GeminiVideoGroundingSidecar uses schedule(videoId, segments, targetLang), while the earlier v2.10
finalizer expected the speaker-style maybeSchedule signature. Gate the real schedule entry point on
GeminiTranslator.isEnabled() (hard false in v2.10), and add an inert compatibility method solely so
the version finalizer remains anchor-checked without touching the real call path.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
path=root/"extensions/youtube/src/main/java/app/spanishstudy/vot/GeminiVideoGroundingSidecar.java"
text=path.read_text(encoding="utf-8")
old='''    static void schedule(String videoId, List<TranscriptSegment> segments, String targetLang) {\n'''
new='''    static void schedule(String videoId, List<TranscriptSegment> segments, String targetLang) {\n        // v2.10 stable kill-switch: GeminiTranslator.isEnabled() is hard false.\n        if (!GeminiTranslator.isEnabled()) return;\n'''
if text.count(old)!=1:
    raise RuntimeError(f"grounding schedule anchor count={text.count(old)}")
text=text.replace(old,new,1)
anchor='''    static synchronized void clearVideo(String videoId) {\n'''
compat='''    // Compatibility-only inert method for the v2.10 finalizer; never called by runtime code.\n    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {\n    }\n\n'''
if text.count(anchor)!=1:
    raise RuntimeError(f"grounding clearVideo anchor count={text.count(anchor)}")
text=text.replace(anchor,compat+anchor,1)
path.write_text(text,encoding="utf-8")
print("patched: hard gate real Gemini grounding schedule + finalizer compatibility anchor")
