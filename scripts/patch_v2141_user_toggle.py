#!/usr/bin/env python3
"""v2.14.1: explicit VOT button presses always toggle, even during loading."""
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2141_user_toggle.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    text = vot.read_text(encoding="utf-8")

    old = '''    /**
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
'''
    if text.count(old) != 1:
        raise RuntimeError(f"loading-safe player toggle anchor count={text.count(old)}")

    new = '''    /**
     * Explicit user-button entry point. A real tap always wins over loading/autostart state.
     * Automatic lifecycle code must use its own idempotent enable path and must never masquerade
     * as a user button press.
     */
    public static void toggleTranslationFromPlayerButton() {
        Utils.verifyOnMainThread();
        final boolean next = app.spanishstudy.vot.SessionTogglePolicy.nextStateForUserPress(
                sessionEnabled, isLoading);
        SpanishStudyDiagnostics.record("SESSION", "user button requested "
                + (next ? "on" : "off") + " loading=" + isLoading);
        if (next != sessionEnabled) {
            toggleTranslation();
        } else {
            notifyStateChanged();
        }
    }
'''
    text = text.replace(old, new, 1)
    vot.write_text(text, encoding="utf-8")
    print("v2.14.1 explicit user VOT toggle restored")


if __name__ == "__main__":
    main()
