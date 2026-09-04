#!/usr/bin/env python3
"""v2.15.2: hard lifecycle gate so VOT network/translation work exists only while VOT is active."""
from pathlib import Path
import sys


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def replace_in_method(path: Path, method_name: str, end_marker: str, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.index(method_name)
    end = text.index(end_marker, start)
    section = text[start:end]
    count = section.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one method-local anchor, found {count}")
    section = section.replace(old, new, 1)
    path.write_text(text[:start] + section + text[end:], encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2152_vot_lifecycle_gate.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    vot = pkg / "VoiceOverTranslationPatch.java"
    controller = study / "SpanishStudyController.java"
    for path in (vot, controller):
        if not path.is_file():
            raise RuntimeError(f"missing required source: {path}")

    # sessionEnabled is read by the background transcript worker's cancel check.
    replace_once(
        vot,
        "    private static boolean sessionEnabled = Settings.VOT_SESSION_ENABLED.get();\n",
        "    private static volatile boolean sessionEnabled = Settings.VOT_SESSION_ENABLED.get();\n",
        "make VOT session state visible to background workers",
    )

    # One authoritative lifecycle predicate for every network/translation entry point.
    replace_once(
        vot,
        '''    /** @return Per-session enabled flag (toggleable via the player button) - not the global setting. */\n    public static boolean isSessionEnabled() {\n        return sessionEnabled;\n    }\n''',
        '''    /** @return Per-session enabled flag (toggleable via the player button) - not the global setting. */\n    public static boolean isSessionEnabled() {\n        return sessionEnabled;\n    }\n\n    /** True only while VOT is globally enabled and the user-facing VOT session is active. */\n    private static boolean isVotRuntimeEnabled() {\n        return Settings.VOT_ENABLED.get() && sessionEnabled;\n    }\n''',
        "add authoritative VOT runtime lifecycle predicate",
    )

    # OFF means OFF: abort translation, stop TTS, kill future prefetch work, and discard any
    # partially translated transcript so re-enabling always starts a clean active-session load.
    replace_in_method(
        vot,
        "public static void deactivateTranslation()",
        "\n    /** Stops any in-progress TTS without changing session state.",
        '''        sessionEnabled = false;\n        Settings.VOT_SESSION_ENABLED.save(false);\n        stopTts();\n        lastSpokenIndex = -1;\n        notifyStateChanged();''',
        '''        sessionEnabled = false;\n        Settings.VOT_SESSION_ENABLED.save(false);\n        TranscriptTranslator.requestAbort();\n        stopTts();\n        TtsPrefetcher.clear();\n        segments = new ArrayList<>();\n        lastSpokenIndex = -1;\n        SpanishStudyDiagnostics.record("VOT-LIFECYCLE", "off abort-translation clear-prefetch");\n        notifyStateChanged();''',
        "abort all background VOT work when session turns off",
    )

    # Settings/provider changes can call reloadTranscript even while VOT is off. Make that path
    # a no-network cleanup operation until the user explicitly turns VOT back on.
    replace_in_method(
        vot,
        "public static void reloadTranscript()",
        "\n    /**\n     * Registers a callback fired whenever toggle/load state changes.",
        '''        Utils.verifyOnMainThread();\n        if (currentVideoId.isEmpty()) return;\n        stopTts();''',
        '''        Utils.verifyOnMainThread();\n        if (currentVideoId.isEmpty()) return;\n        if (!isVotRuntimeEnabled()) {\n            TranscriptTranslator.requestAbort();\n            TtsPrefetcher.clear();\n            segments = new ArrayList<>();\n            lastSpokenIndex = -1;\n            SpanishStudyDiagnostics.record("VOT-LIFECYCLE", "reload suppressed while off");\n            return;\n        }\n        stopTts();''',
        "suppress transcript/provider reload while VOT is off",
    )

    # The private loader is the last-resort gate: no caller can create network activity while OFF.
    replace_in_method(
        vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''        Logger.printDebug(() -> "loadTranscript: " + videoId);\n        Utils.verifyOnMainThread();\n        if (isLoading) return;''',
        '''        Logger.printDebug(() -> "loadTranscript: " + videoId);\n        Utils.verifyOnMainThread();\n        if (!isVotRuntimeEnabled()) {\n            SpanishStudyDiagnostics.record("VOT-LIFECYCLE", "load suppressed while off video=" + videoId);\n            return;\n        }\n        if (!videoId.equals(currentVideoId)) {\n            SpanishStudyDiagnostics.record("VOT-LIFECYCLE", "load suppressed stale-video=" + videoId);\n            return;\n        }\n        if (isLoading) return;''',
        "hard-gate transcript loader on active VOT session",
    )

    # Progressive translation callbacks must not repopulate segments after the user turned VOT off.
    replace_in_method(
        vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                            if (videoId.equals(currentVideoId) && loadLang.equals(resolveTargetLang())) {''',
        '''                            if (isVotRuntimeEnabled()\n                                    && videoId.equals(currentVideoId)\n                                    && loadLang.equals(resolveTargetLang())) {''',
        "drop progressive translation callbacks after VOT turns off",
    )

    # TranscriptTranslator checks this supplier between batches/retries. Include the session edge
    # so OpenRouter/Google/MyMemory stops promptly rather than merely hiding its results.
    replace_in_method(
        vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                            return !videoId.equals(currentVideoId)\n                                    || VideoState.getCurrent() == VideoState.ENDED;''',
        '''                            return !isVotRuntimeEnabled()\n                                    || !videoId.equals(currentVideoId)\n                                    || VideoState.getCurrent() == VideoState.ENDED;''',
        "cancel translator worker when VOT session turns off",
    )

    # Do not publish a completed fetch after OFF was pressed while a request was in flight.
    replace_in_method(
        vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                    if (videoId.equals(currentVideoId) && loadLang.equals(resolveTargetLang())) {''',
        '''                    if (isVotRuntimeEnabled()\n                            && videoId.equals(currentVideoId)\n                            && loadLang.equals(resolveTargetLang())) {''',
        "drop final transcript publication after VOT turns off",
    )

    # The previous finally block could restart translation after a provider/language change even
    # with sessionEnabled=false. Only restart while active. Also restart a clean load when the user
    # toggled OFF then ON while the old request was unwinding.
    replace_in_method(
        vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                    if (!currentVideoId.isEmpty() && Settings.VOT_ENABLED.get()\n                            && (!currentVideoId.equals(videoId)\n                            || !loadLang.equals(resolveTargetLang())\n                            || !loadService.equals(Settings.VOT_TRANSLATION_SERVICE.get()))) {\n                        loadTranscript(currentVideoId);\n                    }''',
        '''                    if (isVotRuntimeEnabled() && !currentVideoId.isEmpty()\n                            && (!currentVideoId.equals(videoId)\n                            || !loadLang.equals(resolveTargetLang())\n                            || !loadService.equals(Settings.VOT_TRANSLATION_SERVICE.get())\n                            || segments.isEmpty())) {\n                        SpanishStudyDiagnostics.record("VOT-LIFECYCLE", "restart active transcript load");\n                        loadTranscript(currentVideoId);\n                    }''',
        "prevent background translator restart while VOT is off",
    )

    # Make the lifecycle contract visible in copied diagnostics.
    ctext = controller.read_text(encoding="utf-8")
    ctext = ctext.replace("Spanish Dub Study v2.15.1 diagnostics", "Spanish Dub Study v2.15.2 diagnostics")
    ctext = ctext.replace("providerRuntimeTelemetry=v2.15.1", "providerRuntimeTelemetry=v2.15.2")
    anchor = '        report.append("providerRecovery=retry-openrouter+single-google-fallback+google-429-circuit\\n");\n'
    if ctext.count(anchor) != 1:
        raise RuntimeError("diagnostic providerRecovery anchor missing")
    ctext = ctext.replace(anchor, anchor + '        report.append("votRuntimeLifecycle=session-gated-no-provider-work-while-off\\n");\n', 1)
    controller.write_text(ctext, encoding="utf-8")

    print("v2.15.2 VOT lifecycle gate integration complete")


if __name__ == "__main__":
    main()
