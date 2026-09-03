package app.spanishstudy.vot;

import java.util.List;

public final class SpeechUnitPlannerTest {
    public static void main(String[] args) {
        mergesTinyContiguousPhrases();
        borrowsRealSilenceBeforeCrossingPause();
        leavesHealthyUnitsAlone();
        respectsMajorPauseBoundary();
        neverMergesAcrossSpeakerTurn();
        preservesBoundaryFlagAfterNeighborMerge();
        System.out.println("speech unit planner: OK");
    }

    private static void mergesTinyContiguousPhrases() {
        List<SpeechUnitPlanner.Unit> out = SpeechUnitPlanner.coalesce(List.of(
                new SpeechUnitPlanner.Unit(0, 900, "Yes."),
                new SpeechUnitPlanner.Unit(900, 1800, "I think so."),
                new SpeechUnitPlanner.Unit(1800, 4300, "Let's keep going.")));
        require(out.size() < 3, "tiny contiguous phrases should coalesce");
        for (SpeechUnitPlanner.Unit unit : out) {
            require(unit.durationMs() >= SpeechUnitPlanner.MIN_UNIT_MS || out.size() == 1,
                    "coalesced unit is still too short: " + unit.durationMs());
        }
        require(String.join(" ", out.stream().map(SpeechUnitPlanner.Unit::text).toList())
                        .equals("Yes. I think so. Let's keep going."),
                "coalescing changed words/order");
    }

    private static void borrowsRealSilenceBeforeCrossingPause() {
        List<SpeechUnitPlanner.Unit> out = SpeechUnitPlanner.coalesce(List.of(
                new SpeechUnitPlanner.Unit(0, 1200, "Done."),
                new SpeechUnitPlanner.Unit(2800, 6000, "Now we start the next topic.")));
        require(out.size() == 2, "real pause should not force text merge");
        require(out.get(0).endMs() == 2400, "short cue should borrow unused silence");
        require(out.get(0).text().equals("Done."), "borrowed silence changed text");
    }

    private static void leavesHealthyUnitsAlone() {
        List<SpeechUnitPlanner.Unit> in = List.of(
                new SpeechUnitPlanner.Unit(0, 3000, "This one already has enough room."),
                new SpeechUnitPlanner.Unit(3000, 6200, "So does this one."));
        List<SpeechUnitPlanner.Unit> out = SpeechUnitPlanner.coalesce(in);
        require(out.equals(in), "healthy phrase units should remain unchanged");
    }

    private static void respectsMajorPauseBoundary() {
        List<SpeechUnitPlanner.Unit> out = SpeechUnitPlanner.coalesce(List.of(
                new SpeechUnitPlanner.Unit(0, 1500, "Short ending."),
                new SpeechUnitPlanner.Unit(5000, 7600, "A new section starts here.")));
        require(out.size() == 2, "large pause must remain a separate speech region");
        require(out.get(0).endMs() == 2400,
                "planner may borrow enough silence but should preserve a substantial pause");
    }

    private static void neverMergesAcrossSpeakerTurn() {
        List<SpeechUnitPlanner.Unit> out = SpeechUnitPlanner.coalesce(List.of(
                new SpeechUnitPlanner.Unit(0, 1000, "I agree."),
                new SpeechUnitPlanner.Unit(1000, 2100, "No, look here.", true)));
        require(out.size() == 2, "different speaker turns must never be fused");
        require(out.get(1).hardBoundaryBefore(), "speaker boundary metadata was lost");
        require(out.get(0).text().equals("I agree."), "speaker A text changed");
        require(out.get(1).text().equals("No, look here."), "speaker B text changed");
    }

    private static void preservesBoundaryFlagAfterNeighborMerge() {
        List<SpeechUnitPlanner.Unit> out = SpeechUnitPlanner.coalesce(List.of(
                new SpeechUnitPlanner.Unit(0, 1000, "First voice."),
                new SpeechUnitPlanner.Unit(1000, 1800, "Second voice starts.", true),
                new SpeechUnitPlanner.Unit(1800, 4200, "And continues talking.")));
        require(out.size() == 2, "second speaker may merge with its own following phrase");
        require(out.get(1).hardBoundaryBefore(), "speaker-turn flag must survive a same-speaker merge");
        require(out.get(1).text().equals("Second voice starts. And continues talking."),
                "same-speaker merge changed text/order");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
