#!/usr/bin/env python3
"""Source equivalent of the stable v2.33.12 caption bootstrap retry.

The first newVideoLoaded callback often arrives as INLINE_MINIMAL and legitimately skips transcript
loading. A later callback for the same video, after the WATCH player becomes eligible, must pass
through the eligibility/load gate without resetting per-video state again.
"""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v23312_caption_bootstrap_source.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    if not vot.is_file(): raise RuntimeError(f"missing VOT source: {vot}")

    rep(
        vot,
        "        if (videoId.equals(currentVideoId)) return;\n\n"
        "        PlayerVolumePatch.resetSpeakerAnalysisForStudy();\n",
        "        final boolean sameVideo = videoId.equals(currentVideoId);\n"
        "        if (!sameVideo) {\n"
        "            PlayerVolumePatch.resetSpeakerAnalysisForStudy();\n",
        "replace same-video hard return with retryable bootstrap branch",
    )

    rep(
        vot,
        "        currentVideoId = videoId;\n"
        "        segments = new ArrayList<>();\n"
        "        SpanishStudyController.onVideoCleared();\n"
        "        httpErrorDialogShownThisVideo = false;\n\n"
        "        if (!Settings.VOT_ENABLED.get() || !sessionEnabled) return;\n",
        "            currentVideoId = videoId;\n"
        "            segments = new ArrayList<>();\n"
        "            SpanishStudyController.onVideoCleared();\n"
        "            httpErrorDialogShownThisVideo = false;\n"
        "        }\n\n"
        "        // Same-video callbacks still pass this existing eligibility gate. This is the\n"
        "        // stable v2.33.12 behavior that recovers from an initial INLINE_MINIMAL callback.\n"
        "        if (!Settings.VOT_ENABLED.get() || !sessionEnabled) return;\n",
        "close new-video-only state mutation before existing eligibility gate",
    )

    print("v2.33.12 caption bootstrap source patch complete")
    print("PRESERVED: same-video state and speaker clusters")
    print("RECOVERED: later eligible same-video callback can invoke guarded loadTranscript")


if __name__ == "__main__":
    main()
