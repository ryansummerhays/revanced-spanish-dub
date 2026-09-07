#!/usr/bin/env python3
"""v2.32.11 Stage I: user-toggleable Spanish TTS audition mute.

This stage exists to let the user validate the original English speakers against the live
Stage-H A/B/C/D badge. Turning Spanish voice off keeps translation, subtitles, PCM capture,
VAD/features/clustering, and the live speaker badge running, while silencing generated Spanish
speech and removing Morphe's original-audio ducking.

No segmentation, OpenRouter packetization, subtitle pagination/timing, PCM analysis, or speaker
clustering logic is changed.
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


def rep_all(path: Path, old: str, new: str, label: str, expected: int) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != expected:
        raise RuntimeError(f"{label}: expected {expected} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("patched:", label, "count=", found)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v23211_spanish_voice_toggle_stage_i.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"

    vot = pkg / "VoiceOverTranslationPatch.java"
    prefs = study / "SpanishStudyPrefs.java"
    sheet = study / "SpanishStudySheet.java"
    controller = study / "SpanishStudyController.java"
    for path in (vot, prefs, sheet, controller):
        if not path.is_file():
            raise RuntimeError(f"missing Stage-H source: {path}")

    # Persistent user preference. Default true preserves all existing behavior.
    rep(
        prefs,
        '    private static final String SPEAKER_EXPERIMENT = "speaker_local_experiment_v228";\n',
        '    private static final String SPEAKER_EXPERIMENT = "speaker_local_experiment_v228";\n'
        '    private static final String SPANISH_VOICE_ENABLED = "spanish_voice_enabled";\n',
        "add Spanish voice preference key",
    )
    rep(
        prefs,
        '    static boolean speakerExperiment(Context c) { return prefs(c).getBoolean(SPEAKER_EXPERIMENT, true); }\n'
        '    static void setSpeakerExperiment(Context c, boolean v) { putBoolean(c, SPEAKER_EXPERIMENT, v); }\n',
        '    static boolean speakerExperiment(Context c) { return prefs(c).getBoolean(SPEAKER_EXPERIMENT, true); }\n'
        '    static void setSpeakerExperiment(Context c, boolean v) { putBoolean(c, SPEAKER_EXPERIMENT, v); }\n'
        '    static boolean spanishVoiceEnabled(Context c) { return prefs(c).getBoolean(SPANISH_VOICE_ENABLED, true); }\n'
        '    static void setSpanishVoiceEnabled(Context c, boolean v) { putBoolean(c, SPANISH_VOICE_ENABLED, v); }\n',
        "add Spanish voice preference accessors",
    )

    # Put the audition control at the top of the custom sheet so it is quick to reach while
    # visually comparing the real English speaker against the live A/B/C/D badge.
    rep(
        sheet,
        '        content.addView(section(activity, "Bilingual subtitles", secondary));\n',
        '        content.addView(section(activity, "Audio comparison", secondary));\n'
        '        content.addView(switchRow(activity, fg, "Spanish voice",\n'
        '                "Turn off generated Spanish speech while keeping the original English audio, subtitles, translation, and A/B/C/D speaker labels active.",\n'
        '                SpanishStudyPrefs.spanishVoiceEnabled(activity),\n'
        '                value -> SpanishStudyController.setSpanishVoiceEnabled(activity, value)));\n\n'
        '        content.addView(section(activity, "Bilingual subtitles", secondary));\n',
        "add Spanish voice audition switch",
    )

    # Controller is the narrow bridge between the study preference and Morphe playback. These
    # helpers are public because VoiceOverTranslationPatch lives in Morphe's package.
    controller_helpers = r'''
    /** True unless the user explicitly mutes generated Spanish speech for speaker validation. */
    public static boolean isSpanishVoiceEnabledForStudy() {
        Activity activity = Utils.getActivity();
        return activity == null || SpanishStudyPrefs.spanishVoiceEnabled(activity);
    }

    /** Effective generated-speech volume without changing the user's normal Morphe volume setting. */
    public static float effectiveSpanishVoiceVolumeForStudy(float configuredVolume) {
        if (!isSpanishVoiceEnabledForStudy()) return 0.0f;
        return Math.max(0.0f, Math.min(1.0f, configuredVolume));
    }

    /** Effective original-audio multiplier. Voice-off means no ducking so English stays audible. */
    public static float effectiveOriginalAudioMultiplierForStudy(float configuredMultiplier) {
        if (!isSpanishVoiceEnabledForStudy()) return 1.0f;
        return Math.max(0.0f, Math.min(1.0f, configuredMultiplier));
    }

    static void setSpanishVoiceEnabled(Activity activity, boolean enabled) {
        if (activity == null) return;
        SpanishStudyPrefs.setSpanishVoiceEnabled(activity, enabled);
        VoiceOverTranslationPatch.applySpanishVoiceStudySetting();
        SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.TTS,
                "Spanish voice audition enabled=" + enabled
                        + " translation/subtitles/speaker-analysis=unchanged");
    }

'''
    rep(
        controller,
        '    public static void showTools(Activity activity) {\n',
        controller_helpers + '    public static void showTools(Activity activity) {\n',
        "add Spanish voice playback bridge",
    )
    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.10 Stage-H live-cluster-label diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.11 Stage-I Spanish-voice-toggle diagnostics\\n");',
        "update Stage-I diagnostics header",
    )
    rep(
        controller,
        '        report.append("session=").append(VoiceOverTranslationPatch.isSessionEnabled()).append(\'\\n\');\n',
        '        report.append("session=").append(VoiceOverTranslationPatch.isSessionEnabled()).append(\'\\n\');\n'
        '        report.append("spanishVoiceEnabled=").append(isSpanishVoiceEnabledForStudy()).append(\'\\n\');\n'
        '        report.append("spanishVoiceMode=audition-mute-only-translation-subtitles-diarization-continue\\n");\n',
        "publish Spanish voice audition state",
    )

    # Silence all generated speech (normal segments and Morphe's preview path) when the audition
    # switch is off. This keeps Edge playback running silently, which intentionally preserves the
    # same TTS media clock used by the subtitle layer while the user listens to English.
    rep_all(
        vot,
        'final float volume = Settings.VOT_TRANSLATION_VOLUME.get() / 100.0f;',
        'final float volume = SpanishStudyController.effectiveSpanishVoiceVolumeForStudy(\n'
        '                Settings.VOT_TRANSLATION_VOLUME.get() / 100.0f);',
        "gate generated Spanish playback volume",
        expected=2,
    )

    # Every stock ducking site must use the same audition policy. A multiplier of 1.0 leaves the
    # original YouTube audio untouched while Spanish is muted.
    rep_all(
        vot,
        'PlayerVolumePatch.setDuckMultiplier(Settings.VOT_ORIGINAL_AUDIO_VOLUME.get() / 100.0f);',
        'PlayerVolumePatch.setDuckMultiplier(\n'
        '                    SpanishStudyController.effectiveOriginalAudioMultiplierForStudy(\n'
        '                            Settings.VOT_ORIGINAL_AUDIO_VOLUME.get() / 100.0f));',
        "disable original-audio ducking while Spanish voice is off",
        expected=7,
    )

    rep(
        vot,
        '        ttsEngine.setVolume(Settings.VOT_TRANSLATION_VOLUME.get() / 100.0f);\n',
        '        ttsEngine.setVolume(SpanishStudyController.effectiveSpanishVoiceVolumeForStudy(\n'
        '                Settings.VOT_TRANSLATION_VOLUME.get() / 100.0f));\n',
        "make live Edge volume updates honor Spanish voice toggle",
    )

    # Apply a toggle immediately. Edge can be muted/unmuted in-place. Android System TTS has no
    # reliable in-flight volume setter, so when muting we stop only that active System utterance;
    # future System utterances use the zero-volume parameter until re-enabled.
    apply_helper = r'''
    /** Applies the Spanish-study audition mute without disabling translation or TTS scheduling. */
    public static void applySpanishVoiceStudySetting() {
        Utils.verifyOnMainThread();
        updatePlaybackVolume();
        if (SpanishStudyController.isSpanishVoiceEnabledForStudy()) {
            updateOriginalAudioMultiplier();
        } else {
            PlayerVolumePatch.clearDuckMultiplier();
            if (tts != null && tts.isSpeaking()) tts.stop();
        }
    }

'''
    rep(
        vot,
        '    /** Re-applies the ducking multiplier so a Settings change takes effect immediately. */\n',
        apply_helper + '    /** Re-applies the ducking multiplier so a Settings change takes effect immediately. */\n',
        "add immediate Spanish voice audition apply hook",
    )

    print("v2.32.11 Stage-I Spanish voice toggle patch complete")
    print("UNCHANGED: mergeIntoSentences, 1500/350 OpenRouter packets, translation requests, subtitle pagination/timing, direct PCM capture, VAD/features, Stage-G clustering, Stage-H A/B/C/D badge")
    print("ADDED: Spanish voice switch; off => generated speech volume 0 + original audio unducked, while translation/subtitles/diarization keep running")


if __name__ == "__main__":
    main()
