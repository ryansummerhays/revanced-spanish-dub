#!/usr/bin/env python3
"""v2.15.0 realtime core: bounded OpenRouter batching, streamed-slot correctness, and provenance."""
from pathlib import Path
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
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = pkg / "TranscriptTranslator.java"

    insert_after(translator,"import java.util.HashMap;\n","import java.util.IdentityHashMap;\n","import IdentityHashMap")
    insert_after(translator,"import java.util.Map;\n","import java.util.Set;\n","import active-connection Set")
    insert_after(translator,"import java.util.concurrent.ExecutionException;\n",
                 "import java.util.concurrent.ExecutorService;\nimport java.util.concurrent.Executors;\nimport java.util.concurrent.Future;\n",
                 "import OpenRouter executor")
    insert_after(translator,"import app.spanishstudy.vot.TranslationQualityLog;\n",
                 "import app.spanishstudy.vot.RealtimeTranslationPlanner;\n"
                 "import app.spanishstudy.vot.TranslationProvenanceLog;\n"
                 "import app.spanishstudy.vot.VideoTranslationContext;\n",
                 "import v2.15 helpers")

    rep(translator,"    private static final int OPENROUTER_MAX_BATCH_CHARS = 1_500;\n",
        "    private static final int OPENROUTER_MAX_BATCH_CHARS = RealtimeTranslationPlanner.MAX_BATCH_CHARS;\n",
        "hard realtime char cap")
    rep(translator,"    private static volatile HttpURLConnection activeConnection;\n",
        '''    private static final Set<HttpURLConnection> activeConnections = Collections.synchronizedSet(
            Collections.newSetFromMap(new IdentityHashMap<>()));
    private static final AtomicInteger openRouterHttpRequestSerial = new AtomicInteger();
''',"track concurrent OpenRouter connections")

    rep(translator,'''        abortTranslation = true;
        HttpURLConnection conn = activeConnection;
        if (conn != null) conn.disconnect();''',
        '''        abortTranslation = true;
        disconnectActiveConnections();''',"abort concurrent OpenRouter streams")
    rep(translator,'''    static void onSeek(long timeMs) {
        if (activeConnection == null) return; // Only an in-flight streaming request can be cut.''',
        '''    static void onSeek(long timeMs) {
        if (activeConnections.isEmpty()) return; // Only in-flight streaming requests can be cut.''',"seek sees either stream")
    rep(translator,'''    private static void applySeekCut() {
        HttpURLConnection conn = activeConnection;
        if (conn == null) return;''',
        '''    private static void applySeekCut() {
        if (activeConnections.isEmpty()) return;''',"seek cutter sees concurrent streams")
    rep(translator,'''        reprioritize = true;
        conn.disconnect();
    }
''',
        '''        reprioritize = true;
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
''',"add disconnect-all helper")

    rep(translator,'''                if (firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }
                firstBatchAfterReposition = false;

                List<TranscriptSegment> batch = batches.get(index);''',
        '''                if (firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }
                firstBatchAfterReposition = false;
                if (isOpenRouter) capRealtimeBatch(batches, batchDone, index);

                List<TranscriptSegment> batch = batches.get(index);''',"cap every OpenRouter dispatch")

    cap_end='''        batches.set(index, head);
        batches.add(index + 1, tail);
        batchDone.add(index + 1, false);
    }

    /**
     * Picks the not-yet-translated batch to translate next:'''
    cap_new='''        batches.set(index, head);
        batches.add(index + 1, tail);
        batchDone.add(index + 1, false);
    }

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
    rep(translator,cap_end,cap_new,"add realtime batch helper")

    rep(translator,'''                        streamCallback(onUpdate, mainHandler, working, batch, offset, targetLang));''',
        '''                        streamCallback(videoId, onUpdate, mainHandler, working, batch, offset, targetLang));''',"thread videoId into stream callback")
    rep(translator,'''    private static Consumer<List<String>> streamCallback(
            @Nullable Consumer<List<TranscriptSegment>> onUpdate,''',
        '''    private static Consumer<List<String>> streamCallback(
            String videoId,
            @Nullable Consumer<List<TranscriptSegment>> onUpdate,''',"extend stream callback")
    rep(translator,'''        return partial -> {
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
            List<TranscriptSegment> snap = new ArrayList<>(working);''',"record streamed readiness")
    rep(translator,'''            List<TranscriptSegment> snap = new ArrayList<>(working);
            applyBatch(snap, batch, offset, partial, lang);
            mainHandler.post(() -> onUpdate.accept(snap));''',
        '''            // Never run applyBatch() across the full partial list: untranslated source placeholders
            // must not be relabeled as target-language text and become TTS-ready.
            List<TranscriptSegment> snap = new ArrayList<>(working);
            for (int j = 0; j < Math.min(batch.size(), partial.size()); j++) {
                String translatedText = partial.get(j);
                TranscriptSegment orig = batch.get(j);
                if (translatedText == null || translatedText.equals(orig.text)) continue;
                snap.set(offset + j, new TranscriptSegment(orig.startMs, orig.endMs, translatedText, lang));
            }
            mainHandler.post(() -> onUpdate.accept(snap));''',"publish translated streamed slots only")

    rep(translator,'''        TranslationQualityLog.beginVideo(videoId);
        final String selected = Settings.VOT_TRANSLATION_SERVICE.get();''',
        '''        TranslationQualityLog.beginVideo(videoId);
        TranslationProvenanceLog.beginVideo(videoId);
        final long providerRequestStartedMs = System.currentTimeMillis();
        final String selected = Settings.VOT_TRANSLATION_SERVICE.get();''',"start provider provenance clock")
    rep(translator,'''            SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "result provider="
                    + effectiveAfter + " outputs=" + translated.size());''',
        '''            SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "result provider="
                    + effectiveAfter + " outputs=" + translated.size()
                    + " elapsedMs=" + (System.currentTimeMillis() - providerRequestStartedMs));''',"record provider latency")

    text=translator.read_text(encoding="utf-8")
    text=text.replace("recordTranslationQuality(effectiveAfter, batch, translated);","recordTranslationQuality(videoId, effectiveAfter, batch, translated);")
    text=text.replace("recordTranslationQuality(TRANSLATION_SERVICE_GOOGLE, batch, fallback);","recordTranslationQuality(videoId, TRANSLATION_SERVICE_GOOGLE, batch, fallback);")
    text=text.replace("recordTranslationQuality(effectiveBefore, batch, translated);","recordTranslationQuality(videoId, effectiveBefore, batch, translated);")
    old_sig='''    private static void recordTranslationQuality(String provider,
                                                 List<TranscriptSegment> batch,'''
    if text.count(old_sig)!=1: raise RuntimeError("recordTranslationQuality signature anchor missing")
    text=text.replace(old_sig,'''    private static void recordTranslationQuality(String videoId,
                                                 String provider,
                                                 List<TranscriptSegment> batch,''',1)
    old_record='''            TranslationQualityLog.record(provider, model, globalIndex,
                    seg.startMs, seg.endMs, seg.text, target);'''
    if text.count(old_record)!=1: raise RuntimeError("quality record anchor missing")
    text=text.replace(old_record,old_record+'''
            if (target != null && !target.equals(seg.text)) {
                TranslationProvenanceLog.markReady(videoId, globalIndex, provider, model, "batch-final", target);
            }''',1)
    translator.write_text(text,encoding="utf-8")
    print("v2.15b realtime core/provenance integration complete")


if __name__ == "__main__":
    main()
