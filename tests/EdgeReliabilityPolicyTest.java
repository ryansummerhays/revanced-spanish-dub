package app.spanishstudy.vot;

public final class EdgeReliabilityPolicyTest {
    public static void main(String[] args) {
        activeCacheMissUsesNative();
        cachedEdgeStaysPreferred();
        futurePhraseDoesNotPrematurelyUseNative();
        unavailableNativeDoesNotBlockEdge();
        repeatedPrefetchFailuresAreSuppressed();
        System.out.println("edge reliability policy: OK");
    }

    private static void activeCacheMissUsesNative() {
        require(EdgeReliabilityPolicy.useNativeForActiveCacheMiss(false, true, 1500, 1000, 3000),
                "active uncached Edge phrase should fail forward to warmed native TTS");
    }

    private static void cachedEdgeStaysPreferred() {
        require(!EdgeReliabilityPolicy.useNativeForActiveCacheMiss(true, true, 1500, 1000, 3000),
                "prefetched Edge audio should remain preferred");
    }

    private static void futurePhraseDoesNotPrematurelyUseNative() {
        require(!EdgeReliabilityPolicy.useNativeForActiveCacheMiss(false, true, 500, 1000, 3000),
                "future phrases should be left for Edge prefetch");
    }

    private static void unavailableNativeDoesNotBlockEdge() {
        require(!EdgeReliabilityPolicy.useNativeForActiveCacheMiss(false, false, 1500, 1000, 3000),
                "if native TTS is not ready the normal Edge path must remain available");
    }

    private static void repeatedPrefetchFailuresAreSuppressed() {
        require(!EdgeReliabilityPolicy.suppressEdgePrefetch(2), "two failures should still permit recovery");
        require(EdgeReliabilityPolicy.suppressEdgePrefetch(3), "third failure should suppress that phrase");
        require(EdgeReliabilityPolicy.suppressEdgePrefetch(10), "suppression must remain stable");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
