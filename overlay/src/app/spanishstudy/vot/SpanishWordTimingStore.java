package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Keeps Edge-TTS word-boundary metadata keyed by the exact text sent to TTS. */
final class SpanishWordTimingStore {
    static final class Snapshot {
        final long[] startMs;
        final long[] durationMs;
        final String[] words;

        Snapshot(long[] startMs, long[] durationMs, String[] words) {
            this.startMs = startMs;
            this.durationMs = durationMs;
            this.words = words;
        }

        int size() { return words.length; }
    }

    private static final int MAX_ENTRIES = 300;
    private static final Map<String, MutableTimeline> TIMELINES =
            new LinkedHashMap<String, MutableTimeline>(64, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, MutableTimeline> eldest) {
                    return size() > MAX_ENTRIES;
                }
            };

    private SpanishWordTimingStore() {}

    static synchronized void begin(String text) {
        if (text == null || text.isBlank()) return;
        TIMELINES.put(text, new MutableTimeline());
    }

    static synchronized void append(String text, String[] words, long[] starts, long[] durations) {
        if (text == null || text.isBlank() || words == null || starts == null || durations == null) return;
        int n = Math.min(words.length, Math.min(starts.length, durations.length));
        if (n == 0) return;
        MutableTimeline timeline = TIMELINES.get(text);
        if (timeline == null) {
            timeline = new MutableTimeline();
            TIMELINES.put(text, timeline);
        }
        for (int i = 0; i < n; i++) {
            String word = words[i] == null ? "" : words[i];
            if (word.isBlank()) continue;
            timeline.add(word, Math.max(0, starts[i]), Math.max(0, durations[i]));
        }
    }

    static synchronized Snapshot get(String text) {
        MutableTimeline timeline = TIMELINES.get(text);
        return timeline == null ? null : timeline.snapshot();
    }

    static synchronized void clear() {
        TIMELINES.clear();
    }

    private static final class MutableTimeline {
        final List<String> words = new ArrayList<>();
        final List<Long> starts = new ArrayList<>();
        final List<Long> durations = new ArrayList<>();

        void add(String word, long start, long duration) {
            // A cached/repeated synthesis can send the same metadata again. Avoid duplicate rows.
            int size = words.size();
            if (size > 0 && starts.get(size - 1) == start && words.get(size - 1).equals(word)) return;
            words.add(word);
            starts.add(start);
            durations.add(duration);
        }

        Snapshot snapshot() {
            int n = words.size();
            long[] s = new long[n];
            long[] d = new long[n];
            String[] w = new String[n];
            for (int i = 0; i < n; i++) {
                s[i] = starts.get(i);
                d[i] = durations.get(i);
                w[i] = words.get(i);
            }
            return new Snapshot(s, d, w);
        }
    }
}
