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

    # ------------------------------------------------------------------------------------------
    # 2) Bound every realtime OpenRouter batch, not only startup, and allow two small subrequests.
    # ------------------------------------------------------------------------------------------
    insert_after(translator,
                 "import java.util.HashMap;\n",
                 "import java.util.IdentityHashMap;\n",
                 "import IdentityHashMap for active OpenRouter connections")
    insert_after(translator,
                 "import java.util.Map;\n",
                 "import java.util.Set;\n",
                 "import Set for active OpenRouter connections")
    insert_after(translator,
                 "import java.util.concurrent.ExecutionException;\n",
                 "import java.util.concurrent.ExecutorService;\n"
                 "import java.util.concurrent.Executors;\n"
                 "import java.util.concurrent.Future;\n",
                 "import bounded OpenRouter parallel executor")
    insert_after(translator,
                 "import app.spanishstudy.vot.TranslationQualityLog;\n",
                 "import app.spanishstudy.vot.RealtimeTranslationPlanner;\n"
                 "import app.spanishstudy.vot.TranslationProvenanceLog;\n"
                 "import app.spanishstudy.vot.VideoTranslationContext;\n",
                 "import realtime/context/provenance helpers")

    rep(translator,
        "    private static final int OPENROUTER_MAX_BATCH_CHARS = 1_500;\n",
        "    private static final int OPENROUTER_MAX_BATCH_CHARS = RealtimeTranslationPlanner.MAX_BATCH_CHARS;\n",
        "hard-cap every OpenRouter batch by realtime character budget")

    rep(translator,
        "    private static volatile HttpURLConnection activeConnection;\n",
        '''    private static final Set<HttpURLConnection> activeConnections = Collections.synchronizedSet(
            Collections.newSetFromMap(new IdentityHashMap<>()));
    private static final AtomicInteger openRouterHttpRequestSerial = new AtomicInteger();
''',
        "track both concurrent OpenRouter connections")

    # v2.14.1 added externalAbortRequested before these lines.
    rep(translator,
        '''        abortTranslation = true;
        HttpURLConnection conn = activeConnection;
        if (conn != null) conn.disconnect();''',
        '''        abortTranslation = true;
        disconnectActiveConnections();''',
        "abort all concurrent OpenRouter streams")

    # patch_playhead_priority intentionally made onSeek work for non-streaming providers too. Keep
    # that behavior; only replace the obsolete singleton connection inside the delayed cutter.
    rep(translator,
        '''    private static void applySeekCut() {
        HttpURLConnection conn = activeConnection;
        List<List<TranscriptSegment>> batches = liveBatches;''',
        '''    private static void applySeekCut() {
        List<List<TranscriptSegment>> batches = liveBatches;''',
        "seek cutter no longer reads singleton connection")

    rep(translator,
        '''        reprioritize = true;
        // Streaming requests can be cut immediately. Non-streaming Gemini cannot be interrupted
        // through this upstream connection field, but its result is discarded as soon as it returns
        // and the dispatcher re-picks the batch under the current playhead.
        if (conn != null) conn.disconnect();
    }
''',
        '''        reprioritize = true;
        // Cut every in-flight OpenRouter subrequest. Non-streaming providers still keep the existing
        // reprioritize behavior and simply discard their stale result when it returns.
        disconnectActiveConnections();
    }

    private static void disconnectActiveConnections() {
        HttpURLConnection[] snapshot;
        synchronized (activeConnections) {
            snapshot = activeConnections.toArray(new HttpURLConnection[0]);
        }
        for (HttpURLConnection conn : snapshot) {
            try { conn.disconnect(); } catch (Exception ignored) {}
        }
    }
''',
        "seek cutter disconnects every OpenRouter stream and adds helper")

    # After the existing startup cap, enforce the realtime event cap on every OpenRouter dispatch.
    rep(translator,
        '''                if (firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }
                firstBatchAfterReposition = false;

                List<TranscriptSegment> batch = batches.get(index);''',
        '''                if (firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }
                firstBatchAfterReposition = false;
                if (isOpenRouter) {
                    capRealtimeBatch(batches, batchDone, index);
                }

                List<TranscriptSegment> batch = batches.get(index);''',
        "enforce microbatch size on every OpenRouter dispatch")

    # Add the general realtime cap immediately after the historical startup cap helper.
    cap_end = '''        batches.set(index, head);
        batches.add(index + 1, tail);
        batchDone.add(index + 1, false);
    }

    /**
     * Picks the not-yet-translated batch to translate next:'''
    cap_new = '''        batches.set(index, head);
        batches.add(index + 1, tail);
        batchDone.add(index + 1, false);
    }

    /** Keep every foreground OpenRouter request inside the tested realtime event/character budget. */
    private static void capRealtimeBatch(List<List<TranscriptSegment>> batches,
                                         List<Boolean> batchDone, int index) {
        List<TranscriptSegment> batch = batches.get(index);
        if (batch.size() <= 1) return;
        ArrayList<String> texts = new ArrayList<>(batch.size());
        for (TranscriptSegment segment : batch) texts.add(segment.text);
        int splitAt = RealtimeTranslationPlanner.boundedSegmentCount(texts);
        if (splitAt <= 0 || splitAt >= batch.size()) return;
        List<TranscriptSegment> head = new ArrayList<>(batch.subList(0, splitAt));
        List<TranscriptSegment> tail = new ArrayList<>(batch.subList(splitAt, batch.size()));
        batches.set(index, head);
        batches.add(index + 1, tail);
        batchDone.add(index + 1, false);
    }

    /**
     * Picks the not-yet-translated batch to translate next:'''
    rep(translator, cap_end, cap_new, "add general realtime OpenRouter cap helper")

    # Thread videoId into the stream callback so first-ready provenance can be recorded immediately.
    rep(translator,
        '''                        streamCallback(onUpdate, mainHandler, working, batch, offset, targetLang));''',
        '''                        streamCallback(videoId, onUpdate, mainHandler, working, batch, offset, targetLang));''',
        "pass video id into streaming provenance callback")
    rep(translator,
        '''    private static Consumer<List<String>> streamCallback(
            @Nullable Consumer<List<TranscriptSegment>> onUpdate,''',
        '''    private static Consumer<List<String>> streamCallback(
            String videoId,
            @Nullable Consumer<List<TranscriptSegment>> onUpdate,''',
        "extend stream callback signature for provenance")

    rep(translator,
        '''        return partial -> {
            List<TranscriptSegment> snap = new ArrayList<>(working);''',
        '''        return partial -> {
            for (int j = 0; j < Math.min(batch.size(), partial.size()); j++) {
                String translatedText = partial.get(j);
                if (translatedText == null || translatedText.equals(batch.get(j).text)) continue;
                int globalIndex = offset + j;
                if (TranslationProvenanceLog.markReady(videoId, globalIndex,
                        TRANSLATION_SERVICE_OPENROUTER, Settings.VOT_OPENROUTER_MODEL.get().trim(),
                        "stream", translatedText)) {
                    SpanishStudyDiagnostics.record("TRANSLATION-READY", "index=" + globalIndex
                            + " provider=openrouter path=stream");
                }
            }
            List<TranscriptSegment> snap = new ArrayList<>(working);''',
        "record first streamed translation readiness")

    rep(translator,
        '''            List<TranscriptSegment> snap = new ArrayList<>(working);
            applyBatch(snap, batch, offset, partial, lang);
            mainHandler.post(() -> onUpdate.accept(snap));''',
        '''            // Critical correctness rule: partial OpenRouter results contain untranslated source
            // placeholders for slots that have not streamed yet. Never run applyBatch() across the
            // whole partial list, because that would relabel those English placeholders as Spanish
            // and make TTS believe they were translated. Publish only slots whose text changed.
            List<TranscriptSegment> snap = new ArrayList<>(working);
            for (int j = 0; j < Math.min(batch.size(), partial.size()); j++) {
                String translatedText = partial.get(j);
                TranscriptSegment orig = batch.get(j);
                if (translatedText == null || translatedText.equals(orig.text)) continue;
                snap.set(offset + j, new TranscriptSegment(
                        orig.startMs, orig.endMs, translatedText, lang));
            }
            mainHandler.post(() -> onUpdate.accept(snap));''',
        "publish only actually translated streamed slots")

    # Logical provider request latency and per-video provenance lifecycle.
    rep(translator,
        '''        TranslationQualityLog.beginVideo(videoId);
        final String selected = Settings.VOT_TRANSLATION_SERVICE.get();''',
        '''        TranslationQualityLog.beginVideo(videoId);
        TranslationProvenanceLog.beginVideo(videoId);
        final long providerRequestStartedMs = System.currentTimeMillis();
        final String selected = Settings.VOT_TRANSLATION_SERVICE.get();''',
        "start provider latency/provenance clock")
    rep(translator,
        '''            SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "result provider="
                    + effectiveAfter + " outputs=" + translated.size());''',
        '''            SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "result provider="
                    + effectiveAfter + " outputs=" + translated.size()
                    + " elapsedMs=" + (System.currentTimeMillis() - providerRequestStartedMs));''',
        "record logical provider latency")

    # Add videoId to quality recorder calls/signature so non-streamed/fallback translations also have provenance.
    text = translator.read_text(encoding="utf-8")
    text = text.replace("recordTranslationQuality(effectiveAfter, batch, translated);",
                        "recordTranslationQuality(videoId, effectiveAfter, batch, translated);")
    text = text.replace("recordTranslationQuality(TRANSLATION_SERVICE_GOOGLE, batch, fallback);",
                        "recordTranslationQuality(videoId, TRANSLATION_SERVICE_GOOGLE, batch, fallback);")
    text = text.replace("recordTranslationQuality(effectiveBefore, batch, translated);",
                        "recordTranslationQuality(videoId, effectiveBefore, batch, translated);")
    old_sig = '''    private static void recordTranslationQuality(String provider,
                                                 List<TranscriptSegment> batch,'''
    if text.count(old_sig) != 1:
        raise RuntimeError("recordTranslationQuality signature anchor missing")
    text = text.replace(old_sig, '''    private static void recordTranslationQuality(String videoId,
                                                 String provider,
                                                 List<TranscriptSegment> batch,''', 1)
    old_record = '''            TranslationQualityLog.record(provider, model, globalIndex,
                    seg.startMs, seg.endMs, seg.text, target);'''
    if text.count(old_record) != 1:
        raise RuntimeError("quality record anchor missing")
    text = text.replace(old_record, old_record + '''
            if (target != null && !target.equals(seg.text)) {
                TranslationProvenanceLog.markReady(videoId, globalIndex, provider, model,
                        "batch-final", target);
            }''', 1)
    translator.write_text(text, encoding="utf-8")
    print("patched: final/fallback translation provenance")


    print("v2.15b realtime core/provenance integration complete")


if __name__ == "__main__":
    main()
