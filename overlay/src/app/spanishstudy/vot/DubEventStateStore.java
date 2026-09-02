package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Makes each translated source slot an atomic dub event.
 *
 * Progressive translation is useful for startup latency, but a slot that already has an accepted
 * target-language translation must never be rewritten underneath subtitles or TTS playback. This
 * store freezes the first accepted target-language segment for each immutable source timestamp and
 * tracks the audio lifecycle separately (translated -> ready -> playing -> done / failed).
 */
public final class DubEventStateStore {
    public enum State { SOURCE, TRANSLATED, READY, PLAYING, DONE, FAILED, SKIPPED }

    private static final int MAX_EVENTS = 5000;
    private static final Map<String, Event> EVENTS =
            new LinkedHashMap<String, Event>(256, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, Event> eldest) {
                    return size() > MAX_EVENTS;
                }
            };

    private DubEventStateStore() {}

    public static synchronized void clear() {
        EVENTS.clear();
    }

    /**
     * Merge one progressive transcript publication while preserving any target-language event that
     * was already accepted. Source-language placeholders are freely replaceable by their translation.
     */
    public static synchronized List<TranscriptSegment> mergeTranslationUpdate(
            List<TranscriptSegment> previous,
            List<TranscriptSegment> incoming,
            String targetLang) {
        if (incoming == null) return previous == null ? new ArrayList<>() : new ArrayList<>(previous);
        List<TranscriptSegment> out = new ArrayList<>(incoming.size());

        for (int i = 0; i < incoming.size(); i++) {
            TranscriptSegment next = incoming.get(i);
            if (next == null) {
                out.add(null);
                continue;
            }
            String key = key(next.startMs, next.endMs);
            Event event = EVENTS.get(key);
            if (event != null && event.committed != null) {
                out.add(event.committed);
                continue;
            }

            TranscriptSegment old = i < (previous == null ? 0 : previous.size()) ? previous.get(i) : null;
            if (sameSlot(old, next) && isTargetLanguage(old, targetLang) && hasText(old)) {
                event = eventFor(old);
                event.committed = old;
                event.state = State.TRANSLATED;
                out.add(old);
                continue;
            }

            if (isTargetLanguage(next, targetLang) && hasText(next)) {
                event = eventFor(next);
                event.committed = next;
                event.state = State.TRANSLATED;
            }
            out.add(next);
        }
        return out;
    }

    public static synchronized void markReady(TranscriptSegment segment, int index, long durationMs) {
        Event event = eventFor(segment);
        event.index = index;
        event.audioDurationMs = Math.max(0L, durationMs);
        if (event.state != State.PLAYING && event.state != State.DONE) event.state = State.READY;
    }

    public static synchronized void markPlaying(TranscriptSegment segment, int index,
                                                long durationMs, float rate) {
        Event event = eventFor(segment);
        event.index = index;
        event.audioDurationMs = Math.max(0L, durationMs);
        event.playbackRate = rate;
        event.state = State.PLAYING;
        event.failures = 0;
    }

    public static synchronized void markDone(TranscriptSegment segment, int index) {
        Event event = eventFor(segment);
        event.index = index;
        event.state = State.DONE;
        event.failures = 0;
    }

    /** @return number of consecutive failures for this immutable event. */
    public static synchronized int markFailure(TranscriptSegment segment, int index) {
        Event event = eventFor(segment);
        event.index = index;
        event.failures++;
        event.state = State.FAILED;
        return event.failures;
    }

    public static synchronized void markSkipped(TranscriptSegment segment, int index) {
        Event event = eventFor(segment);
        event.index = index;
        event.state = State.SKIPPED;
    }

    public static synchronized int failureCount(TranscriptSegment segment) {
        Event event = EVENTS.get(key(segment.startMs, segment.endMs));
        return event == null ? 0 : event.failures;
    }

    /** Compact diagnostic string suitable for debug logs and a future optional overlay. */
    public static synchronized String diagnostic(TranscriptSegment segment) {
        if (segment == null) return "no-event";
        Event event = EVENTS.get(key(segment.startMs, segment.endMs));
        if (event == null) return "source";
        return "#" + event.index + " " + event.state
                + (event.audioDurationMs > 0 ? " audio=" + event.audioDurationMs + "ms" : "")
                + (event.playbackRate > 0f ? " rate=" + String.format(Locale.ROOT, "%.2fx", event.playbackRate) : "")
                + (event.failures > 0 ? " failures=" + event.failures : "");
    }

    private static Event eventFor(TranscriptSegment segment) {
        if (segment == null) throw new IllegalArgumentException("segment == null");
        String key = key(segment.startMs, segment.endMs);
        Event event = EVENTS.get(key);
        if (event == null) {
            event = new Event();
            event.state = State.SOURCE;
            EVENTS.put(key, event);
        }
        return event;
    }

    private static boolean sameSlot(TranscriptSegment a, TranscriptSegment b) {
        return a != null && b != null && a.startMs == b.startMs && a.endMs == b.endMs;
    }

    private static boolean hasText(TranscriptSegment segment) {
        return segment != null && segment.text != null && !segment.text.isBlank();
    }

    private static boolean isTargetLanguage(TranscriptSegment segment, String targetLang) {
        if (segment == null || segment.lang == null || targetLang == null) return false;
        String a = baseLang(segment.lang);
        String b = baseLang(targetLang);
        return !a.isEmpty() && a.equals(b);
    }

    private static String baseLang(String lang) {
        if (lang == null) return "";
        String value = lang.toLowerCase(Locale.ROOT).trim();
        int dash = value.indexOf('-');
        return dash < 0 ? value : value.substring(0, dash);
    }

    private static String key(long startMs, long endMs) {
        return startMs + ":" + endMs;
    }

    private static final class Event {
        TranscriptSegment committed;
        State state;
        int index = -1;
        int failures;
        long audioDurationMs;
        float playbackRate;
    }
}
