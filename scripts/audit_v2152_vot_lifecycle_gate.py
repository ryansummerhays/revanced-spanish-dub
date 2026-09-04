#!/usr/bin/env python3
from pathlib import Path
import sys


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2152_vot_lifecycle_gate.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    vot = (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")

    require(vot, "private static volatile boolean sessionEnabled", "cross-thread session visibility")
    require(vot, "private static boolean isVotRuntimeEnabled()", "runtime lifecycle predicate")
    require(vot, "return Settings.VOT_ENABLED.get() && sessionEnabled;", "global + session lifecycle contract")

    # OFF transition must actively terminate translation and future synthesis work.
    deactivate_start = vot.index("public static void deactivateTranslation()")
    deactivate_end = vot.index("\n    /** Stops any in-progress TTS", deactivate_start)
    deactivate = vot[deactivate_start:deactivate_end]
    for needle, label in (
        ("TranscriptTranslator.requestAbort();", "translator abort on VOT off"),
        ("TtsPrefetcher.clear();", "prefetch clear on VOT off"),
        ("segments = new ArrayList<>();", "partial transcript discard on VOT off"),
        ("VOT-LIFECYCLE", "lifecycle diagnostics on VOT off"),
    ):
        require(deactivate, needle, label)

    # Every private load path is gated before any background work starts.
    load_start = vot.index("private static void loadTranscript(String videoId)")
    load_end = vot.index("\n    /** Lazily creates the System TTS instance", load_start)
    load = vot[load_start:load_end]
    gate_pos = load.index("if (!isVotRuntimeEnabled())")
    background_pos = load.index("Utils.runOnBackgroundThread")
    if gate_pos > background_pos:
        raise RuntimeError("VOT runtime gate occurs after background transcript work starts")
    require(load, "return !isVotRuntimeEnabled()", "translator cancel supplier checks VOT session")
    require(load, "if (isVotRuntimeEnabled()", "progress/final publication checks VOT session")
    require(load, "restart active transcript load", "active-only restart diagnostic")
    require(load, "|| segments.isEmpty()", "clean restart after rapid off/on")

    reload_start = vot.index("public static void reloadTranscript()")
    reload_end = vot.index("\n    /**\n     * Registers a callback fired whenever toggle/load state changes.", reload_start)
    reload_section = vot[reload_start:reload_end]
    require(reload_section, "if (!isVotRuntimeEnabled())", "reload suppression while off")
    require(reload_section, "TranscriptTranslator.requestAbort();", "reload-off abort")
    require(reload_section, "reload suppressed while off", "reload-off diagnostic")

    require(controller, "Spanish Dub Study v2.15.2 diagnostics", "v2.15.2 diagnostic header")
    require(controller, "providerRuntimeTelemetry=v2.15.2", "v2.15.2 telemetry version")
    require(controller, "votRuntimeLifecycle=session-gated-no-provider-work-while-off", "lifecycle policy diagnostic")

    print("v2.15.2 VOT lifecycle audit passed")


if __name__ == "__main__":
    main()
