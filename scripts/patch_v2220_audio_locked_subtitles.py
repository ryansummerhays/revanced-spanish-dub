#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def insert_before(path: Path, anchor: str, insertion: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(anchor)
    if found != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {found} in {path}")
    path.write_text(text.replace(anchor, insertion + anchor, 1), encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2220_audio_locked_subtitles.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"

    controller = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    speaker_store = study / "SpeakerAssignmentStore.java"
    sidecar = study / "GeminiSpeakerDiarizationSidecar.java"
    vot = pkg / "VoiceOverTranslationPatch.java"
    tts = pkg / "TtsEngine.java"
    overlay = study / "SpanishSubtitleOverlay.java"

    for path in (controller, sheet, speaker_store, sidecar, vot, tts, overlay):
        if not path.is_file():
            raise RuntimeError(f"missing v2.21 generated source: {path}")

    # --------------------------------------------------------------------------------------
    # Replace the v2.21 display clock with an audio-locked bilingual overlay.
    # --------------------------------------------------------------------------------------
    shutil.copy2(repo / "overlay/v222/app/spanishstudy/vot/SubtitleAudioSyncPolicy.java",
                 study / "SubtitleAudioSyncPolicy.java")
    shutil.copy2(repo / "overlay/v222/app/spanishstudy/vot/SpeakerCostPolicy.java",
                 study / "SpeakerCostPolicy.java")
    shutil.copy2(repo / "overlay/v222/app/spanishstudy/vot/SpanishSubtitleOverlay.java", overlay)
    print("copied: SubtitleAudioSyncPolicy.java")
    print("copied: SpeakerCostPolicy.java")
    print("copied: SpanishSubtitleOverlay.java")

    # --------------------------------------------------------------------------------------
    # Add a real MediaPlayer onStart callback. v2.20/v2.21 armed subtitle timing in speak(),
    # which can precede actual audible playback by synthesis/prepare latency. The new overload
    # preserves every existing caller while allowing the VOT path to observe mp.start().
    # --------------------------------------------------------------------------------------
    rep(tts,
'''    void play(byte[] mp3, float volume, float rate, long startTimeMs, long id, @Nullable Runnable onDone) {
        Utils.verifyOnMainThread();''',
'''    void play(byte[] mp3, float volume, float rate, long startTimeMs, long id, @Nullable Runnable onDone) {
        play(mp3, volume, rate, startTimeMs, id, null, onDone);
    }

    /** Playback overload with a main-thread callback fired immediately after MediaPlayer.start(). */
    void play(byte[] mp3, float volume, float rate, long startTimeMs, long id,
              @Nullable Runnable onStart, @Nullable Runnable onDone) {
        Utils.verifyOnMainThread();''',
        "add Edge playback onStart overload")

    rep(tts,
'''                playMp3(mp3, volume, rate, startTimeMs, id);''',
'''                playMp3(mp3, volume, rate, startTimeMs, id, onStart);''',
        "pass onStart into MediaPlayer setup")

    rep(tts,
'''    private void playMp3(byte[] mp3, float volume, float rate, long startTimeMs, long id) throws Exception {''',
'''    private void playMp3(byte[] mp3, float volume, float rate, long startTimeMs, long id,
                         @Nullable Runnable onStart) throws Exception {''',
        "accept playback-start callback")

    rep(tts,
'''                mp.start();''',
'''                mp.start();
                if (onStart != null) onStart.run();''',
        "fire subtitle clock at actual audio start")

    # --------------------------------------------------------------------------------------
    # Build the subtitle TTS window from the actual audio start callback instead of speak().
    # Morphe speech synthesis/cache/rate/playback itself remains unchanged.
    # --------------------------------------------------------------------------------------
    rep(vot,
'''import app.spanishstudy.vot.SpanishStudyRuntimeTelemetry;''',
'''import app.spanishstudy.vot.SpanishStudyRuntimeTelemetry;
import app.spanishstudy.vot.SubtitleAudioSyncPolicy;''',
        "import audio subtitle clock policy")

    rep(vot,
'''        SpanishStudyController.onTtsWindow(index, seg.text, speakFromMs, ttsEndVideoTimeMs,
                speechDurationMs, remainingSpeechMs, rate, explicitSeekAttempt);''',
'''        final long subtitleAudioOffsetMs = startTimeMs;
        final Runnable subtitleAudioStarted = () -> {
            final long actualStartVideoMs = VideoInformation.getVideoTime();
            final long actualEndVideoMs = SubtitleAudioSyncPolicy.playbackEndMs(
                    actualStartVideoMs, speechDurationMs, subtitleAudioOffsetMs, rate);
            final long actualRemainingSpeechMs = Math.max(0L, speechDurationMs - subtitleAudioOffsetMs);
            SpanishStudyController.onTtsWindow(index, seg.text, actualStartVideoMs, actualEndVideoMs,
                    speechDurationMs, actualRemainingSpeechMs, rate, explicitSeekAttempt);
        };''',
        "defer subtitle TTS window until audible playback")

    rep(vot,
'''            tts.speak(seg.text, TextToSpeech.QUEUE_FLUSH, params, VOT_ID_PREFIX + id);''',
'''            // Android system TTS does not expose the same MediaPlayer hook; this is the nearest
            // available start point. Edge playback below uses the exact MediaPlayer.start callback.
            subtitleAudioStarted.run();
            tts.speak(seg.text, TextToSpeech.QUEUE_FLUSH, params, VOT_ID_PREFIX + id);''',
        "arm native-system subtitle clock at TTS submission")

    rep(vot,
'''            ttsEngine.play(cached, volume, playbackRate, startTimeMs, playbackId,
                    VoiceOverTranslationPatch::triggerNextSegmentCheck);''',
'''            ttsEngine.play(cached, volume, playbackRate, startTimeMs, playbackId,
                    subtitleAudioStarted, VoiceOverTranslationPatch::triggerNextSegmentCheck);''',
        "lock cached Edge subtitles to real playback start")

    rep(vot,
'''                    ttsEngine.play(finalData, volume, playbackRateNow, startTimeMsSnapshot, playbackId,
                            VoiceOverTranslationPatch::triggerNextSegmentCheck);''',
'''                    ttsEngine.play(finalData, volume, playbackRateNow, startTimeMsSnapshot, playbackId,
                            subtitleAudioStarted, VoiceOverTranslationPatch::triggerNextSegmentCheck);''',
        "lock on-demand Edge subtitles to real playback start")

    rep(controller,
'''        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTtsWindow(
                index, showAtMs, hideAtMs, subtitleStartProgress));''',
'''        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTtsWindow(
                index, showAtMs, hideAtMs, subtitleStartProgress));
        SpanishStudyDiagnostics.record("TTS-AUDIO-START", "epoch="
                + SpanishStudyRuntimeTelemetry.currentEpoch() + " index=" + index
                + " videoMs=" + showAtMs + " endMs=" + hideAtMs
                + " startProgress=" + String.format(java.util.Locale.US, "%.3f", subtitleStartProgress));''',
        "log actual subtitle audio clock start")

    # --------------------------------------------------------------------------------------
    # Make anonymous speaker profiles inspectable rather than showing only A/B/C in diagnostics.
    # --------------------------------------------------------------------------------------
    insert_before(speaker_store,
'''    /** One recent high-confidence acoustic reference per established speaker, up to four speakers. */''',
'''    static synchronized String profileDetails(){
        if(PROFILES.isEmpty())return "No confirmed speaker profiles yet.";
        StringBuilder out=new StringBuilder();
        for(Profile p:PROFILES.values()){
            if(out.length()>0)out.append('\\n');
            out.append("Speaker ").append(p.label)
                    .append(" · ").append(p.assignments).append(" confirmed caption")
                    .append(p.assignments==1?"":"s")
                    .append(" · first ").append(formatTime(p.firstMs==Long.MAX_VALUE?0L:p.firstMs))
                    .append(" · last ").append(formatTime(p.lastMs))
                    .append(" · best confidence ")
                    .append(Math.round(p.bestConfidence*100f)).append('%');
        }
        out.append("\\n\\nLabels are anonymous acoustic clusters, not real-world identity recognition.");
        return out.toString();
    }

''',
        "add readable speaker profile details")

    rep(controller,
'''    public static String speakerProfileStatus() {
        return GeminiSpeakerDiarizationSidecar.status();
    }
''',
'''    public static String speakerProfileStatus() {
        return GeminiSpeakerDiarizationSidecar.status();
    }

    public static String speakerProfileDetails() {
        return SpeakerAssignmentStore.profileDetails();
    }

    public static String speakerUsageStatus() {
        return GeminiSpeakerDiarizationSidecar.usageStatus();
    }

    public static String speakerUsageDetails() {
        return GeminiSpeakerDiarizationSidecar.usageDetails();
    }
''',
        "expose speaker profile and API usage details")

    rep(sheet,
'''        speakerStatus.setOnClickListener(v -> Toast.makeText(activity,
                SpanishStudyController.speakerProfileStatus(), Toast.LENGTH_SHORT).show());
        content.addView(speakerStatus);''',
'''        speakerStatus.setOnClickListener(v -> showSpeakerProfiles(activity));
        content.addView(speakerStatus);
        LinearLayout speakerUsage = valueRow(activity, fg, "Speaker API usage",
                SpanishStudyController.speakerUsageStatus());
        speakerUsage.setOnClickListener(v -> showSpeakerUsage(activity));
        content.addView(speakerUsage);''',
        "show speaker profiles and API usage in menu")

    insert_before(sheet,
'''    private static void showDiagnostics(Activity activity) {''',
'''    private static void showSpeakerProfiles(Activity activity) {
        TextView text = new TextView(activity);
        text.setText(SpanishStudyController.speakerProfileDetails());
        text.setTextIsSelectable(true);
        text.setTextSize(14);
        text.setPadding(Dim.dp16, Dim.dp8, Dim.dp16, Dim.dp8);
        new AlertDialog.Builder(activity)
                .setTitle("Detected speaker profiles")
                .setView(text)
                .setPositiveButton("Close", null)
                .show();
    }

    private static void showSpeakerUsage(Activity activity) {
        TextView text = new TextView(activity);
        text.setText(SpanishStudyController.speakerUsageDetails());
        text.setTextIsSelectable(true);
        text.setTextSize(13);
        text.setPadding(Dim.dp16, Dim.dp8, Dim.dp16, Dim.dp8);
        new AlertDialog.Builder(activity)
                .setTitle("Speaker analysis API usage")
                .setView(text)
                .setPositiveButton("Close", null)
                .show();
    }

''',
        "add speaker detail dialogs")

    # --------------------------------------------------------------------------------------
    # Speaker API: record Interactions usage/cost, slow the cadence substantially, and treat
    # 429 as a long quota/rate-limit backoff instead of repeatedly retrying a doomed request.
    # --------------------------------------------------------------------------------------
    rep(sidecar,
'''    private static final long ONE_SPEAKER_CADENCE_MS = 70_000L;
    private static final long MULTI_SPEAKER_CADENCE_MS = 28_000L;
    private static final long MIN_WALL_BETWEEN_CALLS_MS = 18_000L;''',
'''    private static final long ONE_SPEAKER_CADENCE_MS = 90_000L;
    private static final long MULTI_SPEAKER_CADENCE_MS = 75_000L;
    private static final long MIN_WALL_BETWEEN_CALLS_MS = 45_000L;''',
        "reduce speaker analysis request cadence")

    rep(sidecar,
'''    private static String lastError = "none";''',
'''    private static String lastError = "none";
    private static long usageInputTokens;
    private static long usageToolUseTokens;
    private static long usageOutputTokens;
    private static long usageThoughtTokens;
    private static long usageTotalTokens;
    private static double estimatedPaidCostUsd;''',
        "add speaker token and cost telemetry")

    rep(sidecar,
'''        lastHttpStatus = 0;
        lastLatencyMs = 0L;
        lastError = "none";''',
'''        lastHttpStatus = 0;
        lastLatencyMs = 0L;
        lastError = "none";
        usageInputTokens = 0L;
        usageToolUseTokens = 0L;
        usageOutputTokens = 0L;
        usageThoughtTokens = 0L;
        usageTotalTokens = 0L;
        estimatedPaidCostUsd = 0.0;''',
        "reset speaker usage per video")

    rep(sidecar,
'''        if (code < 200 || code >= 300) {
            String retry = conn.getHeaderField("Retry-After");
            throw new Exception("HTTP " + code + (retry == null ? "" : " retry-after=" + retry)
                    + " " + compactApiError(response));
        }

        String text = extractText(new JSONObject(response));''',
'''        if (code < 200 || code >= 300) {
            if (code == 429) {
                synchronized (GeminiSpeakerDiarizationSidecar.class) {
                    backoffUntilWallMs = Math.max(backoffUntilWallMs,
                            System.currentTimeMillis() + SpeakerCostPolicy.QUOTA_BACKOFF_MS);
                }
            }
            String retry = conn.getHeaderField("Retry-After");
            throw new Exception("HTTP " + code + (retry == null ? "" : " retry-after=" + retry)
                    + " " + compactApiError(response));
        }

        JSONObject root = new JSONObject(response);
        recordUsage(findUsage(root));
        String text = extractText(root);''',
        "record speaker usage and long-backoff HTTP 429")

    rep(sidecar,
'''                        backoffUntilWallMs = System.currentTimeMillis()
                                + Math.min(FAILURE_BACKOFF_MAX_MS, delay);''',
'''                        backoffUntilWallMs = Math.max(backoffUntilWallMs,
                                System.currentTimeMillis() + Math.min(FAILURE_BACKOFF_MAX_MS, delay));''',
        "preserve quota backoff through generic failure handling")

    rep(sidecar,
'''                + "speakerLastError=" + safe(lastError) + '\\n';''',
'''                + "speakerLastError=" + safe(lastError) + '\\n'
                + "speakerInputTokens=" + usageInputTokens + '\\n'
                + "speakerToolUseTokens=" + usageToolUseTokens + '\\n'
                + "speakerOutputTokens=" + usageOutputTokens + '\\n'
                + "speakerThoughtTokens=" + usageThoughtTokens + '\\n'
                + "speakerTotalTokens=" + usageTotalTokens + '\\n'
                + "speakerEstimatedPaidCostUsd="
                + String.format(java.util.Locale.US, "%.6f", estimatedPaidCostUsd) + '\\n';''',
        "publish speaker API token and cost telemetry")

    rep(sidecar,
'''        if (remaining > 0) return base + " · retry in " + (remaining / 1000L) + "s";
        return base;
    }
''',
'''        if (remaining > 0) {
            if (lastHttpStatus == 429) return base + " · Gemini quota limited";
            return base + " · retry in " + (remaining / 1000L) + "s";
        }
        return base;
    }

    static synchronized String usageStatus() {
        return requests + " call" + (requests == 1 ? "" : "s") + " · $"
                + String.format(java.util.Locale.US, "%.4f", estimatedPaidCostUsd) + " est.";
    }

    static synchronized String usageDetails() {
        return "Gemini 3.7 Flash speaker analysis\\n"
                + "Requests: " + requests + " (" + succeeded + " succeeded, " + failed + " failed)\\n"
                + "Input tokens: " + usageInputTokens + "\\n"
                + "Agentic tool-use tokens: " + usageToolUseTokens + "\\n"
                + "Output tokens: " + usageOutputTokens + "\\n"
                + "Thinking tokens: " + usageThoughtTokens + "\\n"
                + "Total reported tokens: " + usageTotalTokens + "\\n"
                + "Estimated paid-tier cost: $"
                + String.format(java.util.Locale.US, "%.6f", estimatedPaidCostUsd)
                + "\\n\\nEstimate uses the Gemini 3.7 Flash Standard introductory rates through 2026-12-31: "
                + "$0.75/M input + $3.75/M output/thinking. Free-tier requests are free. "
                + "HTTP 429 failures normally report no billable usage here.";
    }
''',
        "make speaker quota and cost status visible")

    insert_before(sidecar,
'''    private static String extractText(JSONObject root) {''',
'''    private static JSONObject findUsage(JSONObject root) {
        if (root == null) return null;
        JSONObject usage = root.optJSONObject("usage");
        if (usage != null) return usage;
        JSONObject interaction = root.optJSONObject("interaction");
        return interaction == null ? null : findUsage(interaction);
    }

    private static synchronized void recordUsage(JSONObject usage) {
        if (usage == null) return;
        long input = usage.optLong("total_input_tokens", 0L);
        long tool = usage.optLong("total_tool_use_tokens", 0L);
        long output = usage.optLong("total_output_tokens", 0L);
        long thoughts = usage.optLong("total_thought_tokens", 0L);
        long total = usage.optLong("total_tokens", input + tool + output + thoughts);
        usageInputTokens += Math.max(0L, input);
        usageToolUseTokens += Math.max(0L, tool);
        usageOutputTokens += Math.max(0L, output);
        usageThoughtTokens += Math.max(0L, thoughts);
        usageTotalTokens += Math.max(0L, total);
        estimatedPaidCostUsd += SpeakerCostPolicy.estimatedUsd(input, tool, output, thoughts);
    }

''',
        "parse Interactions API usage object")

    # --------------------------------------------------------------------------------------
    # Diagnostics labels for the new architecture.
    # --------------------------------------------------------------------------------------
    rep(controller,
        'report.append("Spanish Dub Study v2.21.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.22.0 diagnostics\\n");',
        "bump diagnostics to v2.22")

    rep(controller,
        'report.append("subtitleProgressSync=tts-window+partial-speech-offset+source-fallback\\n");',
        'report.append("subtitleProgressSync=actual-audio-start+tts-window+source-only-fallback\\n");',
        "label actual-audio subtitle synchronization")

    rep(controller,
        'report.append("subtitlePageDirection=monotonic-unless-backward-seek\\n");',
        'report.append("subtitlePageDirection=audio-locked-monotonic-unless-backward-seek\\n");\n'
        '        report.append("speakerLabelStyle=separate-pill-badge\\n");\n'
        '        report.append("speakerCostTelemetry=interactions-usage+hypothetical-paid-estimate\\n");',
        "label v2.22 subtitle/speaker UI policies")

    print("v2.22 actual-audio subtitle sync + speaker observability integration complete")


if __name__ == "__main__":
    main()
