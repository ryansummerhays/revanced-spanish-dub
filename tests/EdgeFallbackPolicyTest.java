package app.spanishstudy.vot;

public final class EdgeFallbackPolicyTest {
    public static void main(String[] args) {
        require(!EdgeFallbackPolicy.shouldOpen(0), "zero failures must stay on Edge");
        require(!EdgeFallbackPolicy.shouldOpen(1), "one transient failure must stay on Edge");
        require(EdgeFallbackPolicy.shouldOpen(2), "second consecutive failure should open fallback");
        long now = 1_000L;
        long until = EdgeFallbackPolicy.fallbackUntil(now);
        require(until == 61_000L, "fallback window should be 60 seconds");
        require(EdgeFallbackPolicy.isOpen(60_999L, until), "circuit should remain open inside window");
        require(!EdgeFallbackPolicy.isOpen(61_000L, until), "circuit should close at deadline");
        System.out.println("edge fallback policy: OK");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
