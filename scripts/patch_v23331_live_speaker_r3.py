#!/usr/bin/env python3
"""v2.33.31 Android-AAR API and JNI retention fix.

Runs the reflection-compatible v31 integration, then adapts LiveSpeakerOnline to the actual
sherpa-onnx 1.13.7 Android Kotlin ABI. The Android wrapper constructor is
(AssetManager?, SpeakerEmbeddingExtractorConfig); null selects newFromFile for our extracted
absolute ONNX path. It also exposes dim(), not the desktop Java getDim()/builder surface.
"""
from pathlib import Path
import importlib.util
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE / "patch_v23331_live_speaker_r2.py"
spec = importlib.util.spec_from_file_location("v23331_r2", BASE)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load v2.33.31 r2 patch")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.mod.main = lambda: None  # r2 imports the base module but does not auto-run it on import

# Execute r2's compatibility behavior explicitly by reproducing its module patch and calling base main.
base = mod.mod
base.rep = mod.compatible_rep
base.main()

if len(sys.argv) != 3:
    raise SystemExit("usage: patch_v23331_live_speaker_r3.py <morphe-root> <repo-root>")
root = Path(sys.argv[1]).resolve()
live = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java"
rules = root / "extensions/youtube/spanishstudy-sherpa-jni.pro"
if not live.is_file() or not rules.is_file():
    raise RuntimeError("missing v31 live source or Sherpa JNI rules")

text = live.read_text(encoding="utf-8")
old = '''            SpeakerEmbeddingExtractorConfig config = SpeakerEmbeddingExtractorConfig.builder()\n                    .setModel(embeddingModelPath)\n                    .setNumThreads(1)\n                    .setDebug(false)\n                    .build();\n            SpeakerEmbeddingExtractor created = new SpeakerEmbeddingExtractor(config);\n            int dim = created.getDim();\n'''
new = '''            SpeakerEmbeddingExtractorConfig config =\n                    new SpeakerEmbeddingExtractorConfig(embeddingModelPath, 1, false, "cpu");\n            // Android AAR Kotlin ABI: null AssetManager intentionally selects newFromFile.\n            SpeakerEmbeddingExtractor created = new SpeakerEmbeddingExtractor(null, config);\n            int dim = created.dim();\n'''
if text.count(old) != 1:
    raise RuntimeError(f"Android embedding API rewrite: expected 1 desktop API block, found {text.count(old)}")
live.write_text(text.replace(old, new), encoding="utf-8")
print("patched: use sherpa-onnx 1.13.7 Android speaker-embedding ABI")

rules_text = rules.read_text(encoding="utf-8")
extra = '''\n# v2.33.31 near-live speaker embedding JNI surface.\n# Kotlin public methods call private native methods whose class/method names are bound by JNI.\n-keep class com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractor { *; }\n-keep class com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractor$Companion { *; }\n-keep class com.k2fsa.sherpa.onnx.OnlineStream { *; }\n-keep class com.k2fsa.sherpa.onnx.OnlineStream$Companion { *; }\n'''
if "v2.33.31 near-live speaker embedding JNI surface" not in rules_text:
    rules.write_text(rules_text.rstrip() + "\n" + extra, encoding="utf-8")
print("patched: retain live embedding/OnlineStream JNI names through R8")

final = live.read_text(encoding="utf-8")
for needle in (
    'new SpeakerEmbeddingExtractorConfig(embeddingModelPath, 1, false, "cpu")',
    'new SpeakerEmbeddingExtractor(null, config)',
    'created.dim()',
):
    if needle not in final:
        raise RuntimeError("missing Android live embedding API: " + needle)
for forbidden in ('SpeakerEmbeddingExtractorConfig.builder()', 'created.getDim()'):
    if forbidden in final:
        raise RuntimeError("desktop-only API remains: " + forbidden)
print("v2.33.31 r3 Android ABI patch complete")
