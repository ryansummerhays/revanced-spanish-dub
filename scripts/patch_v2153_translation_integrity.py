#!/usr/bin/env python3
"""v2.15.3: strip translation protocol metadata, prevent token truncation, and clarify speaker state."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def method_section(path: Path, start_marker: str, end_marker: str):
    text = path.read_text(encoding="utf-8")
    marker = text.index(start_marker)
    start = text.rfind("\n", 0, marker) + 1
    end = text.index(end_marker, marker)
    return text, start, end, text[start:end]


def replace_in_method(path: Path, start_marker: str, end_marker: str,
                      old: str, new: str, label: str, count: int = 1) -> None:
    text, start, end, section = method_section(path, start_marker, end_marker)
    found = section.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} method anchor(s), found {found}")
    section = section.replace(old, new, count)
    path.write_text(text[:start] + section + text[end:], encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2153_translation_integrity.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    translator = pkg / "TranscriptTranslator.java"
    vot = pkg / "VoiceOverTranslationPatch.java"
    controller = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    for path in (translator, vot, controller, sheet):
        if not path.is_file():
            raise RuntimeError(f"missing required source: {path}")

    # ---- Provider-output firewall ------------------------------------------------------------
    rep(translator,
        "import app.spanishstudy.vot.OpenRouterOutputGuard;\n",
        "import app.spanishstudy.vot.OpenRouterOutputGuard;\nimport app.spanishstudy.vot.DubTextSanitizer;\n",
        "import final dub text sanitizer")

    replace_in_method(
        translator,
        "private static void applyBatch(",
        "\n    @Nullable\n    private static Consumer<List<String>> streamCallback",
        '''            String translatedText = translated.get(j);\n            if (lang != null''',
        '''            String rawTranslatedText = translated.get(j);\n            String translatedText = DubTextSanitizer.cleanForSpeech(rawTranslatedText);\n            if (translatedText == null) {\n                SpanishStudyDiagnostics.record("TRANSLATION-SANITIZE", "drop final slot=" + (offset + j));\n                continue;\n            }\n            if (rawTranslatedText == null || !translatedText.equals(rawTranslatedText)) {\n                SpanishStudyDiagnostics.record("TRANSLATION-SANITIZE", "clean final slot=" + (offset + j));\n            }\n            if (lang != null''',
        "sanitize every final provider result before transcript publication")

    # Streamed OpenRouter updates bypass applyBatch(), so clean both callback loops independently.
    replace_in_method(
        translator,
        "private static Consumer<List<String>> streamCallback(",
        "\n    @Nullable\n    private static List<String> translateBatchSafe",
        '''                String translatedText = partial.get(j);\n                if (translatedText == null || translatedText.equals(batch.get(j).text)) continue;''',
        '''                String rawTranslatedText = partial.get(j);\n                String translatedText = DubTextSanitizer.cleanForSpeech(rawTranslatedText);\n                if (translatedText == null || translatedText.equals(batch.get(j).text)) continue;\n                if (!translatedText.equals(rawTranslatedText)) {\n                    SpanishStudyDiagnostics.record("TRANSLATION-SANITIZE", "clean stream slot=" + (offset + j));\n                }''',
        "sanitize streamed provenance update")
    replace_in_method(
        translator,
        "private static Consumer<List<String>> streamCallback(",
        "\n    @Nullable\n    private static List<String> translateBatchSafe",
        '''                String translatedText = partial.get(j);\n                TranscriptSegment orig = batch.get(j);\n                if (translatedText == null || translatedText.equals(orig.text)) continue;''',
        '''                String rawTranslatedText = partial.get(j);\n                String translatedText = DubTextSanitizer.cleanForSpeech(rawTranslatedText);\n                TranscriptSegment orig = batch.get(j);\n                if (translatedText == null || translatedText.equals(orig.text)) continue;\n                if (!translatedText.equals(rawTranslatedText)) {\n                    SpanishStudyDiagnostics.record("TRANSLATION-SANITIZE", "clean stream slot=" + (offset + j));\n                }''',
        "sanitize streamed transcript publication")

    # Quality diagnostics should show what can actually reach subtitles/TTS, not raw protocol text.
    text, start, end, section = method_section(
        translator,
        "private static void recordTranslationQuality(",
        "\n    private static")
    marker = "            TranslationQualityLog.record("
    if section.count(marker) != 1:
        raise RuntimeError("translation-quality sanitizer anchor missing")
    section = section.replace(marker,
        '''            target = DubTextSanitizer.cleanForSpeech(target);\n            TranslationQualityLog.record(''', 1)
    translator.write_text(text[:start] + section + text[end:], encoding="utf-8")
    print("patched: sanitize translation-quality trace")

    # ---- Stop self-inflicted finish_reason=length truncation ---------------------------------
    rep(translator,
        '''        JSONObject body = new JSONObject()\n                .put("model", model)''',
        '''        final int maxOutputTokens = RealtimeTranslationPlanner.openRouterMaxOutputTokens(\n                joined.length(), segments.size());\n        JSONObject body = new JSONObject()\n                .put("model", model)''',
        "calculate dynamic OpenRouter output budget")
    rep(translator,
        '''                .put("usage", new JSONObject().put("include", true))\n                .put("max_tokens", segments.size() * 30)''',
        '''                .put("usage", new JSONObject().put("include", true))\n                .put("max_tokens", maxOutputTokens)''',
        "replace 30-token-per-segment OpenRouter cap")
    rep(translator,
        '''        SpanishStudyDiagnostics.record("OPENROUTER-REQ", "start id=" + requestId\n                + " events=" + segments.size() + " contextChars=" + videoContext.length()\n                + " model=" + model);''',
        '''        SpanishStudyDiagnostics.record("OPENROUTER-REQ", "start id=" + requestId\n                + " events=" + segments.size() + " contextChars=" + videoContext.length()\n                + " maxTokens=" + maxOutputTokens + " model=" + model);''',
        "log OpenRouter output budget")
    rep(translator,
        '''                + " unique=" + uniqueMatched + " provider=" + routedProvider\n                + " cost=" + usageCostUsd);''',
        '''                + " unique=" + uniqueMatched + " provider=" + routedProvider\n                + " finish=" + finishReason + " maxTokens=" + maxOutputTokens\n                + " cost=" + usageCostUsd);''',
        "log finish reason per OpenRouter request")

    # An unterminated line on a length-limited stream is precisely the unsafe case seen in v2.15.2.
    # Do not publish the tail, and fail the subrequest closed so it is retried/recovered.
    replace_in_method(
        translator,
        "private static List<String> translateBatchOpenRouterSingle(",
        "\n    static void fetchOpenRouterModelCost",
        '''                if (lineBuffer.length() > 0) {''',
        '''                if (lineBuffer.length() > 0 && !"length".equalsIgnoreCase(finishReason)) {''',
        "suppress unterminated length-truncated OpenRouter tail")
    replace_in_method(
        translator,
        "private static List<String> translateBatchOpenRouterSingle(",
        "\n    static void fetchOpenRouterModelCost",
        '''        if (matchedFirst != segmentSize) {''',
        '''        if ("length".equalsIgnoreCase(finishReason)) {\n            SpanishStudyDiagnostics.record("OPENROUTER-PARSE", "reject length-truncated id=" + requestId\n                    + " matched=" + matchedFirst + "/" + segmentSize);\n            throw new Exception("OpenRouter output truncated at max token budget");\n        }\n\n        if (matchedFirst != segmentSize) {''',
        "reject length-truncated OpenRouter response")

    # ---- Last-resort TTS firewall -------------------------------------------------------------
    rep(vot,
        "import app.morphe.extension.youtube.shared.VideoState;\n",
        "import app.morphe.extension.youtube.shared.VideoState;\nimport app.spanishstudy.vot.DubTextSanitizer;\n",
        "import dub sanitizer into TTS dispatcher")
    replace_in_method(
        vot,
        "private static void speak(TranscriptSegment seg, int index)",
        "\n    private static void triggerNextSegmentCheck()",
        '''        Logger.printDebug(() -> "Speak: " + seg);\n        String lang = resolveTargetLang();''',
        '''        Logger.printDebug(() -> "Speak: " + seg);\n        final String speechText = DubTextSanitizer.cleanForSpeech(seg.text);\n        if (speechText == null || !speechText.equals(seg.text)) {\n            if (pendingSpeechIndex == index) pendingSpeechIndex = -1;\n            lastSpokenIndex = Math.max(lastSpokenIndex, index);\n            SpanishStudyController.onDubPlaybackSkipped(seg, index);\n            SpanishStudyDiagnostics.record("TTS-SANITIZE", speechText == null\n                    ? "blocked protocol-only text index=" + index\n                    : "blocked residual protocol metadata index=" + index);\n            triggerNextSegmentCheck();\n            return;\n        }\n        String lang = resolveTargetLang();''',
        "fail closed if protocol metadata reaches TTS")

    # ---- Speaker behavior must match the real backend ----------------------------------------
    replace_in_method(
        controller,
        "public static boolean speakerVoicesEnabled()",
        "\n    /** Called by the Edge TTS engine",
        '''    public static boolean speakerVoicesEnabled(){\n        android.content.Context context=Utils.getContext();\n        return context!=null&&SpanishStudyPrefs.speakerVoicesEnabled(context);\n    }''',
        '''    public static boolean speakerVoicesEnabled(){\n        // Local acoustic diarization is not implemented in this stable runtime yet. Never let an\n        // old/stale preference imply that alternate voices are confirmed speaker identities.\n        return false;\n    }''',
        "hard-disable per-speaker voice routing until diarization backend exists")

    stext = sheet.read_text(encoding="utf-8")
    stext = stext.replace("Speaker recognition (future)", "Speaker recognition — unavailable")
    stext = stext.replace("Per-speaker Spanish voices (future)", "Per-speaker voices — unavailable")
    stext = stext.replace("Disabled until a lightweight local source-audio pipeline is proven",
                          "Unavailable in this build: no local source-audio speaker backend is active")
    stext = stext.replace("Disabled until local speaker recognition is available",
                          "Unavailable until real A/B/C speaker profiles can be created from source audio")
    sheet.write_text(stext, encoding="utf-8")
    print("patched: make speaker controls accurately describe unavailable backend")

    # ---- Diagnostics -------------------------------------------------------------------------
    ctext = controller.read_text(encoding="utf-8")
    ctext = ctext.replace("Spanish Dub Study v2.15.2 diagnostics", "Spanish Dub Study v2.15.3 diagnostics")
    ctext = ctext.replace("providerRuntimeTelemetry=v2.15.2", "providerRuntimeTelemetry=v2.15.3")
    speaker_anchor = '        report.append("speakerBackend=disabled-pending-local-audio-pipeline\\n");\n'
    if ctext.count(speaker_anchor) != 1:
        raise RuntimeError("speaker diagnostic anchor missing")
    ctext = ctext.replace(speaker_anchor, speaker_anchor
        + '        report.append("speakerProfiles=").append(SpeakerAssignmentStore.profileSummary()).append(\'\\n\');\n'
        + '        report.append("speakerVoiceRouting=disabled-no-local-audio-backend\\n");\n', 1)
    lifecycle_anchor = '        report.append("votRuntimeLifecycle=session-gated-no-provider-work-while-off\\n");\n'
    if ctext.count(lifecycle_anchor) != 1:
        raise RuntimeError("lifecycle diagnostic anchor missing")
    ctext = ctext.replace(lifecycle_anchor, lifecycle_anchor
        + '        report.append("translationOutputSanitizer=batch-enum+slot-duration+timestamp-firewall\\n");\n'
        + '        report.append("openRouterOutputBudget=dynamic-192-640-tokens\\n");\n', 1)
    controller.write_text(ctext, encoding="utf-8")

    print("v2.15.3 translation integrity integration complete")


if __name__ == "__main__":
    main()
