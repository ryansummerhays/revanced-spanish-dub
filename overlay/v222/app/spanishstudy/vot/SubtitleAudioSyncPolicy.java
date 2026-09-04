package app.spanishstudy.vot;

/** Pure policy for locking readable subtitle pages to actual dub audio playback. */
public final class SubtitleAudioSyncPolicy {
    private SubtitleAudioSyncPolicy() {}

    /**
     * Before dub playback really begins, keep the bilingual card on page one instead of
     * advancing from source-video time. Once audio starts, the audio window is authoritative.
     */
    public static double pairedProgress(boolean hasDubText, boolean audioStarted,
                                        double audioProgress, double sourceProgress) {
        if (!hasDubText) return clamp(sourceProgress);
        if (!audioStarted) return 0.0;
        return clamp(audioProgress);
    }

    /** Calculate the video-time end of audio that starts now at the given slot-fit rate. */
    public static long playbackEndMs(long actualStartVideoMs, long totalSpeechMs,
                                     long audioOffsetMs, float slotRate) {
        long remaining = Math.max(0L, totalSpeechMs - Math.max(0L, audioOffsetMs));
        float rate = Math.max(0.01f, slotRate);
        return actualStartVideoMs + (long) Math.ceil(remaining / (double) rate);
    }

    /** Position in the TTS clip when an explicit seek starts playback part-way through it. */
    public static double audioStartProgress(long totalSpeechMs, long audioOffsetMs) {
        if (totalSpeechMs <= 0L) return 0.0;
        return clamp(Math.max(0L, audioOffsetMs) / (double) totalSpeechMs);
    }

    private static double clamp(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }
}
