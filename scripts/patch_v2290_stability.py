#!/usr/bin/env python3
"""v2.29: restore narrow proven reliability fixes on top of the v2.28 stock-Morphe baseline."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2290_stability.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"

    vot = pkg / "VoiceOverTranslationPatch.java"
    translator = pkg / "TranscriptTranslator.java"
    prefetch = pkg / "TtsPrefetcher.java"
    engine = pkg / "TtsEngine.java"
    subtitle = study / "SpanishSubtitleOverlay.java"
    for path in (vot, translator, prefetch, engine, subtitle):
        if not path.is_file():
            raise RuntimeError(f"missing source: {path}")

    # Restore the small, previously tested output-budget helper from v2.16/v2.18. This changes
    # only max_tokens; Morphe keeps its native batching, ordering, streaming and seek behavior.
    budget_src = repo / "overlay/v216/app/spanishstudy/vot/OpenRouterBudget.java"
    if not budget_src.is_file():
        raise RuntimeError(f"missing OpenRouterBudget source: {budget_src}")
    shutil.copy2(budget_src, study / "OpenRouterBudget.java")
    print("copied: OpenRouterBudget.java")

    rep(
        translator,
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "import app.spanishstudy.vot.OpenRouterBudget;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "OpenRouter budget import",
    )
    rep(
        translator,
        "        JSONObject body = new JSONObject()\n"
        "                .put(\"model\", model)\n",
        "        final int maxOutputTokens = OpenRouterBudget.maxOutputTokens(joined.length(), segments.size());\n"
        "        JSONObject body = new JSONObject()\n"
        "                .put(\"model\", model)\n",
        "compute character-aware OpenRouter output budget",
    )
    rep(
        translator,
        "                .put(\"max_tokens\", segments.size() * 30)\n",
        "                .put(\"max_tokens\", maxOutputTokens)\n",
        "use character-aware OpenRouter output budget",
    )
    rep(
        translator,
        "\"OpenRouter request bodyBytes=\" + bodyBytes.length + \" maxTokens=\" + (segments.size() * 30)\n",
        "\"OpenRouter request bodyBytes=\" + bodyBytes.length + \" maxTokens=\" + maxOutputTokens\n",
        "report actual OpenRouter output budget",
    )

    # Stock Morphe initializes the streaming result list with source text, then applyBatch() marks
    # every slot as target-language on each partial callback. That makes untouched tail slots look
    # translated and later roll backward when cardinality validation requeues them. Publish only
    # slots whose streamed text has actually changed; the normal completed-batch path still commits
    # legitimate identical translations (names, numbers, etc.).
    rep(
        translator,
        "        return partial -> {\n"
        "            List<TranscriptSegment> snap = new ArrayList<>(working);\n"
        "            applyBatch(snap, batch, offset, partial, lang);\n"
        "            mainHandler.post(() -> onUpdate.accept(snap));\n"
        "        };\n",
        "        return partial -> {\n"
        "            List<TranscriptSegment> snap = new ArrayList<>(working);\n"
        "            final int limit = Math.min(batch.size(), partial.size());\n"
        "            for (int j = 0; j < limit; j++) {\n"
        "                TranscriptSegment orig = batch.get(j);\n"
        "                String streamed = partial.get(j);\n"
        "                if (streamed != null && !streamed.equals(orig.text)) {\n"
        "                    snap.set(offset + j, new TranscriptSegment(\n"
        "                            orig.startMs, orig.endMs, streamed, lang));\n"
        "                }\n"
        "            }\n"
        "            mainHandler.post(() -> onUpdate.accept(snap));\n"
        "        };\n",
        "publish only genuinely streamed translation slots",
    )

    # Start the existing Morphe prefetcher as progressive translations become usable instead of
    # waiting for the full-video translation worker to finish. Untranslated slots are already
    # ignored by TtsPrefetcher based on their source language.
    rep(
        vot,
        "                                segments = updated;\n"
        "                                SpanishStudyController.onTranscriptUpdated(updated);\n",
        "                                segments = updated;\n"
        "                                SpanishStudyController.onTranscriptUpdated(updated);\n"
        "                                TtsPrefetcher.updateVideo(videoId, updated);\n",
        "feed progressive translations to native TTS prefetch",
    )

    # updateVideo used to reset the prefetch playhead to zero on every snapshot. Preserve the
    # current playhead when only text changed for the same video, otherwise progressive updates
    # would repeatedly send prefetch back to the beginning.
    rep(
        prefetch,
        "        synchronized (lock) {\n"
        "            if (!videoId.equals(currentVideoId)) {\n"
        "                loadingLatch = new CountDownLatch(1);\n"
        "            }\n"
        "            currentVideoId = videoId;\n"
        "            currentSegments = Collections.unmodifiableList(segments);\n"
        "            currentVideoTimeMs = 0;\n",
        "        synchronized (lock) {\n"
        "            final boolean videoChanged = !videoId.equals(currentVideoId);\n"
        "            if (videoChanged) {\n"
        "                loadingLatch = new CountDownLatch(1);\n"
        "            }\n"
        "            currentVideoId = videoId;\n"
        "            currentSegments = Collections.unmodifiableList(segments);\n"
        "            if (videoChanged) currentVideoTimeMs = 0;\n",
        "preserve prefetch playhead across progressive snapshots",
    )

    # Expose read-only MediaPlayer timing to the subtitle layer. MediaPlayer position is the most
    # faithful clock available: it starts only when Edge audio actually starts and naturally follows
    # pauses, seek-into offsets and playback-rate changes.
    rep(
        engine,
        "    boolean isSpeaking() {\n"
        "        Utils.verifyOnMainThread();\n"
        "        return speaking;\n"
        "    }\n",
        "    boolean isSpeaking() {\n"
        "        Utils.verifyOnMainThread();\n"
        "        return speaking;\n"
        "    }\n\n"
        "    long getCurrentPlaybackPositionMsForStudy() {\n"
        "        Utils.verifyOnMainThread();\n"
        "        MediaPlayer player = currentPlayer;\n"
        "        if (player == null) return -1;\n"
        "        try { return player.getCurrentPosition(); } catch (Exception ignored) { return -1; }\n"
        "    }\n\n"
        "    long getCurrentPlaybackDurationMsForStudy() {\n"
        "        Utils.verifyOnMainThread();\n"
        "        MediaPlayer player = currentPlayer;\n"
        "        if (player == null) return -1;\n"
        "        try { return player.getDuration(); } catch (Exception ignored) { return -1; }\n"
        "    }\n",
        "expose read-only Edge MediaPlayer clock",
    )

    rep(
        vot,
        "    public static long getTtsEndVideoTimeMsForStudy() {\n"
        "        Utils.verifyOnMainThread();\n"
        "        return ttsEndVideoTimeMs;\n"
        "    }\n\n",
        "    public static long getTtsEndVideoTimeMsForStudy() {\n"
        "        Utils.verifyOnMainThread();\n"
        "        return ttsEndVideoTimeMs;\n"
        "    }\n\n"
        "    /** True while the selected Edge voice is synthesizing or playing. */\n"
        "    public static boolean isEdgeSpeechActiveForStudy() {\n"
        "        Utils.verifyOnMainThread();\n"
        "        String voice = resolveVoice(resolveTargetLang());\n"
        "        return voice != null && !TTS_ENGINE_SYSTEM.equals(voice) && ttsEngine.isSpeaking();\n"
        "    }\n\n"
        "    /** Actual Edge MediaPlayer progress in [0,1], or -1 before playback has started. */\n"
        "    public static double getEdgePlaybackProgressForStudy() {\n"
        "        Utils.verifyOnMainThread();\n"
        "        long duration = ttsEngine.getCurrentPlaybackDurationMsForStudy();\n"
        "        long position = ttsEngine.getCurrentPlaybackPositionMsForStudy();\n"
        "        if (duration <= 0 || position < 0) return -1.0;\n"
        "        return Math.max(0.0, Math.min(1.0, position / (double) duration));\n"
        "    }\n\n",
        "expose actual Edge playback progress to subtitles",
    )

    # When Edge is active, subtitle pages follow the MP3 itself. During synthesis there is no
    # MediaPlayer yet, so hold page 1 instead of advancing silently with the video clock. System TTS
    # and non-speaking captions retain the stock/source-window fallback.
    rep(
        subtitle,
        "        double progress = SubtitlePagePolicy.progress(timeMs, windowStart, windowEnd);\n"
        "        String shownEs = \"\";\n",
        "        double progress;\n"
        "        String clockSource;\n"
        "        if (activeSpoken == index && VoiceOverTranslationPatch.isEdgeSpeechActiveForStudy()) {\n"
        "            double mediaProgress = VoiceOverTranslationPatch.getEdgePlaybackProgressForStudy();\n"
        "            if (mediaProgress >= 0) {\n"
        "                progress = mediaProgress;\n"
        "                clockSource = \"tts-media\";\n"
        "            } else {\n"
        "                progress = 0.0;\n"
        "                clockSource = \"tts-wait\";\n"
        "            }\n"
        "        } else {\n"
        "            progress = SubtitlePagePolicy.progress(timeMs, windowStart, windowEnd);\n"
        "            clockSource = \"video\";\n"
        "        }\n"
        "        String shownEs = \"\";\n",
        "clock subtitle pages from actual Edge audio",
    )
    rep(
        subtitle,
        "                            + \" displayWindow=\" + windowStart + \"-\" + windowEnd\n"
        "                            + \" speaker=\" + (speaker.isBlank() ? \"?\" : speaker));\n",
        "                            + \" displayWindow=\" + windowStart + \"-\" + windowEnd\n"
        "                            + \" clock=\" + clockSource\n"
        "                            + \" speaker=\" + (speaker.isBlank() ? \"?\" : speaker));\n",
        "log subtitle clock source",
    )

    print("v2.29 stability patch complete")


if __name__ == "__main__":
    main()
