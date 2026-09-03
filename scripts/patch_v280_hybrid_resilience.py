#!/usr/bin/env python3
"""v2.8: make Gemini an optional enhancement layer over a reliable translation baseline."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def replace_method(path: Path, start_marker: str, end_marker: str, replacement: str, label: str):
    text = path.read_text(encoding="utf-8")
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"{label}: start marker missing in {path}")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"{label}: end marker missing in {path}")
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v280_hybrid_resilience.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    gemini = study / "GeminiTranslator.java"
    grounding = study / "GeminiVideoGrounding.java"
    ground_sidecar = study / "GeminiVideoGroundingSidecar.java"
    speaker = study / "GeminiSpeakerDiarizationSidecar.java"
    controller = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"

    # ---------- Hybrid text translation -------------------------------------------------------
    # Gemini remains the quality layer when healthy, but a quota/timeout no longer means repeated
    # Gemini retries. The circuit opens and batches immediately use cached or Google translation.
    # Successful Gemini and Google results are remembered in a bounded process-memory LRU so seeks
    # and transcript reloads do not spend another request on the same immutable source slot.
    new_translate_batch = r'''    public static List<String> translateBatch(String videoId,
                                              List<TranscriptSegment> segments,
                                              String targetLang) throws Exception {
        if (segments == null || segments.isEmpty()) return new ArrayList<>();

        // Optional audiovisual correction/speaker work remains side-data and can never block this
        // baseline translation path.
        GeminiVideoGroundingSidecar.schedule(videoId, segments, targetLang);

        PreparedTranscript prepared = prepared(videoId, targetLang);
        if (prepared == null) {
            prepareTranscript(videoId, segments, targetLang);
            prepared = prepared(videoId, targetLang);
        }

        Context context = Utils.getContext();
        String model = context == null ? SpanishStudyPrefs.DEFAULT_GEMINI_MODEL
                : SpanishStudyPrefs.geminiModel(context).trim();
        List<String> cachedGemini = HybridTranslationMemory.getGeminiBatch(
                videoId, segments, targetLang, model);
        if (cachedGemini != null) {
            SpanishStudyDiagnostics.record("CACHE", "Gemini translation hit events=" + cachedGemini.size());
            return cachedGemini;
        }

        // When Gemini is resting after a quota/network problem, do not probe it on every subtitle
        // batch. Use a complete cached result if available, otherwise translate through Google's
        // lightweight text endpoint immediately. This keeps Spanish independent from Gemini uptime.
        if (!GeminiResilienceGate.canUseText()) {
            List<String> cached = HybridTranslationMemory.getAnyBatch(videoId, segments, targetLang);
            if (cached != null) {
                SpanishStudyDiagnostics.record("CACHE", "fallback translation hit events=" + cached.size());
                return cached;
            }
            try {
                List<String> fallback = translateFallback(segments, targetLang);
                if (isSafeCacheBatch(segments, fallback, targetLang))
                    HybridTranslationMemory.putGoogleBatch(videoId, segments, targetLang, fallback);
                SpanishStudyDiagnostics.record("HYBRID", "Gemini circuit open; Google baseline outputs="
                        + (fallback == null ? -1 : fallback.size()));
                return fallback;
            } catch (Exception fallbackError) {
                SpanishStudyDiagnostics.record("FALLBACK", "Google baseline failed while Gemini paused "
                        + fallbackError.getClass().getSimpleName() + ": "
                        + safeDiagnostic(fallbackError.getMessage()));
                throw fallbackError;
            }
        }

        if (prepared == null) {
            List<String> fallback = translateFallback(segments, targetLang);
            if (isSafeCacheBatch(segments, fallback, targetLang))
                HybridTranslationMemory.putGoogleBatch(videoId, segments, targetLang, fallback);
            return fallback;
        }

        int start = findBatchStart(prepared.segments, segments);
        try {
            final List<String> result;
            if (start < 0) {
                String localGlobalContext = buildGlobalContext(videoId, segments);
                result = translateRange(localGlobalContext, segments, 0, segments.size(), targetLang);
            } else {
                result = translateRange(prepared.globalContext, prepared.segments,
                        start, start + segments.size(), targetLang);
            }
            if (result == null || result.size() != segments.size())
                throw new Exception("Gemini result count mismatch: expected " + segments.size()
                        + " got " + (result == null ? -1 : result.size()));

            GeminiResilienceGate.recordTextSuccess();
            if (isSafeCacheBatch(segments, result, targetLang))
                HybridTranslationMemory.putGeminiBatch(videoId, segments, targetLang, model, result);
            return result;
        } catch (Exception ex) {
            GeminiResilienceGate.recordTextFailure(ex);
            SpanishStudyDiagnostics.record("GEMINI", "optional enhancement failed model=" + model + " "
                    + ex.getClass().getSimpleName() + ": " + safeDiagnostic(ex.getMessage()));

            // v2.8 intentionally removed the old N-per-caption Gemini recovery burst. A malformed
            // or rate-limited enhancement simply degrades to the baseline translator for this batch.
            List<String> cached = HybridTranslationMemory.getAnyBatch(videoId, segments, targetLang);
            if (cached != null) {
                SpanishStudyDiagnostics.record("CACHE", "using remembered translation after Gemini failure events="
                        + cached.size());
                return cached;
            }
            try {
                List<String> fallback = translateFallback(segments, targetLang);
                if (isSafeCacheBatch(segments, fallback, targetLang))
                    HybridTranslationMemory.putGoogleBatch(videoId, segments, targetLang, fallback);
                SpanishStudyDiagnostics.record("FALLBACK", "Google baseline returned outputs="
                        + (fallback == null ? -1 : fallback.size()));
                return fallback;
            } catch (Exception fallbackError) {
                SpanishStudyDiagnostics.record("FALLBACK", "Google baseline failed "
                        + fallbackError.getClass().getSimpleName() + ": "
                        + safeDiagnostic(fallbackError.getMessage()));
                throw fallbackError;
            }
        }
    }

    private static boolean isSafeCacheBatch(List<TranscriptSegment> segments,
                                            List<String> translated,
                                            String targetLang) {
        if (segments == null || translated == null || segments.size() != translated.size()) return false;
        if (targetLang == null || !targetLang.toLowerCase(Locale.ROOT).startsWith("es")) return true;
        for (int i = 0; i < segments.size(); i++) {
            String source = segments.get(i) == null ? "" : segments.get(i).text;
            String target = translated.get(i);
            if (!TranslationAlignmentGuard.isSafeSpanishTranslation(source, target)) return false;
        }
        return true;
    }

'''
    replace_method(
        gemini,
        "    public static List<String> translateBatch(String videoId,",
        "    private static List<String> translateFallback",
        new_translate_batch,
        "replace bursty Gemini-primary batch path with hybrid/cached path",
    )

    # Slow the optional Gemini quality layer enough to leave quota headroom for media/speaker calls.
    rep(translator,
        "    private static final long GEMINI_TRANSLATION_HORIZON_MS = 120_000L;\n    private static final int GEMINI_INTER_BATCH_DELAY_MS = 6_000;",
        "    private static final long GEMINI_TRANSLATION_HORIZON_MS = 90_000L;\n    private static final int GEMINI_INTER_BATCH_DELAY_MS = 12_000;",
        "conserve Gemini text quota with shorter horizon and slower cadence")

    # The old dispatcher-level retry loop is no longer desirable: translateBatch itself always
    # returns Google/cached Spanish when Gemini is resting. Keep the backoff code harmless, but make
    # the normal returned fallback path complete the batch instead of probing Gemini repeatedly.

    # ---------- Media / speaker circuit --------------------------------------------------------
    rep(ground_sidecar,
'''        if (!SpanishStudyPrefs.geminiEnabled(context)
                || SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty()) return;''',
'''        if (!SpanishStudyPrefs.geminiEnabled(context)
                || SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty()) return;
        if (!GeminiResilienceGate.canUseMedia()) return;''',
        "skip optional video grounding while Gemini media circuit rests")

    rep(grounding,
'''        if(!targetLang.toLowerCase(Locale.ROOT).startsWith("es"))return null;
        String apiKey=SpanishStudyPrefs.geminiApiKey(context).trim();''',
'''        if(!targetLang.toLowerCase(Locale.ROOT).startsWith("es"))return null;
        if(!GeminiResilienceGate.canUseMedia())return null;
        String apiKey=SpanishStudyPrefs.geminiApiKey(context).trim();''',
        "guard audiovisual grounding with media circuit")

    rep(grounding,
'''            String jsonText=extractText(new JSONObject(response));
            if(jsonText==null||jsonText.isBlank())throw new Exception("Gemini video grounding returned no text");
            return validateAndCommit(segments,targetLang,new JSONObject(jsonText),context);
        }catch(Exception ex){
            Logger.printDebug(()->"Audiovisual Gemini grounding unavailable; falling back to transcript-only Gemini: "
                    +ex.getClass().getSimpleName()+": "+ex.getMessage());
            return null;
        }''',
'''            String jsonText=extractText(new JSONObject(response));
            if(jsonText==null||jsonText.isBlank())throw new Exception("Gemini video grounding returned no text");
            List<String> result=validateAndCommit(segments,targetLang,new JSONObject(jsonText),context);
            GeminiResilienceGate.recordMediaSuccess();
            return result;
        }catch(Exception ex){
            GeminiResilienceGate.recordMediaFailure(ex);
            Logger.printDebug(()->"Audiovisual Gemini grounding unavailable; baseline translation remains active: "
                    +ex.getClass().getSimpleName()+": "+ex.getMessage());
            return null;
        }''',
        "feed audiovisual success/failure into media circuit")

    rep(speaker,
'''        if (!SpanishStudyPrefs.geminiEnabled(context)
                || SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty()) return;''',
'''        if (!SpanishStudyPrefs.geminiEnabled(context)
                || SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty()) return;
        if (!GeminiResilienceGate.canUseMedia()) return;''',
        "skip speaker API while media circuit rests")

    rep(speaker,
'''                    SpeakerAssignmentStore.commitBatch(snapshot, proposals);
                    success = true;
                    SpanishStudyDiagnostics.record("SPEAKER", "window complete profiles="''',
'''                    SpeakerAssignmentStore.commitBatch(snapshot, proposals);
                    GeminiResilienceGate.recordMediaSuccess();
                    success = true;
                    SpanishStudyDiagnostics.record("SPEAKER", "window complete profiles="''',
        "record successful speaker media call")

    rep(speaker,
'''            } catch (Exception ex) {
                SpanishStudyDiagnostics.record("SPEAKER", "sidecar unavailable "
                        + ex.getClass().getSimpleName() + ": " + safe(ex.getMessage()));''',
'''            } catch (Exception ex) {
                GeminiResilienceGate.recordMediaFailure(ex);
                SpanishStudyDiagnostics.record("SPEAKER", "sidecar unavailable "
                        + ex.getClass().getSimpleName() + ": " + safe(ex.getMessage()));''',
        "record failed speaker media call")

    rep(speaker,
'''    static synchronized String status() {
        String base = SpeakerAssignmentStore.profileSummary();
        if (inFlight) return base + " · analyzing";''',
'''    static synchronized String status() {
        String base = SpeakerAssignmentStore.profileSummary();
        if (!GeminiResilienceGate.canUseMedia())
            return base + " · media " + GeminiResilienceGate.mediaStatus();
        if (inFlight) return base + " · analyzing";''',
        "make quota-paused speaker state visible")

    # ---------- Diagnostics / UI ---------------------------------------------------------------
    rep(controller,
'''        report.append("Spanish Dub Study v2.7.1 diagnostics\\n");''',
'''        report.append("Spanish Dub Study v2.8.0 diagnostics\\n");''',
        "label v2.8.0 diagnostics")

    rep(controller,
'''        report.append("speakerProfiles=").append(GeminiSpeakerDiarizationSidecar.status()).append('\\n');
        report.append("matchSourcePace=").append(SpanishStudyPrefs.matchSourcePace(activity)).append('\\n');
        report.append("--- events ---\\n").append(SpanishStudyDiagnostics.dump());''',
'''        report.append("speakerProfiles=").append(GeminiSpeakerDiarizationSidecar.status()).append('\\n');
        report.append("matchSourcePace=").append(SpanishStudyPrefs.matchSourcePace(activity)).append('\\n');
        report.append("geminiTextState=").append(GeminiResilienceGate.textStatus()).append('\\n');
        report.append("geminiMediaState=").append(GeminiResilienceGate.mediaStatus()).append('\\n');
        report.append("translationMemory=").append(HybridTranslationMemory.summary()).append('\\n');
        report.append("--- events ---\\n").append(SpanishStudyDiagnostics.dump());''',
        "show hybrid circuit/cache state in copied diagnostics")

    rep(sheet,
'''        geminiRow.setOnClickListener(v->SpanishStudyController.configureGemini(activity));
        content.addView(geminiRow);''',
'''        geminiRow.setOnClickListener(v->SpanishStudyController.configureGemini(activity));
        content.addView(geminiRow);
        TextView hybridNote=new TextView(activity);
        hybridNote.setText("Gemini is an optional quality layer. If it times out or reaches quota, Spanish automatically uses the Google baseline and remembered in-memory translations; speaker/video analysis rests independently and retries later. No full-video translation cache is written to disk.");
        hybridNote.setTextColor(secondary);
        hybridNote.setTextSize(12);
        hybridNote.setPadding(0,Dim.dp4,0,Dim.dp8);
        content.addView(hybridNote);''',
        "explain Gemini-as-enhancement behavior in settings")

    print("v2.8 hybrid Gemini resilience integration complete")


if __name__ == "__main__":
    main()
