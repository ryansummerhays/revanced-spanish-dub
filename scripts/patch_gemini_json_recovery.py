#!/usr/bin/env python3
"""Prevent a truncated Gemini JSON response from killing the entire Spanish dub.

Device diagnostics showed Gemini returning only the beginning of the first structured-output object,
then JSONObject/JSONArray parsing failed and the Google rescue path immediately hit HTTP 429. This
patch makes the primary Gemini path itself resilient:

* use minimal thinking for this low-latency translation task;
* give structured output a generous token ceiling;
* record finishReason/token usage/text length when JSON is malformed;
* if a multi-event response is malformed or otherwise fails, retry the same requested events in
  tiny 1-event Gemini requests before falling back to Google.

The source IDs/timestamps and all existing alignment/hallucination checks remain unchanged.
"""
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
    if not gemini.is_file():
        raise RuntimeError(f"Required source missing: {gemini}")

    # This request is translation + constrained JSON, not a reasoning task. Gemini 3.5 Flash defaults
    # to medium thinking; on a small maxOutputTokens budget hidden thinking can consume most of the
    # allowance before the visible JSON is complete. Use the lowest supported effort and a large
    # visible-output ceiling so the JSON object can actually finish.
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
                // Translation/JSON emission is a latency-sensitive constrained task. Keep reasoning
                // minimal so hidden thinking cannot consume the visible structured-output budget.
                .put("thinkingConfig", new JSONObject().put("thinkingLevel", "minimal"))
                // A truncated JSON object is unusable. This ceiling is intentionally generous; the
                // schema and requested ID count still bound the actual response size.
                .put("maxOutputTokens", Math.max(4096, (end - start) * 400));''',
        "use minimal thinking and generous structured-output budget")

    # Capture finish reason and usage before JSON parsing. This turns a vague JSONException into an
    # actionable diagnosis and also catches future service-side truncation regressions.
    rep(gemini,
'''        JSONObject content = candidates.getJSONObject(0).optJSONObject("content");
        JSONArray parts = content == null ? null : content.optJSONArray("parts");
        if (parts == null || parts.length() == 0) throw new Exception("Gemini returned no text");

        String jsonText = parts.getJSONObject(0).optString("text", "").trim();
        JSONArray arr = new JSONArray(jsonText);''',
'''        JSONObject candidate = candidates.getJSONObject(0);
        String finishReason = candidate.optString("finishReason", "");
        JSONObject usage = root.optJSONObject("usageMetadata");
        String usageSummary = usage == null ? "" : (" prompt=" + usage.optInt("promptTokenCount", -1)
                + " output=" + usage.optInt("candidatesTokenCount", -1)
                + " thoughts=" + usage.optInt("thoughtsTokenCount", -1)
                + " total=" + usage.optInt("totalTokenCount", -1));
        JSONObject content = candidate.optJSONObject("content");
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
        "diagnose malformed/truncated structured JSON")

    # v2.6.2 already logs the primary failure and then tries Google. Insert a Gemini-first recovery
    # path: retry each requested event independently. This costs more requests only after a failed
    # multi-event response, but avoids total dub failure when Google fallback is rate-limited.
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

            // Do not immediately hand the entire audible region to a public Google-translate
            // fallback that may be rate-limited. First retry Gemini in one-event requests. A single
            // subtitle needs very little structured output and is much harder to truncate; each
            // retry still gets the same global/local context and the same alignment validation.
            try {
                List<String> recovered = new ArrayList<>(segments.size());
                if (start >= 0) {
                    for (int i = 0; i < segments.size(); i++) {
                        recovered.addAll(translateRange(prepared.globalContext, prepared.segments,
                                start + i, start + i + 1, targetLang));
                    }
                } else {
                    String localContext = buildGlobalContext(videoId, segments);
                    for (int i = 0; i < segments.size(); i++) {
                        recovered.addAll(translateRange(localContext, segments, i, i + 1, targetLang));
                    }
                }
                if (recovered.size() == segments.size()) {
                    SpanishStudyDiagnostics.record("GEMINI", "single-event recovery succeeded outputs="
                            + recovered.size());
                    return recovered;
                }
                throw new Exception("Gemini recovery count mismatch " + recovered.size()
                        + "/" + segments.size());
            } catch (Exception retryError) {
                SpanishStudyDiagnostics.record("GEMINI", "single-event recovery failed "
                        + retryError.getClass().getSimpleName() + ": "
                        + safeDiagnostic(retryError.getMessage()));
            }

            Logger.printDebug(() -> "Gemini batch/recovery failed; using Google fallback: "
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
        "recover failed Gemini batches with one-event Gemini retries")

    print("Gemini structured JSON truncation recovery integration complete")


if __name__ == "__main__":
    main()
