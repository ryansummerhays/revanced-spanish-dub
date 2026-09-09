#!/usr/bin/env python3
"""Compatibility wrapper for v2.33.31 after the v2.33.19 Android-AAR reflection rewrite.

The original v31 patch intentionally uses strict anchors. The Sherpa reflection-compat stage
replaces the direct OfflineSpeakerSegmentation config block, so the first v31 insertion needs to
anchor only on the stable extracted-payload marker. All later v31 edits continue through the
original strict patch unchanged.
"""
from pathlib import Path
import importlib.util
import sys

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "patch_v23331_live_speaker.py"
spec = importlib.util.spec_from_file_location("v23331_base", SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load base v2.33.31 patch")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
_original_rep = mod.rep


def compatible_rep(path, old, new, label, count=1):
    if label == "initialize live ERes2Net extractor from proven embedding payload":
        text = path.read_text(encoding="utf-8")
        if text.count(old) == 0:
            stable = '''            assetsExtracted = true;\n            extractionStep = "payload-ready";\n'''
            replacement = stable + '''            LiveSpeakerOnline.initialize(embedding.getAbsolutePath());\n'''
            return _original_rep(path, stable, replacement, label, 1)
    return _original_rep(path, old, new, label, count)


mod.rep = compatible_rep
mod.main()
