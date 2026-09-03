#!/usr/bin/env python3
"""v2.12.0: minimum viable speech units + duplicate same-video lifecycle guard."""
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
        raise SystemExit("usage: patch_v212_speech_units.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    fetcher = votpkg / "TranscriptFetcher.java"
    vot = votpkg / "VoiceOverTranslationPatch.java"
    controller = study / "SpanishStudyController.java"

    # ---- Minimum viable source/dub units ----------------------------------------------------
    rep(fetcher,
'''import app.spanishstudy.vot.SourceCaptionTimingStore;
''',
'''import app.spanishstudy.vot.SourceCaptionTimingStore;
import app.spanishstudy.vot.SpeechUnitPlanner;
''',
        "import speech-unit planner")

    rep(fetcher,
'''        return out;
    }

    private static int firstTooShort(long sentenceStartMs, long[] ends, long minMs) {''',
'''        // Natural pause parsing can legitimately produce 0.8-1.5s cues, but a translated Spanish
        // utterance often cannot synthesize/start/finish inside such a tiny immutable deadline. Keep
        // the natural punctuation inside the text, then coalesce adjacent cues into a minimum viable
        // speech unit. This reduces deadline churn without losing the original pause information.
        List<SpeechUnitPlanner.Unit> rawUnits = new ArrayList<>(out.size());
        for (TranscriptSegment segment : out) {
            rawUnits.add(new SpeechUnitPlanner.Unit(
                    segment.startMs, segment.endMs, segment.text));
        }
        List<SpeechUnitPlanner.Unit> plannedUnits = SpeechUnitPlanner.coalesce(rawUnits);
        if (plannedUnits.size() == out.size()) return out;

        List<TranscriptSegment> planned = new ArrayList<>(plannedUnits.size());
        for (SpeechUnitPlanner.Unit unit : plannedUnits) {
            planned.add(new TranscriptSegment(unit.startMs(), unit.endMs(), unit.text(),
                    out.isEmpty() ? "en" : out.get(0).lang));
        }
        SpanishStudyDiagnostics.record("PHRASE", "speech units " + out.size() + " -> "
                + planned.size() + " floor=" + SpeechUnitPlanner.MIN_UNIT_MS + "ms");
        return planned;
    }

    private static int firstTooShort(long sentenceStartMs, long[] ends, long minMs) {''',
        "coalesce tiny natural phrases into viable speech units")

    # ---- Duplicate same-video lifecycle guard ----------------------------------------------
    # YouTube can emit several newVideoLoaded callbacks for the same active video while changing
    # fullscreen/maximized player shells. v2.11 still reset TTS/overlay state before its equality
    # check, which caused the same video to clear/reload and could retarget translation to a stale
    # playhead. Ignore duplicates before *any* timeline state is reset.
    rep(vot,
'''    public static void newVideoLoaded(String videoId) {
        // Always reset so seek detection fires correctly on the first videoTimeChanged''',
'''    public static void newVideoLoaded(String videoId) {
        if (videoId == null || videoId.isBlank()) return;
        if (videoId.equals(currentVideoId)) {
            SpanishStudyDiagnostics.record("VIDEO", "duplicate newVideoLoaded ignored id=" + videoId
                    + " player=" + PlayerType.getCurrent());
            return;
        }
        // Reset only for an actual video transition. Same-video seeks/player-shell changes are
        // handled by videoTimeChanged and must not erase the active dub timeline.
        // Always reset so seek detection fires correctly on the first videoTimeChanged''',
        "ignore duplicate same-video lifecycle callbacks before reset")

    # ---- Diagnostics ------------------------------------------------------------------------
    rep(controller,
'''        report.append("Spanish Dub Study v2.11.0 diagnostics\\n");
        report.append("translationMode=google-only-stable\\n");
        report.append("analysisMode=local-lightweight-only\\n");
        report.append("phraseParsing=pause-aware-local\\n");
        report.append("cloudAnalysis=disabled\\n");''',
'''        report.append("Spanish Dub Study v2.12.0 diagnostics\\n");
        report.append("translationMode=google-only-stable\\n");
        report.append("analysisMode=local-lightweight-only\\n");
        report.append("phraseParsing=pause-aware-local\\n");
        report.append("speechUnitFloor=").append(SpeechUnitPlanner.MIN_UNIT_MS).append("ms\\n");
        report.append("cloudAnalysis=disabled\\n");''',
        "label v2.12 and expose speech-unit floor")

    print("v2.12.0 speech-unit/lifecycle integration complete")


if __name__ == "__main__":
    main()
