#!/usr/bin/env python3
"""v2.15.1: strict OpenRouter alignment, usage/cost telemetry, and recoverable provider fallback."""
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
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2151_provider_resilience.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = pkg / "TranscriptTranslator.java"
    controller = study / "SpanishStudyController.java"
    for p in (translator, controller):
        if not p.is_file():
            raise RuntimeError(f"missing required source: {p}")

    insert_after(translator,
                 "import app.spanishstudy.vot.VideoTranslationContext;\n",
                 "import app.spanishstudy.vot.OpenRouterOutputGuard;\n"
                 "import app.spanishstudy.vot.OpenRouterTelemetry;\n"
                 "import app.spanishstudy.vot.ProviderResiliencePolicy;\n",
                 "import v2.15.1 OpenRouter guards/telemetry")

    insert_after(translator,
        "    private static final AtomicInteger openRouterHttpRequestSerial = new AtomicInteger();\n",
        "    private static volatile long googleFallbackBlockedUntilMs;\n",
        "add Google fallback 429 circuit")

    rep(translator,
        '''            joined.append(i + 1).append(" [slot=")
                    .append(String.format(Locale.ROOT, "%.2fs", slotSeconds))
                    .append("]: ").append(input.text);''',
        '''            joined.append(i + 1).append(": [slot=")
                    .append(String.format(Locale.ROOT, "%.2fs", slotSeconds))
                    .append("] ").append(input.text);''',
        "make OpenRouter input numbering parser-compatible")

    rep(translator,
        '''                + "Return ONLY one Spanish line per input, prefixed with the original line number and a colon. Do not merge, skip, explain, or output corrected English."''',
        '''                + "The [slot=...] token is input metadata only. Never copy [slot], millisecond timestamp ranges, >> markers, or reference-context labels into the answer. "
                + "Return ONLY one Spanish line per input, prefixed with the original line number and a colon. Do not merge, skip, explain, or output corrected English."''',
        "forbid context/timing metadata echoes")

    rep(translator,
        '''                .put("stream", true)
                .put("max_tokens", segments.size() * 30)''',
        '''                .put("stream", true)
                .put("usage", new JSONObject().put("include", true))
                .put("max_tokens", segments.size() * 30)''',
        "request exact OpenRouter usage accounting")

    rep(translator,
        '''        conn.setRequestProperty("Content-Type", "application/json");
        conn.setRequestProperty("Authorization", "Bearer " + apiKey);
        conn.setRequestProperty("Accept-Encoding", "identity");
        conn.setDoOutput(true);''',
        '''        conn.setRequestProperty("Content-Type", "application/json");
        conn.setRequestProperty("Authorization", "Bearer " + apiKey);
        conn.setRequestProperty("Accept-Encoding", "identity");
        conn.setRequestProperty("X-OpenRouter-Metadata", "enabled");
        conn.setDoOutput(true);''',
        "enable OpenRouter router metadata")

    old_parse = '''    private static boolean parseLine(String line, List<String> result, int segmentCount) {
        int i = 0;
        while (i < line.length() && Character.isDigit(line.charAt(i))) i++;
        if (i == 0 || i >= line.length()) return false;
        final char sep = line.charAt(i);
        if (sep != ':' && sep != '.' && sep != ')') return false;
        try {
            final int num = Integer.parseInt(line.substring(0, i));
            String text = line.substring(i + 1).trim();
            if (num >= 1 && num <= segmentCount && !text.isEmpty()) {
                result.set(num - 1, text);
                return true;
            }
        } catch (NumberFormatException ex) {
            Logger.printDebug(() -> "Invalid line number: " + line, ex);
        }
        return false;
    }
'''
    new_parse = '''    private static boolean parseLine(String line, List<String> result, int segmentCount) {
        OpenRouterOutputGuard.ParsedLine parsed = OpenRouterOutputGuard.parseNumberedLine(line, segmentCount);
        if (parsed == null) return false;
        result.set(parsed.index, parsed.text);
        return true;
    }
'''
    rep(translator, old_parse, new_parse, "guard numbered OpenRouter output")

    old_apply = '''    private static boolean applyStreamedLine(String line, List<String> result, int segmentCount, int[] matched) {
        if (parseLine(line, result, segmentCount)) {
            matched[0]++;
            return true;
        }
        return false;
    }
'''
    new_apply = '''    private static boolean applyStreamedLine(String line, List<String> result, int segmentCount,
                                             int[] matched, boolean[] matchedSlots) {
        OpenRouterOutputGuard.ParsedLine parsed = OpenRouterOutputGuard.parseNumberedLine(line, segmentCount);
        if (parsed == null) return false;
        result.set(parsed.index, parsed.text);
        if (!matchedSlots[parsed.index]) {
            matchedSlots[parsed.index] = true;
            matched[0]++;
        }
        return true;
    }
'''
    rep(translator, old_apply, new_apply, "count unique OpenRouter output slots")

    rep(translator,
        '''        int[] matched = {0};
        // Full raw model output, kept so a positional fallback can run if numbered parsing fails.''',
        '''        int[] matched = {0};
        boolean[] matchedSlots = new boolean[segments.size()];
        // Full raw model output, kept so a positional fallback can run if numbered parsing fails.''',
        "track unique OpenRouter slots")
    rep(translator,
        '''applyStreamedLine(line, result, segments.size(), matched)''',
        '''applyStreamedLine(line, result, segments.size(), matched, matchedSlots)''',
        "pass unique-slot state to streamed parser", count=2)

    old_positional = '''    @Nullable
    private static List<String> positionalFallback(String raw, int segmentCount) {
        List<String> lines = new ArrayList<>(segmentCount);
        for (String line : raw.split("\\n")) {
            String trimmed = line.trim();
            if (trimmed.isEmpty()) continue;
            lines.add(stripNumberPrefix(trimmed));
        }
        return lines.size() == segmentCount ? lines : null;
    }
'''
    new_positional = '''    @Nullable
    private static List<String> positionalFallback(String raw, int segmentCount) {
        return OpenRouterOutputGuard.positionalFallback(raw, segmentCount);
    }
'''
    rep(translator, old_positional, new_positional, "guard positional OpenRouter recovery")

    rep(translator,
        '''                for (int i = 0; i < segmentSize; i++) result.set(i, positional.get(i));
                matched[0] = segmentSize;''',
        '''                for (int i = 0; i < segmentSize; i++) result.set(i, positional.get(i));
                Arrays.fill(matchedSlots, true);
                matched[0] = segmentSize;''',
        "mark positional OpenRouter recovery fully aligned")

    rep(translator,
        '''        SpanishStudyDiagnostics.record("OPENROUTER-REQ", "start id=" + requestId
                + " events=" + segments.size() + " contextChars=" + videoContext.length()
                + " model=" + model);''',
        '''        OpenRouterTelemetry.recordRequestStart();
        SpanishStudyDiagnostics.record("OPENROUTER-REQ", "start id=" + requestId
                + " events=" + segments.size() + " contextChars=" + videoContext.length()
                + " model=" + model);''',
        "count OpenRouter requests")

    rep(translator,
        '''        activeConnections.add(conn);
        try {
            final int code = conn.getResponseCode();''',
        '''        int responseStatus = -1;
        String generationId = "-";
        String routedProvider = "-";
        String finishReason = "-";
        long usagePromptTokens = -1L;
        long usageCompletionTokens = -1L;
        long usageTotalTokens = -1L;
        long usageCachedTokens = -1L;
        long usageReasoningTokens = -1L;
        double usageCostUsd = Double.NaN;

        activeConnections.add(conn);
        try {
            responseStatus = conn.getResponseCode();
            final int code = responseStatus;
            String headerGeneration = conn.getHeaderField("X-Generation-Id");
            if (headerGeneration != null && !headerGeneration.trim().isEmpty()) {
                generationId = headerGeneration.trim();
            }''',
        "prepare OpenRouter response telemetry")

    chunk_anchor = '''                    JSONArray choices = chunk.optJSONArray("choices");
                    if (choices == null || choices.length() == 0) continue;
                    JSONObject delta = choices.getJSONObject(0).optJSONObject("delta");
                    if (delta == null) continue;
'''
    chunk_new = '''                    String chunkGeneration = chunk.optString("id", "");
                    if (!chunkGeneration.isEmpty()) generationId = chunkGeneration;
                    String chunkProvider = chunk.optString("provider", "");
                    if (!chunkProvider.isEmpty()) routedProvider = chunkProvider;
                    JSONObject usage = chunk.optJSONObject("usage");
                    if (usage != null) {
                        usagePromptTokens = usage.optLong("prompt_tokens", usage.optLong("promptTokens", -1L));
                        usageCompletionTokens = usage.optLong("completion_tokens", usage.optLong("completionTokens", -1L));
                        usageTotalTokens = usage.optLong("total_tokens", usage.optLong("totalTokens", -1L));
                        usageCostUsd = usage.optDouble("cost", Double.NaN);
                        JSONObject promptDetails = usage.optJSONObject("prompt_tokens_details");
                        if (promptDetails == null) promptDetails = usage.optJSONObject("promptTokensDetails");
                        if (promptDetails != null) {
                            usageCachedTokens = promptDetails.optLong("cached_tokens",
                                    promptDetails.optLong("cachedTokens", -1L));
                        }
                        JSONObject completionDetails = usage.optJSONObject("completion_tokens_details");
                        if (completionDetails == null) completionDetails = usage.optJSONObject("completionTokensDetails");
                        if (completionDetails != null) {
                            usageReasoningTokens = completionDetails.optLong("reasoning_tokens",
                                    completionDetails.optLong("reasoningTokens", -1L));
                        }
                    }
                    JSONObject routeMetadata = chunk.optJSONObject("openrouter_metadata");
                    if (routeMetadata != null) {
                        String selectedRouteProvider = "";
                        JSONObject endpoints = routeMetadata.optJSONObject("endpoints");
                        if (endpoints != null) {
                            JSONArray available = endpoints.optJSONArray("available");
                            if (available != null) {
                                for (int ri = 0; ri < available.length(); ri++) {
                                    JSONObject endpoint = available.optJSONObject(ri);
                                    if (endpoint != null && endpoint.optBoolean("selected", false)) {
                                        selectedRouteProvider = endpoint.optString("provider", "");
                                        break;
                                    }
                                }
                            }
                        }
                        StringBuilder attemptSummary = new StringBuilder();
                        JSONArray attempts = routeMetadata.optJSONArray("attempts");
                        if (attempts != null) {
                            for (int ai = 0; ai < attempts.length(); ai++) {
                                JSONObject attempt = attempts.optJSONObject(ai);
                                if (attempt == null) continue;
                                if (attemptSummary.length() > 0) attemptSummary.append(',');
                                attemptSummary.append(attempt.optString("provider", "?"))
                                        .append(':').append(attempt.optInt("status", 0));
                            }
                        }
                        if (!selectedRouteProvider.isEmpty()) routedProvider = selectedRouteProvider;
                        OpenRouterTelemetry.recordRouterMetadata(
                                routeMetadata.optString("strategy", ""),
                                routeMetadata.optString("region", ""),
                                routeMetadata.optInt("attempt", 0),
                                routeMetadata.optString("summary", ""),
                                selectedRouteProvider,
                                attemptSummary.toString());
                    }

                    JSONArray choices = chunk.optJSONArray("choices");
                    if (choices == null || choices.length() == 0) continue;
                    JSONObject choice = choices.getJSONObject(0);
                    String chunkFinish = choice.optString("finish_reason", choice.optString("finishReason", ""));
                    if (!chunkFinish.isEmpty() && !"null".equals(chunkFinish)) finishReason = chunkFinish;
                    JSONObject delta = choice.optJSONObject("delta");
                    if (delta == null) continue;
'''
    rep(translator, chunk_anchor, chunk_new, "parse OpenRouter usage/router/final reason")

    rep(translator,
        '''        } finally {
            activeConnections.remove(conn);
        }

        final int segmentSize = segments.size();''',
        '''        } catch (Exception ex) {
            OpenRouterTelemetry.recordFailure(responseStatus,
                    System.currentTimeMillis() - start,
                    ex.getClass().getSimpleName() + ": " + ex.getMessage());
            throw ex;
        } finally {
            activeConnections.remove(conn);
        }

        final int segmentSize = segments.size();''',
        "record OpenRouter HTTP/network failures")

    old_finish = '''        final int matchedFirst = matched[0];
        Logger.printDebug(() -> "OpenRouter translation complete: " + targetLang
                + " fetchTime: " + (System.currentTimeMillis() - start) + "ms");
        SpanishStudyDiagnostics.record("OPENROUTER-REQ", "done id=" + requestId
                + " elapsedMs=" + (System.currentTimeMillis() - start)
                + " matched=" + matchedFirst + "/" + segmentSize);

        if (matchedFirst != segmentSize) {
            Logger.printDebug(() -> "OpenRouter line mismatch - expected: " + segmentSize
                    + ", got: " + matchedFirst + "; last: " + (segmentSize - matchedFirst)
                    + " segment(s) queued for retry");
            if (matchedFirst > 0) {
                // Return only the translated portion; the caller re-queues the tail for retry.
                return new ArrayList<>(result.subList(0, matchedFirst));
            }
        }
        return result;'''
    new_finish = '''        final int uniqueMatched = Math.max(0, Math.min(matched[0], segmentSize));
        int contiguousCount = 0;
        while (contiguousCount < segmentSize && matchedSlots[contiguousCount]) contiguousCount++;
        final int matchedFirst = contiguousCount;
        if (uniqueMatched != segmentSize || matchedFirst != segmentSize) {
            OpenRouterTelemetry.recordCardinalityMismatch(segmentSize, uniqueMatched);
            SpanishStudyDiagnostics.record("OPENROUTER-PARSE", "alignment id=" + requestId
                    + " expected=" + segmentSize + " unique=" + uniqueMatched
                    + " contiguous=" + matchedFirst);
        }
        OpenRouterTelemetry.recordSuccess(responseStatus, System.currentTimeMillis() - start,
                routedProvider, generationId, finishReason,
                usagePromptTokens, usageCompletionTokens, usageTotalTokens,
                usageCachedTokens, usageReasoningTokens, usageCostUsd);
        Logger.printDebug(() -> "OpenRouter translation complete: " + targetLang
                + " fetchTime: " + (System.currentTimeMillis() - start) + "ms");
        SpanishStudyDiagnostics.record("OPENROUTER-REQ", "done id=" + requestId
                + " elapsedMs=" + (System.currentTimeMillis() - start)
                + " matched=" + matchedFirst + "/" + segmentSize
                + " unique=" + uniqueMatched + " provider=" + routedProvider
                + " cost=" + usageCostUsd);

        if (matchedFirst != segmentSize) {
            Logger.printDebug(() -> "OpenRouter line mismatch - expected: " + segmentSize
                    + ", unique: " + uniqueMatched + ", contiguous: " + matchedFirst
                    + "; last: " + (segmentSize - matchedFirst) + " segment(s) queued for retry");
            if (matchedFirst > 0) {
                // Return only the safely aligned contiguous head; the caller re-queues the tail.
                return new ArrayList<>(result.subList(0, matchedFirst));
            }
            throw new Exception("OpenRouter output alignment mismatch: expected " + segmentSize
                    + " safely aligned lines, got 0 contiguous");
        }
        return result;'''
    rep(translator, old_finish, new_finish, "use contiguous alignment and exact OpenRouter accounting")

    rep(translator,
        '''            return new ArrayList<>();
        } finally {
            pool.shutdownNow();''',
        '''            throw new Exception("OpenRouter parallel output had no contiguous aligned prefix");
        } finally {
            pool.shutdownNow();''',
        "fail malformed empty parallel result into provider fallback")

    old_inner_fallback = '''            final String selectedService = Settings.VOT_TRANSLATION_SERVICE.get();
            if (TranslationProviderPolicy.shouldFallbackToGoogle(
                    selectedService, abortTranslation, reprioritize)) {
                openRouterFallbackToGoogle = true;
                SpanishStudyDiagnostics.record("PROVIDER", "openrouter failed; google fallback events="
                        + batch.size() + " cause=" + ex.getClass().getSimpleName());
                try {
                    return translateBatchGoogle(videoId, batch, targetLang);
                } catch (Exception googleEx) {
                    SpanishStudyDiagnostics.record("PROVIDER", "google fallback failed events="
                            + batch.size() + " cause=" + googleEx.getClass().getSimpleName());
                    ex.addSuppressed(googleEx);
                }
            }
            String msg = ex.getMessage();'''
    new_inner_fallback = '''            final String selectedService = Settings.VOT_TRANSLATION_SERVICE.get();
            if (TRANSLATION_SERVICE_OPENROUTER.equals(selectedService)) {
                SpanishStudyDiagnostics.record("PROVIDER", "openrouter primary failed events="
                        + batch.size() + " cause=" + ex.getClass().getSimpleName());
            }
            String msg = ex.getMessage();'''
    rep(translator, old_inner_fallback, new_inner_fallback, "remove duplicate Google fail-forward")

    # Prior versions changed this catch block several times. Scope the edit to the original safe
    # wrapper and guard the one provider-fatal assignment rather than depending on its formatting.
    text = translator.read_text(encoding="utf-8")
    method_start = text.index("private static List<String> translateBatchSafeOriginal")
    method_end = text.index("\n    private static int findBatchAtTime", method_start)
    method = text[method_start:method_end]
    fatal_anchor = "                abortTranslation = true;"
    if method.count(fatal_anchor) != 1:
        raise RuntimeError("expected one provider-fatal abort assignment in translateBatchSafeOriginal")
    method = method.replace(fatal_anchor,
        '''                if (!TRANSLATION_SERVICE_OPENROUTER.equals(selectedService)) {
                    abortTranslation = true;
                }''', 1)
    translator.write_text(text[:method_start] + method + text[method_end:], encoding="utf-8")
    print("patched: keep OpenRouter provider errors recoverable")

    old_outer_fallback = '''        if (OpenRouterRecoveryPolicy.shouldFallbackToGoogle(
                selected, false, externalAbortRequested, reprioritize)) {
            openRouterFallbackToGoogle = true;
            try {
                List<String> fallback = translateBatchGoogle(videoId, batch, targetLang);
                if (fallback != null && !fallback.isEmpty()) {
                    // A provider-fatal OpenRouter error may have set abortTranslation. The current
                    // session is still wanted, so clear that generic provider-abort after successful
                    // Google recovery. requestAbort() is protected by externalAbortRequested above.
                    abortTranslation = false;
                }
                SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "null-result google fallback outputs="
                        + (fallback == null ? -1 : fallback.size()));
                recordTranslationQuality(videoId, TRANSLATION_SERVICE_GOOGLE, batch, fallback);
                return fallback;
            } catch (Exception fallbackEx) {
                String msg = fallbackEx.getMessage();
                if (msg == null) msg = "";
                msg = msg.replace('\\n', ' ').replace('\\r', ' ');
                if (msg.length() > 180) msg = msg.substring(0, 180);
                final String detail = msg;
                SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "google fallback exception="
                        + fallbackEx.getClass().getSimpleName() + " msg=" + detail);
            }
        }'''
    new_outer_fallback = '''        if (OpenRouterRecoveryPolicy.shouldFallbackToGoogle(
                selected, false, externalAbortRequested, reprioritize)) {
            final long now = System.currentTimeMillis();
            if (now < googleFallbackBlockedUntilMs) {
                SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "google fallback circuit-open remainingMs="
                        + (googleFallbackBlockedUntilMs - now));
            } else {
                OpenRouterTelemetry.recordGoogleFallbackAttempt();
                try {
                    List<String> fallback = translateBatchGoogle(videoId, batch, targetLang);
                    OpenRouterTelemetry.recordGoogleFallbackResult(true, 200);
                    if (fallback != null && !fallback.isEmpty()) abortTranslation = false;
                    openRouterFallbackToGoogle = false;
                    SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "google fallback outputs="
                            + (fallback == null ? -1 : fallback.size()));
                    recordTranslationQuality(videoId, TRANSLATION_SERVICE_GOOGLE, batch, fallback);
                    return fallback;
                } catch (Exception fallbackEx) {
                    final int fallbackStatus = fallbackEx instanceof TextTranslator.TranslationHttpException
                            ? ((TextTranslator.TranslationHttpException) fallbackEx).statusCode : -1;
                    OpenRouterTelemetry.recordGoogleFallbackResult(false, fallbackStatus);
                    final long cooldown = ProviderResiliencePolicy.googleFallbackCooldownMs(fallbackStatus);
                    if (cooldown > 0) googleFallbackBlockedUntilMs = System.currentTimeMillis() + cooldown;
                    openRouterFallbackToGoogle = false;
                    String msg = fallbackEx.getMessage();
                    if (msg == null) msg = "";
                    msg = msg.replace('\\n', ' ').replace('\\r', ' ');
                    if (msg.length() > 180) msg = msg.substring(0, 180);
                    final String detail = msg;
                    SpanishStudyDiagnostics.record("PROVIDER-RUNTIME", "google fallback exception status="
                            + fallbackStatus + " type=" + fallbackEx.getClass().getSimpleName()
                            + " msg=" + detail);
                }
            }
        }'''
    rep(translator, old_outer_fallback, new_outer_fallback, "isolate Google fallback failures")

    rep(translator,
        '''        if (TranslationProviderPolicy.shouldUseOpenRouter(service, openRouterFallbackToGoogle)) {
            return translateBatchOpenRouter(videoId, segments, targetLang, onLineStreamed);
        }
        // A failed OpenRouter session stays on Google until this translate() call finishes.
        return translateBatchGoogle(videoId, segments, targetLang);''',
        '''        if (service.equals(TRANSLATION_SERVICE_OPENROUTER)) {
            return translateBatchOpenRouter(videoId, segments, targetLang, onLineStreamed);
        }
        return translateBatchGoogle(videoId, segments, targetLang);''',
        "always retry the user-selected OpenRouter primary")

    rep(translator,
        '''        int completed = 0;
        // True while the next dispatched batch is the first one after a start or seek.''',
        '''        int completed = 0;
        int consecutiveProviderFailures = 0;
        // True while the next dispatched batch is the first one after a start or seek.''',
        "track recoverable provider failures")

    retry_anchor = '''                applyBatch(working, batch, offset, translated, targetLang);'''
    retry_block = '''                if (translated == null && ProviderResiliencePolicy.shouldRetryOpenRouter(
                        service, externalAbortRequested, reprioritize)) {
                    consecutiveProviderFailures++;
                    final long retryDelay = ProviderResiliencePolicy.retryDelayMs(consecutiveProviderFailures);
                    SpanishStudyDiagnostics.record("PROVIDER-RECOVERY", "retry batch=" + index
                            + " failures=" + consecutiveProviderFailures + " delayMs=" + retryDelay);
                    try {
                        Thread.sleep(retryDelay);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return initial;
                    }
                    continue;
                }
                consecutiveProviderFailures = 0;
''' + retry_anchor
    rep(translator, retry_anchor, retry_block,
        "retry failed OpenRouter batch without killing background translation")

    rep(controller,
        '''        TranslationProvenanceLog.clear();
''',
        '''        TranslationProvenanceLog.clear();
        OpenRouterTelemetry.resetSession();
''',
        "reset OpenRouter telemetry per video")
    rep(controller,
        '''        report.append("translationProvenanceEntries=").append(TranslationProvenanceLog.size()).append('\\n');''',
        '''        report.append("translationProvenanceEntries=").append(TranslationProvenanceLog.size()).append('\\n');
        report.append("providerRecovery=retry-openrouter+single-google-fallback+google-429-circuit\\n");
        report.append(OpenRouterTelemetry.diagnostics());''',
        "append OpenRouter token/cost/provider telemetry")

    text = controller.read_text(encoding="utf-8")
    text = text.replace("Spanish Dub Study v2.15.0 diagnostics", "Spanish Dub Study v2.15.1 diagnostics")
    text = text.replace("providerRuntimeTelemetry=v2.15.0", "providerRuntimeTelemetry=v2.15.1")
    controller.write_text(text, encoding="utf-8")

    print("v2.15.1 provider resilience + OpenRouter accounting integration complete")


if __name__ == "__main__":
    main()
