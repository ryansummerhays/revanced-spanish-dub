#!/usr/bin/env python3
"""v2.33.35: persistent/provisional speaker badge + OpenRouter translation integrity.

Applies after v2.33.34. Intentionally leaves the accepted-PCM AudioTrack hook, video-master
projection, ERes2Net extraction cadence, and TTS/subtitle timing architecture untouched.
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


def req(path: Path, needle: str, label: str) -> None:
    if needle not in path.read_text(encoding="utf-8"):
        raise RuntimeError(f"{label}: missing {needle!r}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: patch_v23335_badge_translation_integrity.py <morphe-root> [repo-root]")
    root = Path(sys.argv[1]).resolve()
    live = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"
    for p in (live, controller, translator):
        if not p.is_file():
            raise RuntimeError(f"missing v2.33.34 source: {p}")

    # ------------------------------------------------------------------
    # Speaker display/identity: make uncertainty visible instead of blank.
    # ------------------------------------------------------------------
    rep(live,
        '''    private static final int MAX_PROTOTYPES = 3;\n''',
        '''    private static final int MAX_PROTOTYPES = 4;\n''',
        "allow one additional confirmed style prototype per human")

    rep(live,
        '''            // During an unresolved candidate span, showing the previous speaker would turn\n            // uncertainty into a false label. Prefer ? until the cluster resolves; promotion\n            // retroactively fills the candidate interval in the video-time timeline.\n            if (candidate != null && videoMs >= candidate.startVideoMs\n                    && videoMs <= candidate.endVideoMs + 400L) return "";\n''',
        '''            // v2.33.35 display policy: never make the speaker indicator disappear merely\n            // because the identity worker is still resolving a short excursion. If the unresolved\n            // cluster is parented to the current human, keep that human visible with a question mark.\n            // A genuinely unparented candidate is shown explicitly as unknown. This changes only\n            // presentation; it does not commit the candidate into the human timeline.\n            if (candidate != null && videoMs >= candidate.startVideoMs\n                    && videoMs <= candidate.endVideoMs + 700L) {\n                if (candidate.parentSpeaker >= 0 && candidate.parentSpeaker < profileCount) {\n                    return labelFor(candidate.parentSpeaker) + "?";\n                }\n                return "?";\n            }\n''',
        "keep unresolved speaker badge visible with explicit uncertainty")

    rep(live,
        '''                    return labelFor(TL_SPEAKER[i]);\n                }\n                if (videoMs > TL_END[i] + LIVE_HOLD_MS) break;\n''',
        '''                    return labelFor(TL_SPEAKER[i]) + "?";\n                }\n                if (videoMs > TL_END[i] + LIVE_HOLD_MS) break;\n''',
        "mark bounded live-lag hold as provisional")

    # v34 required 3 windows before a same-run excursion could bridge back to its parent.
    # The device trace showed short 1-2-window excursions, so allow 2-window bridge evidence,
    # while retaining the separate 3-repeat quarantine before learning a permanent prototype.
    rep(live,
        '''                || c.parentSpeechRunSerial != returnJob.speechRunSerial || c.count < 3) return;\n''',
        '''                || c.parentSpeechRunSerial != returnJob.speechRunSerial || c.count < 2) return;\n''',
        "allow two-window same-run style bridge-back")

    rep(live,
        '''            return "speakerLiveMode=eres2net-short-window-online-human-identity-v23334\\n"\n''',
        '''            return "speakerLiveMode=eres2net-short-window-online-human-identity-v23335\\n"\n''',
        "update live mode marker")

    rep(live,
        '''                    + "speakerLiveUnknownPolicy=unknown-before-false-human-split\\n"\n                    + "speakerLiveImpressionPolicy=same-run-style-excursion+three-bridge-quarantine-before-prototype\\n"\n''',
        '''                    + "speakerLiveUnknownPolicy=visible-provisional-parent-or-explicit-unknown-before-false-human-split\\n"\n                    + "speakerLiveBadgePolicy=confirmed-A-B;provisional-A?-B?;unassigned-?;never-blank-for-live-uncertainty\\n"\n                    + "speakerLiveStyleBridgeMinWindows=2\\n"\n                    + "speakerLiveMaxPrototypesPerHuman=4\\n"\n                    + "speakerLiveImpressionPolicy=same-run-style-excursion+three-bridge-quarantine-before-prototype\\n"\n''',
        "publish v35 visible-uncertainty policy")

    # ------------------------------------------------------------------
    # Translation integrity.
    # v2.30's strict parser pre-populates result[] with source placeholders. The v34 log proved
    # that matchedUnique=0/contiguous=0 could still escape as a full-sized result, which the caller
    # then stamped es-ES. Fail closed here so v34's existing retry-once/Google-batch recovery runs.
    # ------------------------------------------------------------------
    zero_anchor = '''        final int matchedFirst = contiguous;\n'''
    zero_fix = '''        final int matchedFirst = contiguous;\n\n        // v2.33.35 hard invariant: an empty/unparseable OpenRouter stream must never fall through\n        // as a full-sized list of source placeholders. Doing so makes applyBatch() stamp English\n        // source text with the Spanish target language and sends English to the Spanish TTS voice.\n        if (segmentSize > 0 && matchedFirst == 0) {\n            OpenRouterTelemetry.recordCardinalityMismatch(segmentSize, matched[0]);\n            SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.TRANSLATION,\n                    "OpenRouter zero-parsed-output failure expected=" + segmentSize\n                            + " unique=" + matched[0] + " rawChars=" + rawOutput.length());\n            throw new Exception("OpenRouter output alignment mismatch: zero parsed slots");\n        }\n'''
    rep(translator, zero_anchor, zero_fix, "fail closed on zero parsed OpenRouter slots")

    # v2.30 repairs a suspicious translated slot through Google. If that singleton repair fails
    # after earlier slots were already valid, preserve that valid contiguous prefix and let Morphe
    # requeue only the unresolved tail instead of throwing away the good work.
    old_guard = '''            if (fallback == null || fallback.size() != 1\n                    || DubLanguageGuard.reason(segments.get(i).text, fallback.get(0), targetLang) != null) {\n                throw new Exception("Language guard fallback failed at slot " + i);\n            }\n            result.set(i, fallback.get(0));\n'''
    new_guard = '''            if (fallback == null || fallback.size() != 1\n                    || DubLanguageGuard.reason(segments.get(i).text, fallback.get(0), targetLang) != null) {\n                if (i > 0) {\n                    SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.TRANSLATION,\n                            "OpenRouter language-guard preserve-prefix=" + i\n                                    + " unresolvedTail=" + (segmentSize - i));\n                    return new ArrayList<>(result.subList(0, i));\n                }\n                throw new Exception("Language guard fallback failed at slot " + i);\n            }\n            result.set(i, fallback.get(0));\n'''
    rep(translator, old_guard, new_guard,
        "preserve valid translation prefix on later language-guard fallback failure")

    # ------------------------------------------------------------------
    # Diagnostics/version identity only; no packetization or TTS timing changes.
    # ------------------------------------------------------------------
    rep(controller,
        'report.append("Spanish Dub Study v2.33.34 context-aware human/style identity diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.35 persistent speaker badge + translation integrity diagnostics\\n");',
        "update controller header")

    ctext = controller.read_text(encoding="utf-8")
    old_recovery = "translationCustomRecovery=stock-tail-requeue+google-singleton-language-repair"
    if old_recovery in ctext:
        ctext = ctext.replace(old_recovery,
            "translationCustomRecovery=aligned-prefix-preserve+zero-parse-retry-once+google-batch-fallback", 1)
        controller.write_text(ctext, encoding="utf-8")
        print("patched: update translation recovery architecture marker")

    req(live, "speakerLiveMode=eres2net-short-window-online-human-identity-v23335", "v35 live marker")
    req(live, "speakerLiveBadgePolicy=confirmed-A-B;provisional-A?-B?;unassigned-?;never-blank-for-live-uncertainty", "visible uncertainty marker")
    req(live, "speakerLiveStyleBridgeMinWindows=2", "two-window style bridge marker")
    req(live, "MAX_PROTOTYPES = 4", "four style prototypes")
    req(translator, "OpenRouter zero-parsed-output failure", "zero-parse failure marker")
    req(translator, "OpenRouter language-guard preserve-prefix=", "prefix preservation marker")
    req(controller, "v2.33.35 persistent speaker badge + translation integrity", "v35 controller marker")

    print("v2.33.35 speaker badge + translation integrity patch complete")
    print("PRESERVED: exact accepted PCM, verifier-safe int-only postwrite hook, videoMs master clock, ERes2Net timing")


if __name__ == "__main__":
    main()
