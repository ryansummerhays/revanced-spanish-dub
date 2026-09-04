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


def replace_section(path: Path, start_marker: str, end_marker: str, replacement: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"{label}: start marker not found in {path}")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"{label}: end marker not found in {path}")
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2200_subtitles.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    controller = study / "SpanishStudyController.java"
    subtitles = study / "SpanishSubtitleOverlay.java"
    sidecar = study / "GeminiSpeakerDiarizationSidecar.java"
    speaker_store = study / "SpeakerAssignmentStore.java"
    vot = pkg / "VoiceOverTranslationPatch.java"

    for path in (controller, subtitles, sidecar, speaker_store, vot):
        if not path.is_file():
            raise RuntimeError(f"missing v2.19 generated source: {path}")

    shutil.copy2(repo / "overlay/v220/app/spanishstudy/vot/SubtitlePagePolicy.java",
                 study / "SubtitlePagePolicy.java")
    shutil.copy2(repo / "overlay/v220/app/spanishstudy/vot/SpanishSubtitleOverlay.java", subtitles)
    print("copied: SubtitlePagePolicy.java")
    print("copied: SpanishSubtitleOverlay.java")

    rep(controller,
        '''    public static void onTtsWindow(int index, String text, long showAtMs, long hideAtMs,
                                   long remainingSpeechMs, float rate, boolean explicitSeek) {
        if (index < 0 || hideAtMs <= showAtMs) return;
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTtsWindow(index, showAtMs, hideAtMs));''',
        '''    public static void onTtsWindow(int index, String text, long showAtMs, long hideAtMs,
                                   long totalSpeechMs, long remainingSpeechMs,
                                   float rate, boolean explicitSeek) {
        if (index < 0 || hideAtMs <= showAtMs) return;
        final double subtitleStartProgress = SubtitlePagePolicy.startProgress(totalSpeechMs, remainingSpeechMs);
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTtsWindow(
                index, showAtMs, hideAtMs, subtitleStartProgress));''',
        "pass partial TTS progress into subtitle pages")

    rep(vot,
        '''        SpanishStudyController.onTtsWindow(index, seg.text, speakFromMs, ttsEndVideoTimeMs,
                remainingSpeechMs, rate, explicitSeekAttempt);''',
        '''        SpanishStudyController.onTtsWindow(index, seg.text, speakFromMs, ttsEndVideoTimeMs,
                speechDurationMs, remainingSpeechMs, rate, explicitSeekAttempt);''',
        "preserve total and remaining speech duration for page sync")

    rep(controller,
        'report.append("Spanish Dub Study v2.19.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.20.0 diagnostics\\n");',
        "bump diagnostics version")
    rep(controller,
        'report.append("subtitleLinePolicy=up-to-4-lines-autosize\\n");',
        'report.append("subtitleLinePolicy=lossless-pagination-10words-68chars+3-line-safety\\n");\n'
        '        report.append("subtitleProgressSync=tts-window+partial-speech-offset+source-fallback\\n");\n'
        '        report.append("subtitleTextCleanup=display-only-spacing+punctuation-normalization\\n");',
        "publish v2.20 subtitle architecture")
    rep(controller,
        'report.append("speakerBackend=gemini-3.7-flash-youtube-audio-sidecar\\n");',
        'report.append("speakerBackend=gemini-3.7-flash-youtube-agentic-audio-sidecar\\n");',
        "publish speaker request transport change")

    new_build_request = r'''    private static JSONObject buildRequest(String videoId,
                                           List<TranscriptSegment> segments,
                                           long clipStartMs,
                                           long clipEndMs) throws Exception {
        JSONArray input = new JSONArray();
        // v2.19 used a custom static processing object on a public YouTube URI. The live API
        // rejected that shape at input[0].processing. Agentic mode is supported by Gemini 3.7
        // Flash and lets the model seek directly to the requested timestamp region instead.
        input.put(new JSONObject()
                .put("type", "video")
                .put("uri", "https://www.youtube.com/watch?v=" + videoId)
                .put("mime_type", "video/mp4")
                .put("processing", "agentic"));

        StringBuilder prompt = new StringBuilder();
        prompt.append("Perform speaker diarization using the video's DIGITAL AUDIO only. ")
                .append("Inspect the CURRENT WINDOW from ")
                .append(formatTime(clipStartMs)).append(" to ").append(formatTime(clipEndMs))
                .append(" and inspect established anchor timestamps only when needed for voice comparison. ")
                .append("Cluster HUMAN SPEAKERS by acoustic voice identity. ")
                .append("This is diarization, not identity recognition: use anonymous labels A-H only. ")
                .append("The same person must keep the same label across the video. Do not create a new person because someone yells, whispers, laughs, changes emotion/accent/prosody, or has a temporary microphone/voice-chat effect. ")
                .append("If uncertain, prefer an established prior profile instead of inventing a switch. ")
                .append("Return exactly one item per caption event below. confidence is 0..1 and reflects acoustic speaker-identity confidence, not transcript confidence.\n")
                .append(SpeakerAssignmentStore.rosterPrompt()).append("\n\nEVENTS IN CURRENT WINDOW:\n");
        for (int i = 0; i < segments.size(); i++) {
            TranscriptSegment s = segments.get(i);
            prompt.append(i).append(" | ").append(formatTime(s.startMs)).append('-')
                    .append(formatTime(s.endMs)).append(" | ")
                    .append(s.text == null ? "" : s.text.replace('\n', ' ')).append('\n');
        }
        input.put(new JSONObject().put("type", "text").put("text", prompt.toString()));

        JSONObject itemSchema = new JSONObject()
                .put("type", "object")
                .put("properties", new JSONObject()
                        .put("id", new JSONObject().put("type", "integer"))
                        .put("speaker", new JSONObject().put("type", "string"))
                        .put("confidence", new JSONObject().put("type", "number")))
                .put("required", new JSONArray().put("id").put("speaker").put("confidence"));
        JSONObject schema = new JSONObject()
                .put("type", "object")
                .put("properties", new JSONObject().put("items", new JSONObject()
                        .put("type", "array")
                        .put("minItems", segments.size())
                        .put("maxItems", segments.size())
                        .put("items", itemSchema)))
                .put("required", new JSONArray().put("items"));

        return new JSONObject()
                .put("model", DIARIZATION_MODEL)
                .put("input", input)
                .put("generation_config", new JSONObject()
                        .put("temperature", 0.0)
                        .put("max_output_tokens", Math.max(500, segments.size() * 45)))
                .put("response_format", new JSONObject()
                        .put("type", "text")
                        .put("mime_type", "application/json")
                        .put("schema", schema));
    }

'''
    replace_section(sidecar,
                    "    private static JSONObject buildRequest(String videoId,",
                    "    private static String extractText(JSONObject root)",
                    new_build_request,
                    "replace rejected speaker processing object with agentic timestamp navigation")

    rep(speaker_store,
        '''        out.append(". If named reference clips are attached, compare voice identity against them before creating a new label. Do not create a new speaker merely because the same person yells, whispers, laughs, changes accent/prosody, or comes through a different microphone effect.");''',
        '''        out.append(". Use those timestamps as acoustic anchors when comparing voice identity before creating a new label. Do not create a new speaker merely because the same person yells, whispers, laughs, changes accent/prosody, or comes through a different microphone effect.");''',
        "make speaker anchors timestamp-native")

    print("v2.20 subtitle pagination and speaker request repair complete")


if __name__ == "__main__":
    main()
