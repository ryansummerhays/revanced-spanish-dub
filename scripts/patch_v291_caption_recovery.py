#!/usr/bin/env python3
"""v2.9.1: harden caption acquisition and expose session/caption failure causes.

This is intentionally applied after v2.9.0. It keeps the v2.9 provider/speaker/TTS architecture
unchanged and fixes the earlier pipeline gate seen when a playable YouTube video returned zero
source caption events.
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
        raise SystemExit("usage: patch_v291_caption_recovery.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    fetcher = votpkg / "TranscriptFetcher.java"
    controller = study / "SpanishStudyController.java"
    vot = votpkg / "VoiceOverTranslationPatch.java"

    # ---- Caption diagnostics import ---------------------------------------------------------
    # patch_bilingual_subtitles already adds SpanishStudyController here.
    rep(fetcher,
'''import app.spanishstudy.vot.SpanishStudyController;
''',
'''import app.spanishstudy.vot.SpanishStudyController;
import app.spanishstudy.vot.SpanishStudyDiagnostics;
''',
        "import caption diagnostics")

    # ---- Make the Innertube player request use the same account/cookie context as caption GETs --
    rep(fetcher,
'''        conn.setRequestProperty("X-YouTube-Client-Name", "3");
        conn.setRequestProperty("X-YouTube-Client-Version", "20.10.38");
        conn.setDoOutput(true);

        try (OutputStream os = conn.getOutputStream()) {''',
'''        conn.setRequestProperty("X-YouTube-Client-Name", "3");
        conn.setRequestProperty("X-YouTube-Client-Version", "20.10.38");

        // Caption downloads already use Morphe's caption cookies and signed account headers. The
        // player request that discovers the caption URL must use the same access context; otherwise
        // a video can play in the signed-in app while this anonymous discovery request sees no track
        // or stalls behind a consent/access boundary.
        String playerCookies = CaptionCookiesPatch.getCookies();
        if (!playerCookies.isEmpty()) conn.setRequestProperty("Cookie", playerCookies);
        Map<String, String> playerAuthHeaders = AuthUtils.getRequestHeader();
        for (Map.Entry<String, String> entry : playerAuthHeaders.entrySet()) {
            if (!entry.getValue().isEmpty()) conn.setRequestProperty(entry.getKey(), entry.getValue());
        }
        conn.setDoOutput(true);

        final long requestStartedMs = System.currentTimeMillis();
        SpanishStudyDiagnostics.record("CAPTION-NET", "innertube player request start");
        try (OutputStream os = conn.getOutputStream()) {''',
        "authenticate Innertube caption discovery")

    rep(fetcher,
'''        final int code = conn.getResponseCode();
        if (code != 200) throw new Exception("Unexpected response status: " + code);

        String response = Requester.parseString(conn);''',
'''        final int code = conn.getResponseCode();
        final long elapsedMs = System.currentTimeMillis() - requestStartedMs;
        SpanishStudyDiagnostics.record("CAPTION-NET", "innertube response=" + code
                + " elapsed=" + elapsedMs + "ms");
        if (code != 200) throw new Exception("Unexpected response status: " + code);

        String response = Requester.parseString(conn);''',
        "record Innertube response timing")

    # patch_video_context inserts metadata extraction immediately before this return; keep it intact
    # and only make the return expose whether a usable caption track was discovered.
    rep(fetcher,
'''        return new String[]{findBestCaptionUrl(response), extractPoToken(response)};''',
'''        String selectedCaptionUrl = findBestCaptionUrl(response);
        SpanishStudyDiagnostics.record("CAPTIONS", selectedCaptionUrl == null
                ? "innertube returned no usable caption track"
                : "innertube selected caption lang=" + extractLangFromUrl(selectedCaptionUrl));
        return new String[]{selectedCaptionUrl, extractPoToken(response)};''',
        "diagnose caption-track selection")

    # ---- Record the exact reason Innertube/caption-URL paths fall through --------------------
    rep(fetcher,
'''        try {
            String[] innertubeResult = fetchFromInnertube(videoId);
            captionUrl = innertubeResult[0];
            poToken    = innertubeResult[1];
        } catch (Exception ex) {
            Logger.printDebug(() -> "Innertube player failed", ex);
        }''',
'''        try {
            String[] innertubeResult = fetchFromInnertube(videoId);
            captionUrl = innertubeResult[0];
            poToken    = innertubeResult[1];
        } catch (Exception ex) {
            SpanishStudyDiagnostics.record("CAPTION-NET", "innertube failed "
                    + ex.getClass().getSimpleName() + ": " + safeCaptionError(ex.getMessage()));
            Logger.printDebug(() -> "Innertube player failed", ex);
        }''',
        "diagnose Innertube exception")

    rep(fetcher,
'''                if (!segments.isEmpty()) {
                    lastSourceLang = detectedLang;
                    return segments;
                }
            } catch (Exception ex) {
                Logger.printDebug(() -> "Caption fetch failed, trying direct", ex);
            }
        }

        return fetchDirect(videoId);''',
'''                if (!segments.isEmpty()) {
                    lastSourceLang = detectedLang;
                    SpanishStudyDiagnostics.record("CAPTIONS", "signed caption URL parsed lang="
                            + detectedLang + " events=" + segments.size());
                    return segments;
                }
                SpanishStudyDiagnostics.record("CAPTIONS", "signed caption URL returned zero parsed events");
            } catch (Exception ex) {
                SpanishStudyDiagnostics.record("CAPTION-NET", "signed caption URL failed "
                        + ex.getClass().getSimpleName() + ": " + safeCaptionError(ex.getMessage()));
                Logger.printDebug(() -> "Caption fetch failed, trying direct", ex);
            }
        }

        SpanishStudyDiagnostics.record("CAPTIONS", "trying direct timedtext recovery");
        return fetchDirect(videoId);''',
        "diagnose caption URL and direct fallback transition")

    # ---- Direct recovery: manual captions AND ASR --------------------------------------------
    # The old fallback always appended kind=asr. That means an Innertube timeout turns a perfectly
    # valid manually-captioned video into an apparent no-caption video. Try both representations.
    old_direct = '''    private static List<TranscriptSegment> fetchDirect(String videoId) {
        for (String srcLang : List.of("en", "en-US", "en-GB")) {
            try {
                String urlStr = "https://www.youtube.com/api/timedtext?v=" + videoId
                        + "&lang=" + srcLang + "&kind=asr&fmt=json3";
                String json = fetchUrl(urlStr);
                if (!json.isEmpty()) {
                    List<TranscriptSegment> segments = parseJson3(json, "en");
                    if (!segments.isEmpty()) {
                        lastSourceLang = "en";
                        return segments;
                    }
                }
            } catch (Exception ex) {
                final String langFinal = srcLang;
                Logger.printDebug(() -> "Direct caption fetch failed lang: " + langFinal, ex);
            }
        }
        Logger.printDebug(() -> "No captions available for video: " + videoId);
        return new ArrayList<>();
    }'''
    new_direct = '''    private static List<TranscriptSegment> fetchDirect(String videoId) {
        for (String srcLang : List.of("en", "en-US", "en-GB")) {
            for (boolean asr : new boolean[]{false, true}) {
                final String mode = asr ? "asr" : "manual";
                try {
                    SpanishStudyDiagnostics.record("CAPTION-NET", "direct " + mode
                            + " request lang=" + srcLang);
                    String urlStr = "https://www.youtube.com/api/timedtext?v=" + videoId
                            + "&lang=" + srcLang + (asr ? "&kind=asr" : "") + "&fmt=json3";
                    final long startedMs = System.currentTimeMillis();
                    String json = fetchUrl(urlStr);
                    final long elapsedMs = System.currentTimeMillis() - startedMs;
                    if (!json.isEmpty()) {
                        List<TranscriptSegment> segments = parseJson3(json, "en");
                        if (!segments.isEmpty()) {
                            lastSourceLang = "en";
                            SpanishStudyDiagnostics.record("CAPTIONS", "direct " + mode
                                    + " recovered lang=" + srcLang + " events=" + segments.size()
                                    + " elapsed=" + elapsedMs + "ms");
                            return segments;
                        }
                        SpanishStudyDiagnostics.record("CAPTION-NET", "direct " + mode
                                + " parsed zero events lang=" + srcLang + " elapsed=" + elapsedMs + "ms");
                    } else {
                        SpanishStudyDiagnostics.record("CAPTION-NET", "direct " + mode
                                + " empty lang=" + srcLang + " elapsed=" + elapsedMs + "ms");
                    }
                } catch (Exception ex) {
                    final String langFinal = srcLang;
                    final String modeFinal = mode;
                    SpanishStudyDiagnostics.record("CAPTION-NET", "direct " + modeFinal
                            + " failed lang=" + langFinal + " " + ex.getClass().getSimpleName()
                            + ": " + safeCaptionError(ex.getMessage()));
                    Logger.printDebug(() -> "Direct caption fetch failed mode=" + modeFinal
                            + " lang=" + langFinal, ex);
                }
            }
        }
        SpanishStudyDiagnostics.record("CAPTIONS", "all caption recovery paths exhausted");
        Logger.printDebug(() -> "No captions available for video: " + videoId);
        return new ArrayList<>();
    }'''
    rep(fetcher, old_direct, new_direct, "recover manual captions when Innertube fails")

    # Small sanitizer for copied diagnostics: never dump signed caption URLs/cookies/tokens.
    rep(fetcher,
'''    private static String fetchUrl(String urlStr) throws Exception {''',
'''    private static String safeCaptionError(String raw) {
        if (raw == null) return "";
        String clean = raw.replaceAll("https?://\\S+", "<url>")
                .replaceAll("\\s+", " ").trim();
        return clean.length() <= 180 ? clean : clean.substring(0, 180);
    }

    private static String fetchUrl(String urlStr) throws Exception {''',
        "sanitize caption diagnostics")

    # ---- Session breadcrumbs ----------------------------------------------------------------
    # v2.9 logs disable events but not re-enables, which makes repeated toggling impossible to
    # distinguish from duplicated callbacks. Record both edges and include the immediate caller.
    rep(controller,
'''    public static void onSessionDisabled(){
        SpanishStudyDiagnostics.record("SESSION", "disabled");
        SpanishSubtitleOverlay.hide();
    }''',
'''    public static void onSessionEnabled(){
        SpanishStudyDiagnostics.record("SESSION", "enabled");
    }

    public static void onSessionDisabled(){
        SpanishStudyDiagnostics.record("SESSION", "disabled caller=" + sessionCaller());
        SpanishSubtitleOverlay.hide();
    }

    private static String sessionCaller(){
        StackTraceElement[] stack=Thread.currentThread().getStackTrace();
        boolean pastDeactivate=false;
        for(StackTraceElement frame:stack){
            String method=frame.getMethodName();
            if("deactivateTranslation".equals(method)){pastDeactivate=true;continue;}
            if(pastDeactivate){
                String cls=frame.getClassName();
                int dot=cls.lastIndexOf('.');
                if(dot>=0)cls=cls.substring(dot+1);
                return cls+"."+method;
            }
        }
        return "unknown";
    }''',
        "diagnose session re-enable and disable caller")

    rep(vot,
'''        sessionEnabled = true;
        Settings.VOT_SESSION_ENABLED.save(true);
        if (!currentVideoId.isEmpty() && segments.isEmpty() && !isLoading) {''',
'''        sessionEnabled = true;
        Settings.VOT_SESSION_ENABLED.save(true);
        SpanishStudyController.onSessionEnabled();
        if (!currentVideoId.isEmpty() && segments.isEmpty() && !isLoading) {''',
        "record session enable edge")

    # ---- Version ----------------------------------------------------------------------------
    rep(controller,
'''        report.append("Spanish Dub Study v2.9.0 diagnostics\\n");''',
'''        report.append("Spanish Dub Study v2.9.1 diagnostics\\n");''',
        "label v2.9.1 diagnostics")

    print("v2.9.1 caption recovery/session diagnostics integration complete")


if __name__ == "__main__":
    main()
