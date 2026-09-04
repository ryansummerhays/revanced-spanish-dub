package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;

public final class StartupTranslationPlannerTest {
    public static void main(String[] args) {
        capsLargeCurrentBatchBySegmentCount();
        capsByCharacters();
        keepsSingleOversizedSegment();
        handlesEmptyInput();
        System.out.println("startup translation planner: OK");
    }

    private static void capsLargeCurrentBatchBySegmentCount() {
        List<String> texts = new ArrayList<>();
        for (int i = 0; i < 40; i++) texts.add("short phrase " + i);
        int count = StartupTranslationPlanner.initialSegmentCount(texts);
        require(count == StartupTranslationPlanner.MAX_INITIAL_SEGMENTS,
                "large playhead batch should cap at " + StartupTranslationPlanner.MAX_INITIAL_SEGMENTS + ", got " + count);
    }

    private static void capsByCharacters() {
        List<String> texts = List.of(
                "a".repeat(240),
                "b".repeat(240),
                "c".repeat(240),
                "small tail");
        int count = StartupTranslationPlanner.initialSegmentCount(texts);
        require(count == 2, "character budget should split before third long phrase, got " + count);
    }

    private static void keepsSingleOversizedSegment() {
        int count = StartupTranslationPlanner.initialSegmentCount(List.of("x".repeat(900), "later"));
        require(count == 1, "first segment must never be split away even when oversized");
    }

    private static void handlesEmptyInput() {
        require(StartupTranslationPlanner.initialSegmentCount(List.of()) == 0, "empty input should return 0");
        require(StartupTranslationPlanner.initialSegmentCount(null) == 0, "null input should return 0");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
