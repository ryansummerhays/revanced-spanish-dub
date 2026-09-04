#!/usr/bin/env python3
"""v2.15.0: realtime OpenRouter microbatches, video-specific raw-caption context, provenance, and UI cleanup."""
from pathlib import Path
import re
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def insert_after(path: Path, anchor: str, addition: str, label: str) -> None:
    rep(path, anchor, anchor + addition, label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v215_realtime_context.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    fetcher = pkg / "TranscriptFetcher.java"
    translator = pkg / "TranscriptTranslator.java"
    vot = pkg / "VoiceOverTranslationPatch.java"
    controller = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    for p in (fetcher, translator, vot, controller, sheet):
        if not p.is_file():
            raise RuntimeError(f"missing required source: {p}")

    # Replace one OpenRouter stream with a two-way wrapper while keeping one logical batch/timeline.
    text = translator.read_text(encoding="utf-8")
    single_sig = '''    private static List<String> translateBatchOpenRouter(
            String videoId,
            List<TranscriptSegment> segments, String targetLang,
            @Nullable Consumer<List<String>> onLineStreamed) throws Exception {'''
    if text.count(single_sig) != 1:
        raise RuntimeError("OpenRouter method signature anchor missing")
    renamed = single_sig.replace("translateBatchOpenRouter(", "translateBatchOpenRouterSingle(")
    text = text.replace(single_sig, renamed, 1)
    at = text.index(renamed)
    wrapper = r'''    private static List<String> translateBatchOpenRouter(
            String videoId,
            List<TranscriptSegment> segments, String targetLang,
            @Nullable Consumer<List<String>> onLineStreamed) throws Exception {
        final int size = segments.size();
        if (size <= 1 || RealtimeTranslationPlanner.OPENROUTER_PARALLEL_REQUESTS < 2) {
            return translateBatchOpenRouterSingle(videoId, segments, targetLang, onLineStreamed);
        }

        final int split = (size + 1) / 2;
        final List<TranscriptSegment> leftSegments = new ArrayList<>(segments.subList(0, split));
        final List<TranscriptSegment> rightSegments = new ArrayList<>(segments.subList(split, size));
        final List<String> merged = new ArrayList<>(size);
        for (TranscriptSegment segment : segments) merged.add(segment.text);

        Consumer<List<String>> leftStream = onLineStreamed == null ? null
                : partial -> publishParallelPartial(merged, 0, partial, onLineStreamed);
        Consumer<List<String>> rightStream = onLineStreamed == null ? null
                : partial -> publishParallelPartial(merged, split, partial, onLineStreamed);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        SpanishStudyDiagnostics.record("OPENROUTER-PARALLEL", "logical events=" + size
                + " split=" + leftSegments.size() + "+" + rightSegments.size());
        try {
            Future<List<String>> leftFuture = pool.submit(() ->
                    translateBatchOpenRouterSingle(videoId, leftSegments, targetLang, leftStream));
            Future<List<String>> rightFuture = pool.submit(() ->
                    translateBatchOpenRouterSingle(videoId, rightSegments, targetLang, rightStream));
            List<String> left;
            List<String> right;
            try {
                left = leftFuture.get();
                right = rightFuture.get();
            } catch (ExecutionException ex) {
                disconnectActiveConnections();
                Throwable cause = ex.getCause();
                if (cause instanceof Exception) throw (Exception) cause;
                throw new RuntimeException(cause);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                disconnectActiveConnections();
                throw ex;
            }
            synchronized (merged) {
                for (int i = 0; i < left.size() && i < leftSegments.size(); i++) merged.set(i, left.get(i));
                for (int i = 0; i < right.size() && i < rightSegments.size(); i++) merged.set(split + i, right.get(i));
            }

            // translateBatchOpenRouterSingle returns exactly the contiguous numbered prefix that the
            // provider actually supplied. Use those returned lengths as the completion signal rather
            // than comparing translated text with English source text: proper nouns, acronyms and
            // coined terms may legitimately remain byte-for-byte unchanged after translation.
            final int leftReady = Math.min(left.size(), leftSegments.size());
            final int rightReady = Math.min(right.size(), rightSegments.size());
            final int contiguous = leftReady < leftSegments.size()
                    ? leftReady
                    : leftSegments.size() + rightReady;
            synchronized (merged) {
                if (contiguous >= size) return new ArrayList<>(merged);
                if (contiguous > 0) return new ArrayList<>(merged.subList(0, contiguous));
            }
            return new ArrayList<>();
        } finally {
            pool.shutdownNow();
        }
    }

    private static void publishParallelPartial(List<String> merged, int offset,
                                               List<String> partial,
                                               Consumer<List<String>> callback) {
        List<String> snapshot;
        synchronized (merged) {
            for (int i = 0; i < partial.size() && offset + i < merged.size(); i++) {
                merged.set(offset + i, partial.get(i));
            }
            snapshot = new ArrayList<>(merged);
        }
        callback.accept(snapshot);
    }

'''
    text = text[:at] + wrapper + text[at:]
    translator.write_text(text, encoding="utf-8")
    print("patched: two-way concurrent OpenRouter microbatch wrapper")

    # Refactor the renamed single request to participate in active connection set.
    rep(translator,
        '''        activeConnection = conn;
        try {''',
        '''        activeConnections.add(conn);
        try {''',
        "register each OpenRouter HTTP stream")
    rep(translator,
        '''        } finally {
            if (activeConnection == conn) activeConnection = null;
        }
''',
        '''        } finally {
            activeConnections.remove(conn);
        }
''',
        "unregister each OpenRouter HTTP stream")

    # Duration-aware, video-specific prompt. The AI silently repairs obvious ASR issues but returns
    # only Spanish so token output/latency is not doubled by a second corrected-English channel.
    rep(translator,
        '''            joined.append(i + 1).append(": ").append(segments.get(i).text);''',
        '''            TranscriptSegment input = segments.get(i);
            double slotSeconds = Math.max(1L, input.endMs - input.startMs) / 1000.0;
            joined.append(i + 1).append(" [slot=")
                    .append(String.format(Locale.ROOT, "%.2fs", slotSeconds))
                    .append("]: ").append(input.text);''',
        "include source-duration hint in OpenRouter input")

    old_prompt = '''        String targetLangName = Locale.forLanguageTag(targetLang).getDisplayLanguage(Locale.ENGLISH);
        JSONObject systemMessage = new JSONObject()
                .put("role", "system")
                .put("content", "Translate numbered YouTube caption lines to " + targetLangName + " (" + targetLang + "). "
                        + "The text may have misspellings or noise - translate the intent. "
                        + "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.");
        JSONObject userMessage = new JSONObject()
                .put("role", "user")
                .put("content", joined.toString());'''
    new_prompt = '''        String targetLangName = Locale.forLanguageTag(targetLang).getDisplayLanguage(Locale.ENGLISH);
        TranscriptSegment firstContextSegment = segments.get(0);
        TranscriptSegment lastContextSegment = segments.get(segments.size() - 1);
        String videoContext = VideoTranslationContext.contextFor(videoId,
                firstContextSegment.startMs, lastContextSegment.endMs);
        String guidance = "Produce natural spoken " + targetLangName + " (" + targetLang
                + ") dubbing for numbered YouTube captions. "
                + "Silently repair only obvious English ASR/punctuation mistakes when the nearby raw captions or video context strongly support the correction. "
                + "Use video context to resolve proper nouns, jargon, jokes, slang and coined terms; never force context onto unrelated text. "
                + "Preserve official names and established terminology when supported. "
                + "For each line, preserve the full meaning but prefer concise conversational Spanish that can be spoken within its [slot] duration at normal-to-moderately-fast speech. Avoid needless expansion or filler. "
                + "Return ONLY one Spanish line per input, prefixed with the original line number and a colon. Do not merge, skip, explain, or output corrected English."
                + (videoContext.isEmpty() ? "" : "\\n\\nVIDEO-SPECIFIC CONTEXT (reference only):\\n" + videoContext);
        JSONObject systemMessage = new JSONObject()
                .put("role", "system")
                .put("content", guidance);
        JSONObject userMessage = new JSONObject()
                .put("role", "user")
                .put("content", joined.toString());'''
    rep(translator, old_prompt, new_prompt, "add video-specific raw-caption context and concise dubbing prompt")

    # Request-level telemetry: start, TTFT, completion, context size. No transcript or credentials.
    rep(translator,
        '''        String model = Settings.VOT_OPENROUTER_MODEL.get();
        final long start = System.currentTimeMillis();''',
        '''        String model = Settings.VOT_OPENROUTER_MODEL.get();
        final long start = System.currentTimeMillis();
        final int requestId = openRouterHttpRequestSerial.incrementAndGet();''',
        "assign OpenRouter HTTP request id")
    rep(translator,
        '''        byte[] bodyBytes = body.toString().getBytes(StandardCharsets.UTF_8);
''',
        '''        SpanishStudyDiagnostics.record("OPENROUTER-REQ", "start id=" + requestId
                + " events=" + segments.size() + " contextChars=" + videoContext.length()
                + " model=" + model);
        byte[] bodyBytes = body.toString().getBytes(StandardCharsets.UTF_8);
''',
        "log OpenRouter subrequest start")
    rep(translator,
        '''                String sseLine;
                while ((sseLine = reader.readLine()) != null) {''',
        '''                String sseLine;
                boolean firstTokenLogged = false;
                while ((sseLine = reader.readLine()) != null) {''',
        "track first OpenRouter token")
    rep(translator,
        '''                    String content = delta.optString("content", "");
                    rawOutput.append(content);''',
        '''                    String content = delta.optString("content", "");
                    if (!firstTokenLogged && !content.isEmpty()) {
                        firstTokenLogged = true;
                        SpanishStudyDiagnostics.record("OPENROUTER-REQ", "ttft id=" + requestId
                                + " ms=" + (System.currentTimeMillis() - start));
                    }
                    rawOutput.append(content);''',
        "log OpenRouter TTFT")
    rep(translator,
        '''        Logger.printDebug(() -> "OpenRouter translation complete: " + targetLang
                + " fetchTime: " + (System.currentTimeMillis() - start) + "ms");''',
        '''        Logger.printDebug(() -> "OpenRouter translation complete: " + targetLang
                + " fetchTime: " + (System.currentTimeMillis() - start) + "ms");
        SpanishStudyDiagnostics.record("OPENROUTER-REQ", "done id=" + requestId
                + " elapsedMs=" + (System.currentTimeMillis() - start)
                + " matched=" + matchedFirst + "/" + segmentSize);''',
        "log OpenRouter subrequest completion")

    print("v2.15c OpenRouter parallel/context telemetry integration complete")


if __name__ == "__main__":
    main()
