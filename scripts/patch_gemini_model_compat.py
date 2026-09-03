#!/usr/bin/env python3
"""Make Gemini translation compatible with structured-output model support.

The app historically defaulted to gemini-3.5-flash-lite while the translator requires structured
JSON output. Google currently documents structured-output support for gemini-3.5-flash and
 gemini-3.1-flash-lite, but not 3.5-flash-lite. Existing installs may therefore fail the first
playhead batch immediately, then fall through to a secondary translator that can also fail, leaving
all source-language segments unchanged.

This patch transparently migrates the legacy 3.5-flash-lite preference to 3.5-flash, removes the
unnecessary temperature field for Gemini 3.5, and records the exact Gemini/fallback failure in the
in-app diagnostics trail.
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
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    prefs = study / "SpanishStudyPrefs.java"
    gemini = study / "GeminiTranslator.java"

    rep(prefs,
        '    static final String DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite";\n',
        '    static final String DEFAULT_GEMINI_MODEL = "gemini-3.5-flash";\n',
        "use structured-output-compatible Gemini default")

    rep(prefs,
'''    static String geminiModel(Context c){String v=prefs(c).getString(GEMINI_MODEL,DEFAULT_GEMINI_MODEL);return v==null||v.isBlank()?DEFAULT_GEMINI_MODEL:v;}''',
'''    static String geminiModel(Context c){
        String v=prefs(c).getString(GEMINI_MODEL,DEFAULT_GEMINI_MODEL);
        if(v==null||v.isBlank())return DEFAULT_GEMINI_MODEL;
        // v2.6.2 migration: 3.5 Flash-Lite is not currently listed by Google as supporting the
        // structured-output mode this translator depends on. Existing users may have this saved
        // from older builds, so migrate it transparently rather than requiring a settings reset.
        if("gemini-3.5-flash-lite".equals(v.trim()))return "gemini-3.5-flash";
        return v;
    }''',
        "migrate saved 3.5-flash-lite setting")

    rep(gemini,
'''        } catch (Exception ex) {
            Logger.printDebug(() -> "Gemini batch failed; using Google fallback: "
                    + ex.getClass().getSimpleName() + ": " + ex.getMessage());
            return translateFallback(segments, targetLang);
        }''',
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
        "record Gemini and Google fallback failure details")

    rep(gemini,
'''        JSONObject generationConfig = new JSONObject()
                .put("responseMimeType", "application/json")
                .put("responseJsonSchema", arraySchema)
                .put("temperature", 0.0)
                .put("maxOutputTokens", Math.max(900, (end - start) * 150));''',
'''        JSONObject generationConfig = new JSONObject()
                .put("responseMimeType", "application/json")
                .put("responseJsonSchema", arraySchema)
                // Gemini 3.5 uses its own effort defaults; temperature is unnecessary here and
                // Google recommends removing the legacy sampling knobs during 3.5 migration.
                .put("maxOutputTokens", Math.max(900, (end - start) * 150));''',
        "remove legacy Gemini temperature parameter")

    # Add a small sanitizer for diagnostics; never dump request bodies/API keys/transcript context.
    rep(gemini,
'''    private static boolean containsDigit(String value) {''',
'''    private static String safeDiagnostic(String value) {
        if(value==null)return "";
        String clean=value.replaceAll("\\\\s+"," ").trim();
        return clean.length()<=220?clean:clean.substring(0,220);
    }

    private static boolean containsDigit(String value) {''',
        "add safe Gemini diagnostic formatter")

    print("Gemini structured-output compatibility integration complete")


if __name__ == "__main__":
    main()
