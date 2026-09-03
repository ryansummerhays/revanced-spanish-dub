#!/usr/bin/env python3
"""v2.11.0: pause-aware local phrase parsing + safer startup session behavior."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def rep_count(path: Path, old: str, new: str, expected: int, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} anchors, found {count} in {path}")
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v211_natural_phrases.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    fetcher = votpkg / "TranscriptFetcher.java"
    vot = votpkg / "VoiceOverTranslationPatch.java"
    button = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/videoplayer/VoiceOverTranslationButton.java"
    controller = study / "SpanishStudyController.java"

    # ---- Pause-aware phrase parser -----------------------------------------------------------
    # v2.6 preserved JSON3 inner timing but the phrase splitter still consumed text alone. Feed it
    # measured inter-word gaps so ASR run-ons can gain conservative punctuation and split at real
    # pauses instead of relying only on punctuation that YouTube happened to emit.
    rep(fetcher,
'''            List<String> pieces = new ArrayList<>(SemanticClauseSplitter.split(sentence.text));''',
'''            long[] interWordGaps = SourceCaptionTimingStore.interWordGaps(
                    sentence.startMs, sentence.endMs, sentence.text);
            List<String> pieces = new ArrayList<>(
                    SemanticClauseSplitter.split(sentence.text, interWordGaps));''',
        "wire preserved word pauses into semantic phrase parser")

    # ---- Session startup safety --------------------------------------------------------------
    # The player button previously toggled an already-enabled session OFF while the initial
    # transcript was still loading. The button's loading appearance made that easy to trigger and
    # it created a multi-second first-phrase delay. During an active transcript load, keep the
    # session enabled; once loading finishes, the exact same tap still disables normally.
    rep(vot,
'''    /** Flips the session enabled flag and either stops TTS or kicks off transcript loading. */
    public static void toggleTranslation() {''',
'''    /**
     * Player-button entry point. A tap while an already-enabled session is still loading means
     * "keep starting" rather than "turn it off". This prevents startup player transitions / an
     * ambiguous loading icon from cancelling the session just before the first batch publishes.
     */
    public static void toggleTranslationFromPlayerButton() {
        Utils.verifyOnMainThread();
        if (sessionEnabled && isLoading) {
            SpanishStudyDiagnostics.record("SESSION", "player tap while loading; kept enabled");
            notifyStateChanged();
            return;
        }
        toggleTranslation();
    }

    /** Flips the session enabled flag and either stops TTS or kicks off transcript loading. */
    public static void toggleTranslation() {''',
        "add loading-safe player session toggle")

    rep_count(button,
'''VoiceOverTranslationPatch.toggleTranslation();''',
'''VoiceOverTranslationPatch.toggleTranslationFromPlayerButton();''',
        2,
        "route both player buttons through loading-safe toggle")

    # ---- Diagnostics cleanup ----------------------------------------------------------------
    ctext = controller.read_text(encoding="utf-8")
    old_header = '''        report.append("Spanish Dub Study v2.10.0 diagnostics\\n");
        report.append("translationMode=google-only-stable\\n");
        report.append("geminiRuntime=disabled-in-v2.10\\n");
        report.append("analysisMode=local-lightweight-only\\n");'''
    new_header = '''        report.append("Spanish Dub Study v2.11.0 diagnostics\\n");
        report.append("translationMode=google-only-stable\\n");
        report.append("analysisMode=local-lightweight-only\\n");
        report.append("phraseParsing=pause-aware-local\\n");
        report.append("cloudAnalysis=disabled\\n");'''
    if old_header not in ctext:
        raise RuntimeError("v2.11 diagnostics header anchor not found")
    ctext = ctext.replace(old_header, new_header, 1)

    # Remove stale preference/status lines that made the stable build look as though Gemini/media
    # analysis were still active. Stored prefs remain untouched for future experimental releases.
    stale_keys = (
        'geminiTranslationSelected=', 'geminiConfigured=', 'geminiModel=',
        'videoGrounding=', 'videoGroundingActive=', 'videoGroundingScope=',
        'speakerRecognition=', 'speakerVoices=', 'speakerProfiles=',
        'geminiTextState=', 'geminiMediaState=', 'translationMemory='
    )
    cleaned = []
    for line in ctext.splitlines():
        if any(key in line for key in stale_keys):
            continue
        if 'report.append("maxSpeechRate=")' in line:
            cleaned.append(line.replace('maxSpeechRate=', 'preferredSpeechRate='))
            cleaned.append('        report.append("catchupCeiling=").append(adaptiveCatchupCeiling()).append(\'\\n\');')
            continue
        cleaned.append(line)
    controller.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
    print("patched: concise v2.11 diagnostics and truthful speech-rate labels")

    print("v2.11.0 pause-aware phrase/session integration complete")


if __name__ == "__main__":
    main()
