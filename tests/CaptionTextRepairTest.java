package app.spanishstudy.vot;

import java.util.List;

public final class CaptionTextRepairTest {
    public static void main(String[] args) {
        joinsDanglingArticle();
        repairsInternalArtifacts();
        respectsSpeakerBoundary();
        System.out.println("CaptionTextRepairTest OK");
    }

    private static void joinsDanglingArticle() {
        List<SpeechUnitPlanner.Unit> in = List.of(
                new SpeechUnitPlanner.Unit(0, 4_800, "Beat a."),
                new SpeechUnitPlanner.Unit(4_800, 8_800, "gym leader, Elite Four member, or champion,"));
        CaptionTextRepair.RepairResult r = CaptionTextRepair.repair(in);
        check(r.units().size() == 1, "dangling article merged");
        check(r.units().get(0).text().contains("Beat a gym leader"), "joined text");
    }

    private static void repairsInternalArtifacts() {
        List<SpeechUnitPlanner.Unit> in = List.of(
                new SpeechUnitPlanner.Unit(0, 5_000, "Finish. the run without wiping out. starter or. team carrier"));
        String out = CaptionTextRepair.repair(in).units().get(0).text();
        check(out.contains("Finish the run"), "short fragment period removed");
        check(out.contains("starter or team carrier"), "dangling conjunction period removed");
    }

    private static void respectsSpeakerBoundary() {
        List<SpeechUnitPlanner.Unit> in = List.of(
                new SpeechUnitPlanner.Unit(0, 2_000, "Beat a."),
                new SpeechUnitPlanner.Unit(2_000, 4_000, "gym leader", true));
        check(CaptionTextRepair.repair(in).units().size() == 2, "speaker boundary retained");
    }

    private static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }
}
