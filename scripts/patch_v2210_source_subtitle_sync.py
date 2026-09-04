#!/usr/bin/env python3
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
        raise SystemExit("usage: patch_v2210_source_subtitle_sync.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    fetcher = pkg / "TranscriptFetcher.java"
    overlay = study / "SpanishSubtitleOverlay.java"
    controller = study / "SpanishStudyController.java"
    sidecar = study / "GeminiSpeakerDiarizationSidecar.java"

    for path in (fetcher, overlay, controller, sidecar):
        if not path.is_file():
            raise RuntimeError(f"missing v2.20 generated source: {path}")

    shutil.copy2(repo / "overlay/src/app/spanishstudy/vot/CaptionTrackPreference.java",
                 study / "CaptionTrackPreference.java")
    shutil.copy2(repo / "overlay/v221/app/spanishstudy/vot/SubtitleSyncPolicy.java",
                 study / "SubtitleSyncPolicy.java")
    print("copied: CaptionTrackPreference.java")
    print("copied: SubtitleSyncPolicy.java")

    # --------------------------------------------------------------------------------------
    # Restore the English-first source policy that existed before the Morphe-core reset.
    # English is the study/source language; Spanish is the dub target and must not bypass
    # OpenRouter merely because YouTube happens to expose a Spanish caption track.
    # --------------------------------------------------------------------------------------
    rep(fetcher,
        '''import app.spanishstudy.vot.SpanishStudyController;\n''',
        '''import app.spanishstudy.vot.CaptionTrackPreference;\nimport app.spanishstudy.vot.SpanishStudyController;\nimport app.spanishstudy.vot.SpanishStudyDiagnostics;\n''',
        "import English-first caption policy and diagnostics")

    old_selector = r'''        String targetLang = VoiceCatalog.getIso639(VoiceOverTranslationPatch.resolveTargetLang());
        String firstUrl = null;
        String firstNonGemini = null;
        String targetLangUrl = null;
        String englishUrl = null;
        int searchFrom = tracksIdx;

        while (true) {
            int baseUrlIdx = json.indexOf("\"baseUrl\":\"", searchFrom);
            if (baseUrlIdx < 0 || baseUrlIdx > tracksIdx + 50_000) break;
            baseUrlIdx += "\"baseUrl\":\"".length();

            final int endIdx = json.indexOf('"', baseUrlIdx);
            if (endIdx < 0) break;

            String url = json.substring(baseUrlIdx, endIdx)
                    .replace("\\u0026", "&")
                    .replace("\\u003d", "=")
                    .replace("\\u003e", ">")
                    .replace("\\u003c", "<");

            if (firstUrl == null) firstUrl = url;
            final boolean nonGemini = !url.contains("variant=gemini");
            if (firstNonGemini == null && nonGemini) firstNonGemini = url;

            String urlLang = extractLangFromUrl(url).split("-")[0];
            if (targetLangUrl == null && nonGemini && targetLang.equals(urlLang)) targetLangUrl = url;
            if (englishUrl == null && nonGemini && "en".equals(urlLang)) englishUrl = url;

            searchFrom = endIdx + 1;
        }

        if (targetLangUrl != null) return targetLangUrl;
        if (englishUrl != null) return englishUrl;
        return firstNonGemini != null ? firstNonGemini : firstUrl;'''

    new_selector = r'''        String targetLang = VoiceCatalog.getIso639(VoiceOverTranslationPatch.resolveTargetLang());
        String bestUrl = null;
        int bestRank = Integer.MAX_VALUE;
        int searchFrom = tracksIdx;

        while (true) {
            int baseUrlIdx = json.indexOf("\"baseUrl\":\"", searchFrom);
            if (baseUrlIdx < 0 || baseUrlIdx > tracksIdx + 50_000) break;
            baseUrlIdx += "\"baseUrl\":\"".length();

            final int endIdx = json.indexOf('"', baseUrlIdx);
            if (endIdx < 0) break;

            String url = json.substring(baseUrlIdx, endIdx)
                    .replace("\\u0026", "&")
                    .replace("\\u003d", "=")
                    .replace("\\u003e", ">")
                    .replace("\\u003c", "<");

            final boolean nonGemini = !url.contains("variant=gemini");
            final String urlLang = extractLangFromUrl(url);
            final int rank = CaptionTrackPreference.rank(urlLang, nonGemini, targetLang);
            if (rank < bestRank) {
                bestRank = rank;
                bestUrl = url;
            }
            searchFrom = endIdx + 1;
        }

        return bestUrl;'''
    rep(fetcher, old_selector, new_selector,
        "prefer English source captions before Spanish dub-target captions")

    rep(fetcher,
        '''        String response = Requester.parseString(conn);\n        return new String[]{findBestCaptionUrl(response), extractPoToken(response)};''',
        '''        String response = Requester.parseString(conn);\n        String selectedCaptionUrl = findBestCaptionUrl(response);\n        if (selectedCaptionUrl == null) {\n            SpanishStudyDiagnostics.record("CAPTION-TRACK",\n                    "policy=english-first selected=none");\n        } else {\n            String selectedLang = extractLangFromUrl(selectedCaptionUrl);\n            SpanishStudyDiagnostics.record("CAPTION-TRACK",\n                    "policy=english-first selected=" + selectedLang\n                            + " english=" + CaptionTrackPreference.isEnglish(selectedLang));\n        }\n        return new String[]{selectedCaptionUrl, extractPoToken(response)};''',
        "log selected source caption language")

    # --------------------------------------------------------------------------------------
    # Keep page progress monotonic during ordinary playback. v2.20 could show page 2 from
    # source-fallback timing and then jump backward to page 1 when a late TTS window arrived.
    # Only a genuine backward seek is allowed to rewind bilingual page progress.
    # --------------------------------------------------------------------------------------
    rep(overlay,
        '''    private static int lastEnglishPage = -1;''',
        '''    private static int lastEnglishPage = -1;\n    private static final Map<Integer, Double> progressFloors = new HashMap<>();\n    private static long lastUpdateTimeMs = Long.MIN_VALUE;''',
        "add monotonic bilingual progress state")

    rep(overlay,
        '''        translatedPages.clear();\n        resetPageTelemetry();''',
        '''        translatedPages.clear();\n        progressFloors.clear();\n        lastUpdateTimeMs = Long.MIN_VALUE;\n        resetPageTelemetry();''',
        "reset subtitle progress on new transcript")

    rep(overlay,
        '''        ensureAttached(a);\n        updateLayout(a);\n\n        int sourceIndex = findSourceIndex(timeMs);''',
        '''        ensureAttached(a);\n        updateLayout(a);\n\n        final boolean backwardSeek = SubtitleSyncPolicy.isBackwardSeek(lastUpdateTimeMs, timeMs);\n        if (backwardSeek) {\n            progressFloors.clear();\n            resetPageTelemetry();\n            SpanishStudyDiagnostics.record("SUBTITLE-SYNC",\n                    "action=backward-seek-reset from=" + lastUpdateTimeMs + " to=" + timeMs);\n        }\n        lastUpdateTimeMs = timeMs;\n\n        int sourceIndex = findSourceIndex(timeMs);''',
        "detect real backward seeks before page selection")

    rep(overlay,
        '''        if (ttsActive) {\n            progress = activeTts.progress(timeMs);\n        } else if (source != null) {\n            progress = SubtitlePagePolicy.progress(timeMs, source.startMs, source.endMs);\n        }\n\n        ShownPage sourcePage = pageFor(sourcePages, pairSourceIndex,''',
        '''        if (ttsActive) {\n            progress = activeTts.progress(timeMs);\n        } else if (source != null) {\n            progress = SubtitlePagePolicy.progress(timeMs, source.startMs, source.endMs);\n        }\n        if (displayIndex >= 0) {\n            double previousProgress = progressFloors.getOrDefault(displayIndex, 0.0);\n            progress = SubtitleSyncPolicy.monotonicProgress(\n                    previousProgress, progress, backwardSeek);\n            progressFloors.put(displayIndex, progress);\n        }\n\n        ShownPage sourcePage = pageFor(sourcePages, pairSourceIndex,''',
        "prevent late TTS windows from rewinding subtitle pages")

    rep(overlay,
        '''        translatedPages.clear();\n        sourcePages.clear();\n        sourceCursor = 0;\n        resetPageTelemetry();''',
        '''        translatedPages.clear();\n        sourcePages.clear();\n        progressFloors.clear();\n        lastUpdateTimeMs = Long.MIN_VALUE;\n        sourceCursor = 0;\n        resetPageTelemetry();''',
        "clear subtitle progress state")

    # --------------------------------------------------------------------------------------
    # Speaker sidecar: v2.20 moved from HTTP 400 to valid HTTP 200 agentic requests, but the
    # default 22s client deadline is too short for agentic video navigation. Reduce thinking,
    # increase response allowance, and permit a longer read window. This remains isolated.
    # --------------------------------------------------------------------------------------
    rep(sidecar,
        '''    private static final int READ_TIMEOUT_MS = 22_000;''',
        '''    private static final int READ_TIMEOUT_MS = 45_000;''',
        "allow agentic speaker analysis time to finish")

    rep(sidecar,
        '''                .put("generation_config", new JSONObject()\n                        .put("temperature", 0.0)\n                        .put("max_output_tokens", Math.max(500, segments.size() * 45)))''',
        '''                .put("generation_config", new JSONObject()\n                        .put("thinking_level", "low")\n                        .put("max_output_tokens", Math.max(1200, segments.size() * 80)))''',
        "use low-thinking larger structured speaker response")

    # --------------------------------------------------------------------------------------
    # Diagnostics: make the two user-visible subtitle toggles and restored source policy obvious.
    # --------------------------------------------------------------------------------------
    rep(controller,
        'report.append("Spanish Dub Study v2.20.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.21.0 diagnostics\\n");',
        "bump diagnostics version")
    rep(controller,
        'report.append("subtitleTextCleanup=display-only-spacing+punctuation-normalization\\n");',
        'report.append("subtitleTextCleanup=display-only-spacing+punctuation-normalization\\n");\n'
        '        report.append("subtitlePageDirection=monotonic-unless-backward-seek\\n");\n'
        '        report.append("sourceTrackPolicy=english-first-non-gemini+target-fallback\\n");',
        "publish source and subtitle sync policies")
    rep(controller,
        '''        Activity activity = Utils.getActivity();\n        report.append("speakerRecognitionEnabled=").append(activity != null''',
        '''        Activity activity = Utils.getActivity();\n        report.append("spanishSubtitlesEnabled=").append(activity != null\n                && SpanishStudyPrefs.showSubtitles(activity)).append('\\n');\n        report.append("englishSubtitlesEnabled=").append(activity != null\n                && SpanishStudyPrefs.showEnglishSubtitles(activity)).append('\\n');\n        report.append("speakerRecognitionEnabled=").append(activity != null''',
        "publish bilingual subtitle toggle state")
    rep(controller,
        'report.append("speakerBackend=gemini-3.7-flash-youtube-agentic-audio-sidecar\\n");',
        'report.append("speakerBackend=gemini-3.7-flash-youtube-agentic-audio-sidecar-low-thinking\\n");',
        "publish speaker latency policy")

    print("v2.21 English-source and bilingual subtitle sync integration complete")


if __name__ == "__main__":
    main()
