#!/usr/bin/env python3
"""Make an enabled VoT session load on every video and expose the real player bounds."""
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched: {label}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_autostart_session.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    button = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/videoplayer/VoiceOverTranslationButton.java"
    for path in (vot, button):
        if not path.is_file():
            raise RuntimeError(f"Required source missing: {path}")

    replace_once(
        vot,
        '''            }\n            return kotlin.Unit.INSTANCE;\n        });\n\n        VideoState.getOnChange().addObserver(state -> {''',
        '''            }\n\n            // newVideoLoaded can fire while YouTube is still using INLINE_MINIMAL. Upstream skips\n            // transcript loading there; retry automatically as soon as this same video enters a\n            // real watch player so an enabled-looking button can never mean "nothing loaded".\n            if (Settings.VOT_ENABLED.get() && sessionEnabled\n                    && !currentVideoId.isEmpty() && segments.isEmpty() && !isLoading\n                    && (playerType.isMaximizedOrFullscreen()\n                        || playerType == PlayerType.WATCH_WHILE_MINIMIZED\n                        || playerType == PlayerType.WATCH_WHILE_PICTURE_IN_PICTURE\n                        || playerType == PlayerType.WATCH_WHILE_SLIDING_MINIMIZED_MAXIMIZED)) {\n                TtsPrefetcher.updateVideo(currentVideoId, segments);\n                loadTranscript(currentVideoId);\n            }\n            return kotlin.Unit.INSTANCE;\n        });\n\n        VideoState.getOnChange().addObserver(state -> {''',
        "retry transcript load when active player appears",
    )

    replace_once(
        button,
        "import app.morphe.extension.youtube.settings.Settings;\n",
        "import app.morphe.extension.youtube.settings.Settings;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
        "player button study import",
    )

    replace_once(
        button,
        '''            if (LegacyPlayerControlsPatch.RESTORE_OLD_PLAYER_BUTTONS || !Settings.VOT_ENABLED.get()) return;\n\n            VoiceOverTranslationPatch.addOnTranslationStateChangeCallback(''',
        '''            if (LegacyPlayerControlsPatch.RESTORE_OLD_PLAYER_BUTTONS || !Settings.VOT_ENABLED.get()) return;\n            SpanishStudyController.onPlayerControlsView(controlsView);\n\n            VoiceOverTranslationPatch.addOnTranslationStateChangeCallback(''',
        "capture modern player controls bounds",
    )

    replace_once(
        button,
        '''            if (!LegacyPlayerControlsPatch.RESTORE_OLD_PLAYER_BUTTONS) return;\n\n            VoiceOverTranslationPatch.addOnTranslationStateChangeCallback(''',
        '''            if (!LegacyPlayerControlsPatch.RESTORE_OLD_PLAYER_BUTTONS) return;\n            SpanishStudyController.onPlayerControlsView(controlsView);\n\n            VoiceOverTranslationPatch.addOnTranslationStateChangeCallback(''',
        "capture legacy player controls bounds",
    )

    # Make the icon distinguish OFF, enabled-but-loading/not-ready, and actually active.
    replace_once(
        button,
        '''            final int alpha = VoiceOverTranslationPatch.isSessionEnabled() ? 255 : 128;''',
        '''            final int alpha = VoiceOverTranslationPatch.isTranslationActive()\n                    ? 255\n                    : VoiceOverTranslationPatch.isSessionEnabled() ? 190 : 128;''',
        "show loading versus active button state",
    )

    print("VoT per-video autostart/player-bounds integration complete")


if __name__ == "__main__":
    main()
