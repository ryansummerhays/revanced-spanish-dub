#!/usr/bin/env python3
"""Make startup/resume/seek translation strictly playhead-first, including non-streaming Gemini."""
from pathlib import Path
import sys

def rep(path,old,new,label):
    t=path.read_text(); c=t.count(old)
    if c!=1: raise RuntimeError(f"{label}: expected 1 anchor, found {c}")
    path.write_text(t.replace(old,new,1)); print("patched:",label)

def main():
    root=Path(sys.argv[1]).resolve()
    pkg=root/"extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot=pkg/"VoiceOverTranslationPatch.java"; tr=pkg/"TranscriptTranslator.java"

    # Snapshot the player's real clock before transcript loading starts. This fixes continue-watching
    # and chapter/deep-link starts where newVideoLoaded could launch batch 0 before the next time tick.
    rep(vot,
'''        lastVideoTimeMs = 0;
        lastSpokenIndex = -1;
        wasExplicitSeek = false;''',
'''        lastVideoTimeMs = 0;
        // Current position is more important than transcript order. Seed the translation dispatcher
        // from the actual player clock so opening a 50-minute video at 40:00 does not begin at 0:00.
        videoPositionHint = Math.max(0L, VideoInformation.getVideoTime());
        lastSpokenIndex = -1;
        wasExplicitSeek = false;''',"seed playhead before transcript load")

    # Existing upstream onSeek only reprioritized streaming/OpenRouter requests because only those
    # expose activeConnection. Gemini generateContent is non-streaming, so a seek could not mark its
    # current batch stale. Mark reprioritize for every translator; disconnect only when possible.
    rep(tr,
'''    static void onSeek(long timeMs) {
        if (activeConnection == null) return; // Only an in-flight streaming request can be cut.
        pendingSeekTimeMs = timeMs;
        seekHandler.removeCallbacks(seekCutter);
        seekHandler.postDelayed(seekCutter, SEEK_DEBOUNCE_MS);
    }''',
'''    static void onSeek(long timeMs) {
        pendingSeekTimeMs = timeMs;
        seekHandler.removeCallbacks(seekCutter);
        seekHandler.postDelayed(seekCutter, SEEK_DEBOUNCE_MS);
    }''',"reprioritize non-streaming Gemini seeks")

    rep(tr,
'''    private static void applySeekCut() {
        HttpURLConnection conn = activeConnection;
        if (conn == null) return;
        List<List<TranscriptSegment>> batches = liveBatches;''',
'''    private static void applySeekCut() {
        HttpURLConnection conn = activeConnection;
        List<List<TranscriptSegment>> batches = liveBatches;''',"evaluate seek even without streaming connection")

    rep(tr,
'''        reprioritize = true;
        conn.disconnect();''',
'''        reprioritize = true;
        // Streaming requests can be cut immediately. Non-streaming Gemini cannot be interrupted
        // through this upstream connection field, but its result is discarded as soon as it returns
        // and the dispatcher re-picks the batch under the current playhead.
        if (conn != null) conn.disconnect();''',"discard stale non-streaming batch after seek")

    # Give the first translation dispatch a tiny grace period after transcript fetch so YouTube can
    # publish its restored/deep-link clock. This is far cheaper than translating the wrong 0:00 batch.
    rep(tr,
'''        try {
            while (completed < batchDone.size()) {''',
'''        try {
            // Initial restore/deep-link position can arrive a few frames after newVideoLoaded.
            // A short one-time grace makes the first expensive request target the settled playhead.
            try { Thread.sleep(180L); } catch (InterruptedException ignored) { Thread.currentThread().interrupt(); }
            while (completed < batchDone.size()) {''',"settle initial playhead before first request")

    print("Playhead-first translation priority integration complete")

if __name__=="__main__": main()
