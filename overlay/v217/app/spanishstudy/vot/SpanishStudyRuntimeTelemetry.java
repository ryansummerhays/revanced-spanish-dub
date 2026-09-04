package app.spanishstudy.vot;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/** Small per-video counters for diagnosing subtitle timing and translation integrity. */
public final class SpanishStudyRuntimeTelemetry {
    private static final AtomicLong epoch = new AtomicLong();
    private static final AtomicInteger translatedSnapshotsAccepted = new AtomicInteger();
    private static final AtomicInteger translatedSnapshotsSuppressed = new AtomicInteger();
    private static final AtomicInteger translationEnglishGuardRejects = new AtomicInteger();
    private static final AtomicInteger ttsEnglishGuardTriggers = new AtomicInteger();
    private static final AtomicInteger subtitleTtsOverrunCount = new AtomicInteger();
    private static final AtomicLong subtitleTtsOverrunTotalMs = new AtomicLong();
    private static final AtomicLong subtitleTtsOverrunMaxMs = new AtomicLong();

    private SpanishStudyRuntimeTelemetry() {}

    public static long beginEpoch() {
        resetCounters();
        return epoch.incrementAndGet();
    }

    public static long bumpEpoch() {
        return epoch.incrementAndGet();
    }

    public static long currentEpoch() {
        return epoch.get();
    }

    public static void recordSnapshotAccepted() {
        translatedSnapshotsAccepted.incrementAndGet();
    }

    public static void recordSnapshotSuppressed() {
        translatedSnapshotsSuppressed.incrementAndGet();
    }

    public static void recordTranslationEnglishGuardReject() {
        translationEnglishGuardRejects.incrementAndGet();
    }

    public static void recordTtsEnglishGuardTrigger() {
        ttsEnglishGuardTriggers.incrementAndGet();
    }

    public static void recordSubtitleOverrun(long overrunMs) {
        if (overrunMs <= 0) return;
        subtitleTtsOverrunCount.incrementAndGet();
        subtitleTtsOverrunTotalMs.addAndGet(overrunMs);
        subtitleTtsOverrunMaxMs.accumulateAndGet(overrunMs, Math::max);
    }

    public static String diagnostics() {
        int n = subtitleTtsOverrunCount.get();
        double mean = n == 0 ? 0.0 : subtitleTtsOverrunTotalMs.get() / (double) n;
        return "sessionEpoch=" + epoch.get() + '\n'
                + "translatedSnapshotsAccepted=" + translatedSnapshotsAccepted.get() + '\n'
                + "translatedSnapshotsSuppressed=" + translatedSnapshotsSuppressed.get() + '\n'
                + "translationEnglishGuardRejects=" + translationEnglishGuardRejects.get() + '\n'
                + "ttsEnglishGuardTriggers=" + ttsEnglishGuardTriggers.get() + '\n'
                + "subtitleTtsOverrunCount=" + n + '\n'
                + "subtitleMeanTtsOverrunMs=" + String.format(Locale.US, "%.1f", mean) + '\n'
                + "subtitleMaxTtsOverrunMs=" + subtitleTtsOverrunMaxMs.get() + '\n';
    }

    private static void resetCounters() {
        translatedSnapshotsAccepted.set(0);
        translatedSnapshotsSuppressed.set(0);
        translationEnglishGuardRejects.set(0);
        ttsEnglishGuardTriggers.set(0);
        subtitleTtsOverrunCount.set(0);
        subtitleTtsOverrunTotalMs.set(0);
        subtitleTtsOverrunMaxMs.set(0);
    }
}