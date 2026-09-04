package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;

public final class RealtimeTranslationPlannerTest {
    public static void main(String[] args) {
        capsSegments();
        capsCharacters();
        keepsOversizeFirst();
        outputBudget();
        System.out.println("RealtimeTranslationPlannerTest OK");
    }

    private static void capsSegments() {
        List<String> x = new ArrayList<>();
        for (int i = 0; i < 20; i++) x.add("short");
        check(RealtimeTranslationPlanner.boundedSegmentCount(x) == 6, "segment cap");
    }

    private static void capsCharacters() {
        List<String> x = List.of("a".repeat(300), "b".repeat(300), "c".repeat(300));
        check(RealtimeTranslationPlanner.boundedSegmentCount(x) == 2, "character cap");
    }

    private static void keepsOversizeFirst() {
        check(RealtimeTranslationPlanner.boundedSegmentCount(List.of("x".repeat(900), "small")) == 1,
                "oversize first retained");
    }

    private static void outputBudget() {
        check(RealtimeTranslationPlanner.openRouterMaxOutputTokens(80, 1) >= 192,
                "short request output headroom");
        check(RealtimeTranslationPlanner.openRouterMaxOutputTokens(300, 3) >= 216,
                "three-caption output headroom");
        check(RealtimeTranslationPlanner.openRouterMaxOutputTokens(650, 6) >= 421,
                "full realtime batch output headroom");
        check(RealtimeTranslationPlanner.openRouterMaxOutputTokens(5000, 20) == 640,
                "output budget cap");
    }

    private static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }
}
