#!/usr/bin/env python3
"""Audit v2.32.11 Stage I: Spanish TTS audition mute with original-audio restore."""
from pathlib import Path
import sys


def need(text: str, token: str, label: str) -> None:
    if token not in text:
        raise RuntimeError(f"missing {label}: {token}")
    print("ok:", label)


def forbid(text: str, token: str, label: str) -> None:
    if token in text:
        raise RuntimeError(f"forbidden {label}: {token}")
    print("ok absent:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v23211_spanish_voice_toggle_stage_i.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"

    vot = (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    prefs = (study / "SpanishStudyPrefs.java").read_text(encoding="utf-8")
    sheet = (study / "SpanishStudySheet.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    subtitle = (study / "SpanishSubtitleOverlay.java").read_text(encoding="utf-8")
    player_volume = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    hook = (root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt").read_text(encoding="utf-8")

    need(controller, "Spanish Dub Study v2.32.11 Stage-I Spanish-voice-toggle diagnostics", "Stage-I header")
    need(controller, "spanishVoiceEnabled=", "Spanish voice state diagnostic")
    need(controller, "spanishVoiceMode=audition-mute-only-translation-subtitles-diarization-continue", "audition-mode diagnostic")
    need(controller, "effectiveSpanishVoiceVolumeForStudy", "effective generated-voice volume helper")
    need(controller, "effectiveOriginalAudioMultiplierForStudy", "effective original-audio helper")
    need(controller, "VoiceOverTranslationPatch.applySpanishVoiceStudySetting()", "live toggle bridge")

    need(prefs, 'SPANISH_VOICE_ENABLED = "spanish_voice_enabled"', "persistent Spanish voice preference")
    need(prefs, "spanishVoiceEnabled(Context c)", "Spanish voice preference getter")
    need(prefs, "setSpanishVoiceEnabled(Context c, boolean v)", "Spanish voice preference setter")

    need(sheet, '"Audio comparison"', "audio comparison settings section")
    need(sheet, '"Spanish voice"', "Spanish voice switch")
    need(sheet, "SpanishStudyController.setSpanishVoiceEnabled(activity, value)", "Spanish voice switch callback")
    need(sheet, "A/B/C/D speaker labels active", "speaker-validation UI explanation")

    need(vot, "applySpanishVoiceStudySetting()", "immediate audition apply hook")
    need(vot, "effectiveSpanishVoiceVolumeForStudy", "generated volume gating in Morphe playback")
    need(vot, "effectiveOriginalAudioMultiplierForStudy", "original-audio duck gating in Morphe playback")
    need(vot, "PlayerVolumePatch.clearDuckMultiplier();", "immediate original-audio restore")
    if vot.count("effectiveSpanishVoiceVolumeForStudy") < 3:
        raise RuntimeError("expected Spanish voice gating in normal/test volume plus live update")
    print("ok: generated Spanish volume gated at all required paths")
    if vot.count("effectiveOriginalAudioMultiplierForStudy") != 7:
        raise RuntimeError(f"expected 7 duck-gating sites, found {vot.count('effectiveOriginalAudioMultiplierForStudy')}")
    print("ok: all seven Morphe original-audio duck sites honor audition mode")
    forbid(vot,
           "PlayerVolumePatch.setDuckMultiplier(Settings.VOT_ORIGINAL_AUDIO_VOLUME.get() / 100.0f);",
           "ungated stock original-audio duck site")

    # Stage H speaker badge and Stage G clustering must remain intact.
    need(controller, "speakerPcmDiarizationStatus=diagnostic-live-committed-cluster-badge-no-voice-routing", "Stage-H speaker status retained")
    need(controller, "speakerFeatureClustering=online-fixed-centroid-stage-g-diagnostic-only", "Stage-G clustering retained")
    need(controller, "speakerFeatureAssignment=committed-cluster-live-subtitle-badge-stage-h", "Stage-H label assignment retained")
    need(subtitle, "getSpeakerClusterCommittedForStudy()", "Stage-H live committed badge retained")
    need(subtitle, "String.valueOf((char) ('A' + committedCluster))", "A/B/C/D badge retained")
    need(player_volume, "STUDY_SPEAKER_CLUSTER_NEW_DISTANCE = 0.255", "Stage-G threshold retained")
    need(player_volume, "STUDY_SPEAKER_CLUSTER_STABLE_RUN = 2", "Stage-G stabilization retained")

    # Sacred translation/caption invariants.
    need(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "1500-char batch ceiling unchanged")
    need(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "350-char first batch unchanged")
    need(fetcher, "private static List<TranscriptSegment> mergeIntoSentences", "stock sentence merger retained")
    need(translator,
         "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.",
         "numbered translation packet contract retained")
    need(hook, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "direct PCM callback retained")
    need(hook, "observeAudioTrackForStudy(Landroid/media/AudioTrack;)V", "AudioTrack metadata callback retained")

    print("v2.32.11 Stage-I audit passed")
    print("Runtime target: toggle Spanish voice OFF and hear unducked original English while subtitles and live A/B/C/D continue; toggle ON to restore Spanish immediately for Edge TTS.")


if __name__ == "__main__":
    main()
