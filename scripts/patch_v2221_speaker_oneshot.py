#!/usr/bin/env python3
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def replace_section(path: Path, start_marker: str, end_marker: str,
                    replacement: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"{label}: start marker not found")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"{label}: end marker not found")
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2221_speaker_oneshot.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    sidecar = study / "GeminiSpeakerDiarizationSidecar.java"
    controller = study / "SpanishStudyController.java"

    rep(sidecar,
        '''    private static final int READ_TIMEOUT_MS = 45_000;''',
        '''    private static final int READ_TIMEOUT_MS = 120_000;''',
        "allow one-shot full-video analysis to finish")

    rep(sidecar,
        '''    private static final int MAX_EVENTS_PER_WINDOW = 48;''',
        '''    private static final int MAX_EVENTS_PER_WINDOW = 700;''',
        "bound full-video speaker response below model output ceiling")

    rep(sidecar,
        '''    private static boolean inFlight;''',
        '''    private static boolean inFlight;
    private static boolean analysisComplete;''',
        "track completed one-shot speaker map")

    rep(sidecar,
        '''        consecutiveFailures = 0;
        inFlight = false;
        requestGeneration++;''',
        '''        consecutiveFailures = 0;
        inFlight = false;
        analysisComplete = false;
        requestGeneration++;''',
        "reset one-shot completion on new video")

    rep(sidecar,
        '''        final long now = System.currentTimeMillis();''',
        '''        synchronized (GeminiSpeakerDiarizationSidecar.class) {
            if (analysisComplete) return;
        }
        final long now = System.currentTimeMillis();''',
        "stop scheduling after full-video speaker map succeeds")

    new_select = '''    private static List<TranscriptSegment> selectWindow(List<TranscriptSegment> source, long playheadMs) {
        ArrayList<TranscriptSegment> valid = new ArrayList<>();
        for (TranscriptSegment seg : source) if (seg != null) valid.add(seg);
        if (valid.size() <= MAX_EVENTS_PER_WINDOW) return valid;

        // Uniformly cover the whole video instead of truncating to its beginning. Existing
        // bounded profile propagation fills the small gaps between sampled caption events.
        ArrayList<TranscriptSegment> sampled = new ArrayList<>(MAX_EVENTS_PER_WINDOW);
        for (int i = 0; i < MAX_EVENTS_PER_WINDOW; i++) {
            int index = (int) Math.round(i * (valid.size() - 1.0)
                    / Math.max(1.0, MAX_EVENTS_PER_WINDOW - 1.0));
            TranscriptSegment seg = valid.get(index);
            if (sampled.isEmpty() || sampled.get(sampled.size() - 1) != seg) sampled.add(seg);
        }
        return sampled;
    }

'''
    replace_section(sidecar,
                    "    private static List<TranscriptSegment> selectWindow(",
                    "    private static List<SpeakerAssignmentStore.Proposal> request(",
                    new_select,
                    "sample the full caption timeline rather than rolling windows")

    rep(sidecar,
        '''        final long clipStartMs = Math.max(0L, playheadMs - WINDOW_BEHIND_MS);
        final long clipEndMs = Math.max(clipStartMs + 1_000L, playheadMs + WINDOW_AHEAD_MS);
        final List<TranscriptSegment> snapshot = new ArrayList<>(window);''',
        '''        final long clipStartMs = 0L;
        final long clipEndMs = Math.max(1_000L, window.get(window.size() - 1).endMs);
        final List<TranscriptSegment> snapshot = new ArrayList<>(window);''',
        "request one full-video speaker timeline")

    rep(sidecar,
        '''                            succeeded++;
                            lastLatencyMs = System.currentTimeMillis() - requestStartedMs;
                            lastError = "none";''',
        '''                            succeeded++;
                            analysisComplete = true;
                            lastLatencyMs = System.currentTimeMillis() - requestStartedMs;
                            lastError = "none";''',
        "mark full-video speaker map complete")

    rep(sidecar,
        '''        if (inFlight) return base + " · analyzing";''',
        '''        if (inFlight) return base + " · mapping full video";
        if (analysisComplete) return base + " · mapped";''',
        "show one-shot map state in menu")

    rep(sidecar,
        '''        // v2.19 used a custom static processing object on a public YouTube URI. The live API
        // rejected that shape at input[0].processing. Agentic mode is supported by Gemini 3.7
        // Flash and lets the model seek directly to the requested timestamp region instead.''',
        '''        // Agentic mode receives the public YouTube video once and navigates across the full
        // caption timeline. v2.22 intentionally avoids repeated full-URL requests for rolling windows.''',
        "document one-shot agentic speaker mapping")

    rep(sidecar,
        '''        prompt.append("Perform speaker diarization using the video's DIGITAL AUDIO only. ")
                .append("Inspect the CURRENT WINDOW from ")
                .append(formatTime(clipStartMs)).append(" to ").append(formatTime(clipEndMs))
                .append(" and inspect established anchor timestamps only when needed for voice comparison. ")''',
        '''        prompt.append("Perform speaker diarization using the video's DIGITAL AUDIO only. ")
                .append("Map speaker identity across the FULL VIDEO caption timeline from ")
                .append(formatTime(clipStartMs)).append(" to ").append(formatTime(clipEndMs))
                .append(". Navigate to each supplied caption timestamp and compare voices globally before assigning labels. ")''',
        "prompt global speaker consistency in one request")

    rep(sidecar,
        '''                .append(SpeakerAssignmentStore.rosterPrompt()).append("\\n\\nEVENTS IN CURRENT WINDOW:\\n");''',
        '''                .append(SpeakerAssignmentStore.rosterPrompt()).append("\\n\\nCAPTION EVENTS ACROSS FULL VIDEO:\\n");''',
        "label full-video event list")

    rep(sidecar,
        '''                        .put("max_output_tokens", Math.max(1200, segments.size() * 80)))''',
        '''                        .put("max_output_tokens", Math.min(60_000,
                                Math.max(1200, segments.size() * 80))))''',
        "cap one-shot structured output allowance")

    rep(controller,
        '''        report.append("speakerCostTelemetry=interactions-usage+hypothetical-paid-estimate\\n");''',
        '''        report.append("speakerCostTelemetry=interactions-usage+hypothetical-paid-estimate\\n");
        report.append("speakerAnalysisMode=one-shot-full-video-caption-map\\n");''',
        "publish one-shot speaker architecture")

    print("v2.22 one-shot full-video speaker mapping integration complete")


if __name__ == "__main__":
    main()
