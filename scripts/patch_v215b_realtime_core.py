#!/usr/bin/env python3
"""v2.15.0 realtime core: bounded OpenRouter batching, streamed-slot correctness, provenance."""
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


def regex_once(path: Path, pattern: str, repl: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, found {count} in {path}")
    path.write_text(updated, encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v215b_realtime_core.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = pkg / "TranscriptTranslator.java"
    if not translator.is_file():
        raise RuntimeError(f"missing required source: {translator}")

    insert_after(translator, "import java.util.HashMap;\n", "import java.util.IdentityHashMap;\n",
                 "import IdentityHashMap for active OpenRouter connections")
    insert_after(translator, "import java.util.Map;\n", "import java.util.Set;\n",
                 "import Set for active OpenRouter connections")
    insert_after(translator, "import java.util.concurrent.ExecutionException;\n",
                 "import java.util.concurrent.ExecutorService;\n"
                 "import java.util.concurrent.Executors;\n"
                 "import java.util.concurrent.Future;\n",
                 "import bounded OpenRouter parallel executor")
    insert_after(translator, "import app.spanishstudy.vot.TranslationQualityLog;\n",
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

    rep(translator,
        '''        abortTranslation = true;
        HttpURLConnection conn = activeConnection;
        if (conn != null) conn.disconnect();''',
        '''        abortTranslation = true;
        disconnectActiveConnections();''',
        "abort all concurrent OpenRouter streams")

    # patch_playhead_priority intentionally made seek reprioritization provider-agnostic. Preserve
    # that behavior while replacing only the old singleton streaming connection management.
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

    # Match the semantic first-batch block but deliberately ignore comments inserted by earlier
    # release layers. The following List assignment anchors this to the actual dispatcher body.
    regex_once(
        translator,
        r'''(?P<indent>\s*)if \(firstBatchAfterReposition\) \{\n(?P=indent)    capFirstBatch\(batches, batchDone, index\);\n(?P=indent)\}\n(?P=indent)firstBatchAfterReposition = false;\n(?:[ \t]*//[^\n]*\n)*\n?(?P=indent)List<TranscriptSegment> batch = batches\.get\(index\);''',
        '''\g<indent>if (firstBatchAfterReposition) {\n\g<indent>    capFirstBatch(batches, batchDone, index);\n\g<indent>}\n\g<indent>firstBatchAfterReposition = false;\n\g<indent>if (isOpenRouter) {\n\g<indent>    capRealtimeBatch(batches, batchDone, index);\n\g<indent>}\n\n\g<indent>List<TranscriptSegment> batch = batches.get(index);''',
        "enforce microbatch size on every OpenRouter dispatch")

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

    text = translator.read_text(encoding="utf-8")
    replacements = {
        "recordTranslationQuality(effectiveAfter, batch, translated);":
            "recordTranslationQuality(videoId, effectiveAfter, batch, translated);",
        "recordTranslationQuality(TRANSLATION_SERVICE_GOOGLE, batch, fallback);":
            "recordTranslationQuality(videoId, TRANSLATION_SERVICE_GOOGLE, batch, fallback);",
        "recordTranslationQuality(effectiveBefore, batch, translated);":
            "recordTranslationQuality(videoId, effectiveBefore, batch, translated);",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"translation quality call anchor missing: {old}")
        text = text.replace(old, new)
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
