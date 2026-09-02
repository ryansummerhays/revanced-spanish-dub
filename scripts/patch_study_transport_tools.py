#!/usr/bin/env python3
"""Add practical study transport controls and keep TTS buffering memory-bounded.

No full-video MP3s are persisted. The ordinary in-memory Edge cache is reduced to 400 LRU entries
(typically only several MB) and disappears with the app process.
"""
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched: {label}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_study_transport_tools.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    cache = pkg / "TtsCache.java"
    for path in (vot, cache):
        if not path.is_file():
            raise RuntimeError(f"Required source missing: {path}")

    study_methods = r'''
    /**
     * Replay the current (offset 0) or previous (offset -1) immutable source phrase by seeking the
     * VIDEO itself. This keeps original picture/audio, bilingual subtitles and Spanish TTS on the
     * same source clock instead of replaying a detached TTS clip over a moving video.
     */
    public static boolean replayStudyPhrase(int relativeOffset) {
        Utils.verifyOnMainThread();
        if (segments.isEmpty()) return false;

        final long now = VideoInformation.getVideoTime();
        int index = -1;
        for (int i = 0; i < segments.size(); i++) {
            TranscriptSegment segment = segments.get(i);
            if (now >= segment.startMs && now < segment.endMs) {
                index = i;
                break;
            }
            if (segment.endMs <= now) index = i;
            if (segment.startMs > now && index < 0) {
                index = i;
                break;
            }
        }
        if (index < 0) return false;
        index += relativeOffset;
        if (index < 0 || index >= segments.size()) return false;

        TranscriptSegment target = segments.get(index);
        stopTtsPreservingMultiplier();
        lastSpokenIndex = -1;
        wasExplicitSeek = true;
        return VideoInformation.seekTo(Math.max(0L, target.startMs + 15L));
    }

    /** Human-readable contiguous synthesized Edge audio ready immediately ahead of the playhead. */
    public static String getDubBufferStatusForStudy() {
        Utils.verifyOnMainThread();
        if (segments.isEmpty()) return isLoading ? "Translating…" : "No transcript";
        final String lang = resolveTargetLang();
        final String voice = resolveVoice(lang);
        if (voice == null) return "No voice";
        if (TTS_ENGINE_SYSTEM.equals(voice)) return "System TTS";

        final long now = VideoInformation.getVideoTime();
        long readyUntil = now;
        int readyCount = 0;
        boolean started = false;
        for (int i = 0; i < segments.size(); i++) {
            TranscriptSegment seg = segments.get(i);
            if (seg.endMs <= now) continue;
            if (!started) {
                if (seg.startMs > now + 2_000L) break;
                started = true;
            }
            if (seg.startMs > readyUntil + 1_500L) break;
            byte[] audio = TtsCache.get(currentVideoId, i, voice, lang, seg.text);
            if (audio == null || audio.length == 0) break;
            readyUntil = Math.max(readyUntil, seg.endMs);
            readyCount++;
        }
        long seconds = Math.max(0L, (readyUntil - now + 500L) / 1000L);
        if (readyCount == 0) return isLoading ? "Preparing…" : "0 s ready";
        return seconds + " s ready";
    }

'''
    replace_once(
        vot,
        "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n",
        study_methods + "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n",
        "add replay and buffer-status study APIs",
    )

    replace_once(
        cache,
        "            Utils.createSizeRestrictedMap(1000));\n",
        "            Utils.createSizeRestrictedMap(400));\n",
        "bound Edge TTS in-memory cache to 400 phrases",
    )
    replace_once(
        cache,
        " * ~20 MB, so keeping a few thousand sentences in memory is safe.\n",
        " * ~20 MB. Spanish Study deliberately keeps only a small 400-phrase LRU window in memory;\n * full videos are never persisted and old phrases/videos are automatically evicted.\n",
        "document bounded non-persistent cache",
    )

    print("Study replay/buffer tools and bounded-memory caching integration complete")


if __name__ == "__main__":
    main()
