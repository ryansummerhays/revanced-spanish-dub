package app.spanishstudy.vot;

public final class VideoTranslationContextTest {
    public static void main(String[] args) {
        VideoTranslationContext.beginVideo("v1");
        VideoTranslationContext.prepareMetadata("v1", "A strange Pokémon challenge", "Example",
                "Keywords/tags: Pokemon, Nuzlocke. A challenge run.");
        VideoTranslationContext.addRawCue(1_000, 2_000, ">> we picked toadial today");
        VideoTranslationContext.addRawCue(2_000, 3_000, "toadial is our starter");
        VideoTranslationContext.addRawCue(3_000, 4_000, "the nuzlocke begins");
        VideoTranslationContext.addRawCue(4_000, 5_000, "nuzlocke rules apply");
        String context = VideoTranslationContext.contextFor("v1", 1_500, 4_500);
        check(context.contains("Pokémon") || context.contains("Pokemon"), "metadata present");
        check(context.contains("toadial"), "raw cue present");
        check(context.contains("Nuzlocke") || context.contains("nuzlocke"), "whole-video terms present");
        check(VideoTranslationContext.rawCueCount() == 4, "cue count");
        VideoTranslationContext.beginVideo("v2");
        check(VideoTranslationContext.rawCueCount() == 0, "video reset");
        System.out.println("VideoTranslationContextTest OK");
    }

    private static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }
}
