#!/usr/bin/env python3
"""Add conservative live source-expression transfer to the Edge-TTS path.

The original YouTube AudioTrack is already captured by Morphe's volume hook. We attach Android's
Visualizer to that SAME playback session, then gently apply only trustworthy relative pitch/energy
movement to the Spanish MediaPlayer. This is intentionally separate from speaker identity: pitch or
volume changes can never select another voice.
"""
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
        raise SystemExit("usage: patch_source_expression.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    player_volume = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    tts = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TtsEngine.java"
    vot_patch = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/voiceovertranslation/VoiceOverTranslationPatch.kt"

    for path in (player_volume, tts, vot_patch):
        if not path.is_file():
            raise RuntimeError(f"Required source missing: {path}")

    # ---- Feed the already-captured YouTube AudioTrack into the playback Visualizer ------------
    replace_once(
        player_volume,
        "import app.morphe.extension.shared.Utils;\n",
        "import app.morphe.extension.shared.Utils;\nimport app.spanishstudy.vot.SourceExpressionMonitor;\n",
        "PlayerVolumePatch source-expression import",
    )
    replace_once(
        player_volume,
        '''        lastAudioTrackRef.set(track);\n        applyMultiplier();''',
        '''        lastAudioTrackRef.set(track);\n        SourceExpressionMonitor.onAudioTrack(track);\n        applyMultiplier();''',
        "publish YouTube AudioTrack to expression monitor",
    )
    replace_once(
        player_volume,
        '''    /**\n     * Sets the ducking multiplier (0..1). Called from the main thread.\n     */''',
        '''    /** Current YouTube playback AudioTrack for the opt-in Spanish study expression monitor. */\n    public static AudioTrack getAudioTrackForStudy() {\n        return lastAudioTrackRef.get();\n    }\n\n    /**\n     * Sets the ducking multiplier (0..1). Called from the main thread.\n     */''',
        "expose active YouTube AudioTrack to study monitor",
    )

    # ---- Add RECORD_AUDIO only because Android Visualizer requires it for playback sessions ----
    replace_once(
        vot_patch,
        "import app.morphe.util.copyResources\n",
        "import app.morphe.util.copyResources\nimport app.morphe.util.getNode\nimport org.w3c.dom.Element\n",
        "voice-over resource patch manifest imports",
    )
    replace_once(
        vot_patch,
        '''    execute {\n        copyResources(''',
        '''    execute {\n        // Android's Visualizer API requires RECORD_AUDIO even when attached to this app's own\n        // playback AudioTrack. Add it only if YouTube does not already declare it. The runtime\n        // request is still opt-in and happens only when source-expression matching is enabled.\n        document("AndroidManifest.xml").use { document ->\n            val manifest = document.getNode("manifest") as Element\n            val permissions = manifest.getElementsByTagName("uses-permission")\n            var declared = false\n            for (i in 0 until permissions.length) {\n                val item = permissions.item(i) as? Element ?: continue\n                if (item.getAttribute("android:name") == "android.permission.RECORD_AUDIO") {\n                    declared = true\n                    break\n                }\n            }\n            if (!declared) {\n                val permission = document.createElement("uses-permission")\n                permission.setAttribute("android:name", "android.permission.RECORD_AUDIO")\n                manifest.appendChild(permission)\n            }\n        }\n\n        copyResources(''',
        "declare Visualizer permission when absent",
    )

    # ---- Edge MediaPlayer: keep sync speed and expression pitch as independent controls --------
    replace_once(
        tts,
        "import app.spanishstudy.vot.SpanishStudyController;\n",
        "import app.spanishstudy.vot.SpanishStudyController;\nimport app.spanishstudy.vot.SourceExpressionMonitor;\n",
        "TtsEngine source-expression import",
    )
    replace_once(
        tts,
        '''    /** Tracks the active synthesis/playback session to prevent overlapping segments. */\n    private long playbackId;''',
        '''    /** Tracks the active synthesis/playback session to prevent overlapping segments. */\n    private long playbackId;\n\n    // Source-expression transfer is independent of timeline fitting. currentBasePlaybackRate is\n    // still entirely controlled by the existing sync logic; the live monitor only adds a tightly\n    // bounded pitch multiplier and a very small volume multiplier on top.\n    private static final long EXPRESSION_TICK_MS = 80L;\n    private float currentBasePlaybackRate = 1.0f;\n    private float currentBaseVolume = 1.0f;\n    private float lastExpressionPitch = 1.0f;\n    private float lastExpressionVolume = 1.0f;\n    private boolean expressionTickScheduled;''',
        "add independent live expression playback state",
    )

    replace_once(
        tts,
        '''        Utils.runOnBackgroundThread(() -> {\n            try {\n                // playMp3 blocks until completion or error.''',
        '''        currentBasePlaybackRate = Math.max(0.1f, rate);\n        currentBaseVolume = Math.max(0f, Math.min(1f, volume));\n        lastExpressionPitch = 1.0f;\n        lastExpressionVolume = 1.0f;\n        scheduleExpressionTick();\n\n        Utils.runOnBackgroundThread(() -> {\n            try {\n                // playMp3 blocks until completion or error.''',
        "initialize expression state for each Edge playback",
    )

    replace_once(
        tts,
        '''    /** Updates the active playback volume. No-op if there is no active player. */\n    void setVolume(float volume) {\n        Utils.verifyOnMainThread();\n        if (currentPlayer == null) return;\n        try {\n            currentPlayer.setVolume(volume, volume);\n        } catch (Exception ex) {\n            VoiceOverTranslationPatch.logError(() -> "MediaPlayer setVolume failed", ex);\n        }\n    }''',
        '''    /** Updates the active playback volume without discarding source-expression gain. */\n    void setVolume(float volume) {\n        Utils.verifyOnMainThread();\n        currentBaseVolume = Math.max(0f, Math.min(1f, volume));\n        applyLiveExpression(true);\n    }''',
        "preserve expression when base TTS volume changes",
    )

    replace_once(
        tts,
        '''    /** Updates the active MediaPlayer's rate in place. No-op if there is no active player. */\n    void setPlaybackRate(float rate) {\n        Utils.verifyOnMainThread();\n        if (currentPlayer == null) return;\n        try {\n            currentPlayer.setPlaybackParams(new PlaybackParams().setSpeed(rate));\n        } catch (Exception ex) {\n            VoiceOverTranslationPatch.logError(() -> "MediaPlayer setPlaybackRate failed", ex);\n        }\n    }''',
        '''    /** Updates sync speed without flattening the independently tracked source pitch. */\n    void setPlaybackRate(float rate) {\n        Utils.verifyOnMainThread();\n        currentBasePlaybackRate = Math.max(0.1f, rate);\n        applyLiveExpression(true);\n    }''',
        "keep live pitch independent of speech/video speed changes",
    )

    expression_helpers = r'''
    /**
     * Applies only small, confidence-gated expression movement to the already selected Spanish
     * voice. If the monitor is unavailable or uncertain its getters return 1.0, making this exactly
     * the ordinary Morphe playback path.
     */
    private void applyLiveExpression(boolean force) {
        Utils.verifyOnMainThread();
        MediaPlayer player = currentPlayer;
        if (player == null) return;

        final float pitch = SourceExpressionMonitor.pitchMultiplier();
        final float expressionVolume = SourceExpressionMonitor.volumeMultiplier();
        if (force || Math.abs(pitch - lastExpressionPitch) >= 0.004f) {
            try {
                player.setPlaybackParams(new PlaybackParams()
                        .setSpeed(currentBasePlaybackRate)
                        .setPitch(pitch));
                lastExpressionPitch = pitch;
            } catch (Exception ex) {
                Logger.printDebug(() -> "Source-expression pitch update failed", ex);
            }
        }

        if (force || Math.abs(expressionVolume - lastExpressionVolume) >= 0.008f) {
            try {
                float effectiveVolume = Math.max(0f,
                        Math.min(1f, currentBaseVolume * expressionVolume));
                player.setVolume(effectiveVolume, effectiveVolume);
                lastExpressionVolume = expressionVolume;
            } catch (Exception ex) {
                Logger.printDebug(() -> "Source-expression volume update failed", ex);
            }
        }
    }

    private void scheduleExpressionTick() {
        Utils.verifyOnMainThread();
        if (expressionTickScheduled) return;
        expressionTickScheduled = true;
        Utils.runOnMainThreadDelayed(this::expressionTick, EXPRESSION_TICK_MS);
    }

    private void expressionTick() {
        Utils.verifyOnMainThread();
        expressionTickScheduled = false;
        if (stopped || !speaking) return;

        // Run one neutralizing tick even after the setting is turned off, then stop scheduling.
        applyLiveExpression(false);
        if (SourceExpressionMonitor.isRequestedEnabled()) scheduleExpressionTick();
    }

'''
    replace_once(
        tts,
        "    /** Stops any in-progress synthesis or playback immediately. */\n",
        expression_helpers + "    /** Stops any in-progress synthesis or playback immediately. */\n",
        "add confidence-gated live expression playback loop",
    )

    print("Conservative source-expression transfer integration complete")


if __name__ == "__main__":
    main()
