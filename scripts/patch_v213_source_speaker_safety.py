#!/usr/bin/env python3
"""v2.13.0: English-source correctness + explicit caption speaker-turn safety."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v213_source_speaker_safety.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    fetcher = votpkg / "TranscriptFetcher.java"
    controller = study / "SpanishStudyController.java"

    # ---- English source track is authoritative ----------------------------------------------
    rep(fetcher,
'''import app.spanishstudy.vot.SemanticClauseSplitter;
''',
'''import app.spanishstudy.vot.CaptionSpeakerTurnStore;
import app.spanishstudy.vot.CaptionTrackPreference;
import app.spanishstudy.vot.SemanticClauseSplitter;
''',
        "import source-track and speaker-turn helpers")

    old_selector = '''        String targetLang = VoiceCatalog.getIso639(VoiceOverTranslationPatch.resolveTargetLang());
        String firstUrl = null;
        String firstNonGemini = null;
        String targetLangUrl = null;
        String englishUrl = null;
        int searchFrom = tracksIdx;

        while (true) {
            int baseUrlIdx = json.indexOf("\\\"baseUrl\\\":\\\"", searchFrom);
            if (baseUrlIdx < 0 || baseUrlIdx > tracksIdx + 50_000) break;
            baseUrlIdx += "\\\"baseUrl\\\":\\\"".length();

            final int endIdx = json.indexOf('"', baseUrlIdx);
            if (endIdx < 0) break;

            String url = json.substring(baseUrlIdx, endIdx)
                    .replace("\\\\u0026", "&")
                    .replace("\\\\u003d", "=")
                    .replace("\\\\u003e", ">")
                    .replace("\\\\u003c", "<");

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

    new_selector = '''        String targetLang = VoiceCatalog.getIso639(VoiceOverTranslationPatch.resolveTargetLang());
        String bestUrl = null;
        int bestRank = Integer.MAX_VALUE;
        int searchFrom = tracksIdx;

        while (true) {
            int baseUrlIdx = json.indexOf("\\\"baseUrl\\\":\\\"", searchFrom);
            if (baseUrlIdx < 0 || baseUrlIdx > tracksIdx + 50_000) break;
            baseUrlIdx += "\\\"baseUrl\\\":\\\"".length();

            final int endIdx = json.indexOf('"', baseUrlIdx);
            if (endIdx < 0) break;

            String url = json.substring(baseUrlIdx, endIdx)
                    .replace("\\\\u0026", "&")
                    .replace("\\\\u003d", "=")
                    .replace("\\\\u003e", ">")
                    .replace("\\\\u003c", "<");

            final boolean nonGemini = !url.contains("variant=gemini");
            String urlLang = extractLangFromUrl(url);
            int rank = CaptionTrackPreference.rank(urlLang, nonGemini, targetLang);
            if (rank < bestRank) {
                bestRank = rank;
                bestUrl = url;
            }
            searchFrom = endIdx + 1;
        }

        return bestUrl;'''
    rep(fetcher, old_selector, new_selector,
        "prefer English source captions over Spanish dub-target captions")

    rep(fetcher,
'''        String selectedCaptionUrl = findBestCaptionUrl(response);
        SpanishStudyDiagnostics.record("CAPTIONS", selectedCaptionUrl == null
                ? "innertube returned no usable caption track"
                : "innertube selected caption lang=" + extractLangFromUrl(selectedCaptionUrl));
        return new String[]{selectedCaptionUrl, extractPoToken(response)};''',
'''        String selectedCaptionUrl = findBestCaptionUrl(response);
        if (selectedCaptionUrl == null) {
            SpanishStudyDiagnostics.record("CAPTIONS", "innertube returned no usable caption track");
        } else {
            String selectedLang = extractLangFromUrl(selectedCaptionUrl);
            SpanishStudyDiagnostics.record("CAPTIONS", "innertube selected caption lang=" + selectedLang
                    + " policy=english-first");
            if (!CaptionTrackPreference.isEnglish(selectedLang)) {
                SpanishStudyDiagnostics.record("CAPTIONS", "English source unavailable; fallback caption lang="
                        + selectedLang);
            }
        }
        return new String[]{selectedCaptionUrl, extractPoToken(response)};''',
        "diagnose English-first caption policy and fallback")

    # ---- Preserve explicit speaker-turn markers ---------------------------------------------
    rep(fetcher,
'''        SourceCaptionTimingStore.beginTranscript();
''',
'''        SourceCaptionTimingStore.beginTranscript();
        CaptionSpeakerTurnStore.beginTranscript();
''',
        "reset caption speaker-turn timeline per parsed track")

    rep(fetcher,
'''                SourceCaptionTimingStore.addTimedChunk(
                        startMs + offset, startMs + nextOffset, utf8);''',
'''                CaptionSpeakerTurnStore.markFromChunk(
                        startMs + offset, startMs + nextOffset, utf8);
                SourceCaptionTimingStore.addTimedChunk(
                        startMs + offset, startMs + nextOffset, utf8);''',
        "record explicit speaker markers at inner-caption timing")

    rep(fetcher,
'''                    .replace(">>", "")
''',
'''                    .replace(">>", " ")
''',
        "remove speaker marker without accidentally joining words")

    # If the next raw caption line begins a new explicit speaker turn, finish the current sentence
    # before appending the next person's words. Mid-event markers are handled by the timing store,
    # which promotes the marker to a hard semantic pause before phrase splitting.
    rep(fetcher,
'''                    flush = endsSentence(text)
                            || text.length() >= MAX_SENTENCE_CHARS
                            || (gap > MAX_SENTENCE_GAP_MS && text.length() > 80);''',
'''                    flush = CaptionSpeakerTurnStore.isTurnStartNear(lines.get(i + 1).startMs)
                            || endsSentence(text)
                            || text.length() >= MAX_SENTENCE_CHARS
                            || (gap > MAX_SENTENCE_GAP_MS && text.length() > 80);''',
        "hard-stop punctuated sentence merge before explicit speaker turn")

    rep(fetcher,
'''                    flush = gap > UNPUNCTUATED_GAP_MS
                            || (gap > UNPUNCTUATED_SOFT_GAP_MS
                            && startsWithUpperCase(lines.get(i + 1).text))
                            || text.length() >= MAX_UNPUNCTUATED_CHARS;''',
'''                    flush = CaptionSpeakerTurnStore.isTurnStartNear(lines.get(i + 1).startMs)
                            || gap > UNPUNCTUATED_GAP_MS
                            || (gap > UNPUNCTUATED_SOFT_GAP_MS
                            && startsWithUpperCase(lines.get(i + 1).text))
                            || text.length() >= MAX_UNPUNCTUATED_CHARS;''',
        "hard-stop unpunctuated sentence merge before explicit speaker turn")

    # v2.12 makes natural phrases into viable speech units. Carry speaker-turn ownership into that
    # planner so a short line is NEVER re-merged with the previous person's text merely to hit 2.4s.
    rep(fetcher,
'''            rawUnits.add(new SpeechUnitPlanner.Unit(
                    segment.startMs, segment.endMs, segment.text));''',
'''            rawUnits.add(new SpeechUnitPlanner.Unit(
                    segment.startMs, segment.endMs, segment.text,
                    CaptionSpeakerTurnStore.isTurnStartNear(segment.startMs)));''',
        "make explicit speaker turns hard speech-unit boundaries")

    rep(fetcher,
'''        SpanishStudyDiagnostics.record("PHRASE", "speech units " + out.size() + " -> "
                + planned.size() + " floor=" + SpeechUnitPlanner.MIN_UNIT_MS + "ms");''',
'''        SpanishStudyDiagnostics.record("PHRASE", "speech units " + out.size() + " -> "
                + planned.size() + " floor=" + SpeechUnitPlanner.MIN_UNIT_MS + "ms"
                + " speakerTurns=" + CaptionSpeakerTurnStore.count());''',
        "diagnose explicit speaker-turn preservation")

    # ---- Diagnostics version/policy ----------------------------------------------------------
    rep(controller,
'''        report.append("Spanish Dub Study v2.12.0 diagnostics\\n");
        report.append("translationMode=google-only-stable\\n");
        report.append("analysisMode=local-lightweight-only\\n");
        report.append("phraseParsing=pause-aware-local\\n");
        report.append("speechUnitFloor=").append(SpeechUnitPlanner.MIN_UNIT_MS).append("ms\\n");
        report.append("cloudAnalysis=disabled\\n");''',
'''        report.append("Spanish Dub Study v2.13.0 diagnostics\\n");
        report.append("translationMode=google-only-stable\\n");
        report.append("analysisMode=local-lightweight-only\\n");
        report.append("sourceTrackPolicy=english-first\\n");
        report.append("phraseParsing=pause-aware-local\\n");
        report.append("speechUnitFloor=").append(SpeechUnitPlanner.MIN_UNIT_MS).append("ms\\n");
        report.append("captionSpeakerTurns=").append(CaptionSpeakerTurnStore.count()).append('\\n');
        report.append("speakerBoundaryMode=caption-markers-hard-boundary\\n");
        report.append("speakerIdentityMode=pending-local-audio-clustering\\n");
        report.append("cloudAnalysis=disabled\\n");''',
        "label v2.13 source/speaker-safe diagnostics")

    print("v2.13.0 source-track/speaker-turn safety integration complete")


if __name__ == "__main__":
    main()
