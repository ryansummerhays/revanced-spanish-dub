#!/usr/bin/env python3
"""Harden Gemini structured output and keep long-video translation alive across quota hiccups."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_gemini_json_recovery.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    gemini = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/GeminiTranslator.java"
    tr = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"

    rep(gemini,
'''        JSONObject generationConfig = new JSONObject()
                .put("responseMimeType", "application/json")
                .put("responseJsonSchema", arraySchema)
                // Gemini 3.5 uses its own effort defaults; temperature is unnecessary here and
                // Google recommends removing the legacy sampling knobs during 3.5 migration.
                .put("maxOutputTokens", Math.max(900, (end - start) * 150));''',
'''        JSONObject generationConfig = new JSONObject()
                .put("responseMimeType", "application/json")
                .put("responseJsonSchema", arraySchema)
                .put("thinkingConfig", new JSONObject().put("thinkingLevel", "minimal"))
                .put("maxOutputTokens", Math.max(4096, (end - start) * 400));''',
        "use minimal thinking and generous structured-output budget")

    rep(gemini,
'''        JSONObject content = candidates.getJSONObject(0).optJSONObject("content");
        JSONArray parts = content == null ? null : content.optJSONArray("parts");
        if (parts == null || parts.length() == 0) throw new Exception("Gemini returned no text");

        String jsonText = parts.getJSONObject(0).optString("text", "").trim();
        JSONArray arr = new JSONArray(jsonText);''',
'''        JSONObject responseCandidate = candidates.getJSONObject(0);
        String finishReason = responseCandidate.optString("finishReason", "");
        JSONObject usage = root.optJSONObject("usageMetadata");
        String usageSummary = usage == null ? "" : (" prompt=" + usage.optInt("promptTokenCount", -1)
                + " output=" + usage.optInt("candidatesTokenCount", -1)
                + " thoughts=" + usage.optInt("thoughtsTokenCount", -1)
                + " total=" + usage.optInt("totalTokenCount", -1));
        JSONObject content = responseCandidate.optJSONObject("content");
        JSONArray parts = content == null ? null : content.optJSONArray("parts");
        if (parts == null || parts.length() == 0) {
            throw new Exception("Gemini returned no text finish=" + finishReason + usageSummary);
        }
        String jsonText = parts.getJSONObject(0).optString("text", "").trim();
        final JSONArray arr;
        try {
            arr = new JSONArray(jsonText);
        } catch (org.json.JSONException malformed) {
            SpanishStudyDiagnostics.record("GEMINI", "malformed structured JSON finish="
                    + finishReason + " chars=" + jsonText.length() + usageSummary);
            throw new Exception("Gemini structured JSON incomplete finish=" + finishReason
                    + " chars=" + jsonText.length() + usageSummary, malformed);
        }''',
        "diagnose malformed structured JSON")

    rep(gemini,
'''        } catch (Exception ex) {
            SpanishStudyDiagnostics.record("GEMINI", "primary failed model="
                    + SpanishStudyPrefs.geminiModel(Utils.getContext()) + " "
                    + ex.getClass().getSimpleName() + ": " + safeDiagnostic(ex.getMessage()));
            Logger.printDebug(() -> "Gemini batch failed; using Google fallback: "
                    + ex.getClass().getSimpleName() + ": " + ex.getMessage());
            try {
                List<String> fallback=translateFallback(segments,targetLang);
                SpanishStudyDiagnostics.record("FALLBACK", "Google text fallback returned outputs="
                        + (fallback==null?-1:fallback.size()));
                return fallback;
            } catch(Exception fallbackError){
                SpanishStudyDiagnostics.record("FALLBACK", "Google text fallback failed "
                        + fallbackError.getClass().getSimpleName() + ": "
                        + safeDiagnostic(fallbackError.getMessage()));
                throw fallbackError;
            }
        }''',
'''        } catch (Exception ex) {
            SpanishStudyDiagnostics.record("GEMINI", "primary failed model="
                    + SpanishStudyPrefs.geminiModel(Utils.getContext()) + " "
                    + ex.getClass().getSimpleName() + ": " + safeDiagnostic(ex.getMessage()));
            final String primaryMessage = ex.getMessage() == null ? "" : ex.getMessage();
            final boolean primaryRateLimited = primaryMessage.contains("429")
                    || primaryMessage.toLowerCase(java.util.Locale.ROOT).contains("quota");
            if (!primaryRateLimited) {
                try {
                    List<String> recovered = new ArrayList<>(segments.size());
                    if (start >= 0) {
                        for (int i = 0; i < segments.size(); i++)
                            recovered.addAll(translateRange(prepared.globalContext, prepared.segments,
                                    start + i, start + i + 1, targetLang));
                    } else {
                        String localContext = buildGlobalContext(videoId, segments);
                        for (int i = 0; i < segments.size(); i++)
                            recovered.addAll(translateRange(localContext, segments, i, i + 1, targetLang));
                    }
                    if (recovered.size() == segments.size()) {
                        SpanishStudyDiagnostics.record("GEMINI", "single-event recovery succeeded outputs=" + recovered.size());
                        return recovered;
                    }
                } catch (Exception retryError) {
                    SpanishStudyDiagnostics.record("GEMINI", "single-event recovery failed "
                            + retryError.getClass().getSimpleName() + ": " + safeDiagnostic(retryError.getMessage()));
                }
            } else {
                SpanishStudyDiagnostics.record("GEMINI", "rate limited; deferring retry instead of bursting");
            }
            try {
                List<String> fallback=translateFallback(segments,targetLang);
                SpanishStudyDiagnostics.record("FALLBACK", "Google text fallback returned outputs="
                        + (fallback==null?-1:fallback.size()));
                return fallback;
            } catch(Exception fallbackError){
                SpanishStudyDiagnostics.record("FALLBACK", "Google text fallback failed "
                        + fallbackError.getClass().getSimpleName() + ": " + safeDiagnostic(fallbackError.getMessage()));
                throw fallbackError;
            }
        }''',
        "recover malformed batches without retry burst on quota limit")

    rep(tr,
'''    private static final long SEEK_DEBOUNCE_MS = 350;
    private static final Handler seekHandler = new Handler(Looper.getMainLooper());''',
'''    private static final long SEEK_DEBOUNCE_MS = 350;
    private static final long GEMINI_TRANSLATION_HORIZON_MS = 120_000L;
    private static final int GEMINI_INTER_BATCH_DELAY_MS = 6_000;
    private static final int GEMINI_RETRY_MIN_MS = 5_000;
    private static final int GEMINI_RETRY_MAX_MS = 60_000;
    private static final Handler seekHandler = new Handler(Looper.getMainLooper());''',
        "add rolling Gemini horizon and retry constants")

    rep(tr,
'''        final int batchDelay = isGemini ? 0
                : isMyMemory ? MYMEMORY_INTER_BATCH_DELAY_MS
                : isOpenRouter ? OPENROUTER_INTER_BATCH_DELAY_MS
                  : GOOGLE_INTER_BATCH_DELAY_MS;''',
'''        final int batchDelay = isGemini ? GEMINI_INTER_BATCH_DELAY_MS
                : isMyMemory ? MYMEMORY_INTER_BATCH_DELAY_MS
                : isOpenRouter ? OPENROUTER_INTER_BATCH_DELAY_MS
                  : GOOGLE_INTER_BATCH_DELAY_MS;''',
        "pace successful Gemini batches")

    rep(tr,
'''        boolean firstBatchAfterReposition = true;

        try {
            // Initial restore/deep-link position can arrive a few frames after newVideoLoaded.''',
'''        boolean firstBatchAfterReposition = true;
        int geminiRetryBackoffMs = GEMINI_RETRY_MIN_MS;

        try {
            // Initial restore/deep-link position can arrive a few frames after newVideoLoaded.''',
        "add Gemini retry backoff")

    rep(tr,
'''                firstBatchAfterReposition = false;

                List<TranscriptSegment> batch = batches.get(index);''',
'''                firstBatchAfterReposition = false;

                if (isGemini) {
                    List<TranscriptSegment> candidateBatch = batches.get(index);
                    if (!candidateBatch.isEmpty()
                            && candidateBatch.get(0).startMs > timeMs + GEMINI_TRANSLATION_HORIZON_MS) {
                        try { Thread.sleep(750L); }
                        catch (InterruptedException e) { Thread.currentThread().interrupt(); return initial; }
                        continue;
                    }
                }

                List<TranscriptSegment> batch = batches.get(index);''',
        "hold far-future Gemini generation until playhead approaches")

    rep(tr,
'''                if (abortTranslation) break;

                applyBatch(working, batch, offset, translated, targetLang);''',
'''                if (abortTranslation) break;

                if (translated == null && isGemini) {
                    final int waitMs = geminiRetryBackoffMs;
                    SpanishStudyDiagnostics.record("GEMINI", "batch deferred; retry in " + waitMs
                            + "ms index=" + index + " playhead=" + VoiceOverTranslationPatch.videoPositionHint);
                    try { Thread.sleep(waitMs); }
                    catch (InterruptedException e) { Thread.currentThread().interrupt(); return initial; }
                    geminiRetryBackoffMs = Math.min(GEMINI_RETRY_MAX_MS, geminiRetryBackoffMs * 2);
                    firstBatchAfterReposition = true;
                    continue;
                }
                if (translated != null && isGemini) geminiRetryBackoffMs = GEMINI_RETRY_MIN_MS;

                applyBatch(working, batch, offset, translated, targetLang);''',
        "retry transient Gemini failure without marking batch done")

    rep(tr,
'''            if (ex instanceof FileNotFoundException
                    || (msg != null && (msg.contains("402") || msg.contains("429") || msg.contains("401") || msg.contains("403")))) {
                abortTranslation = true;
            }''',
'''            if (ex instanceof FileNotFoundException
                    || (msg != null && (msg.contains("402") || msg.contains("401") || msg.contains("403")
                    || (msg.contains("429") && !GeminiTranslator.isEnabled())))) {
                abortTranslation = true;
            }''',
        "keep Gemini 429 retryable")

    print("Gemini structured JSON and rolling quota recovery integration complete")


if __name__ == "__main__":
    main()
