package app.spanishstudy.vot;

/** Pure gate preventing one subtitle index from being dispatched more than once concurrently. */
public final class SpeechDispatchPolicy {
    private SpeechDispatchPolicy() {}

    public static boolean mayDispatch(int candidateIndex,
                                      int lastSpokenIndex,
                                      int pendingSpeechIndex,
                                      boolean engineSpeaking,
                                      boolean explicitSeek) {
        if (candidateIndex < 0) return false;
        if (candidateIndex == pendingSpeechIndex) return false;
        if (!explicitSeek && candidateIndex <= lastSpokenIndex) return false;
        return !engineSpeaking || explicitSeek;
    }
}
