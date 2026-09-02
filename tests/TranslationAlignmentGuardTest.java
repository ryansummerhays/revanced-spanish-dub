package app.spanishstudy.vot;

import java.util.List;

public final class TranslationAlignmentGuardTest {
    public static void main(String[] args) {
        exactPairPasses();
        wrongSourceEchoFails();
        neighboringWeaponLeakFails();
        copiedEnglishFailsSpanishGuard();
        differentEnglishSentenceFailsSpanishGuard();
        shortAmbiguousTokenIsAllowed();
        concatenatedSpanishFails();
        groundedBackTranslationPasses();
        hallucinatedBackTranslationFails();
        missingNumberFailsGrounding();
        System.out.println("translation alignment guard: OK");
    }

    private static void exactPairPasses() {
        TranslationAlignmentGuard.validate(
                "Let's try it with the R-9.",
                "Let's try it with the R-9.",
                "Probemos con la R-9.",
                List.of("Oh, what's the— okay.", "That feels much better."));
    }

    private static void wrongSourceEchoFails() {
        expectFailure(() -> TranslationAlignmentGuard.validate(
                "Oh, what's the— okay.",
                "Let's try it with the R-9.",
                "Probemos con la R-9.",
                List.of("Let's try it with the R-9.")));
    }

    /** Reproduces the class of mismatch shown in the user's screenshot. */
    private static void neighboringWeaponLeakFails() {
        expectFailure(() -> TranslationAlignmentGuard.validate(
                "Oh, what's the— okay.",
                "Oh, what's the— okay.",
                "Probemos con la R-9.",
                List.of("Let's try it with the R-9.", "That feels much better.")));
    }

    /** Reproduces English source text being sent through the Spanish TTS voice. */
    private static void copiedEnglishFailsSpanishGuard() {
        require(!TranslationAlignmentGuard.isSafeSpanishTranslation(
                "Let's try it with the R-9.", "Let's try it with the R-9."),
                "copied English should never be tagged as Spanish");
    }

    private static void differentEnglishSentenceFailsSpanishGuard() {
        require(!TranslationAlignmentGuard.isSafeSpanishTranslation(
                "Probemos esto.", "What is the best way to do this now?"),
                "clearly English output should never be tagged as Spanish");
    }

    private static void shortAmbiguousTokenIsAllowed() {
        require(TranslationAlignmentGuard.isSafeSpanishTranslation("Okay.", "OK."),
                "short language-neutral tokens should not be over-filtered");
    }

    /** Reproduces v2.3.2 output such as "Sí,creíqueCausticseríalamejor...". */
    private static void concatenatedSpanishFails() {
        require(!TranslationAlignmentGuard.isSafeSpanishTranslation(
                "Yeah, I figured Caustic would be the play because it's World's Edge and he's fun in general.",
                "Sí,creíqueCausticseríalamejorjugadaporqueesWorldsEdgeyademásesdivertidoengeneral."),
                "long Spanish text without normal word spacing must be rejected");
    }

    private static void groundedBackTranslationPasses() {
        require(TranslationAlignmentGuard.isGroundedByBackTranslation(
                "I figured Caustic would be the play because it's World's Edge and he's fun in general.",
                "I thought Caustic would be the choice because it's World's Edge and he's fun in general."),
                "faithful paraphrastic back-translation should pass");
    }

    private static void hallucinatedBackTranslationFails() {
        require(!TranslationAlignmentGuard.isGroundedByBackTranslation(
                "The terminal velocity will be roughly 1.3 meters per second for Doug's bowling ball.",
                "The boat reaches the trench after several hours and the crew decides to turn around."),
                "unrelated invented content should fail the grounding check");
    }

    private static void missingNumberFailsGrounding() {
        require(!TranslationAlignmentGuard.isGroundedByBackTranslation(
                "The R-99 does 12 damage at this range.",
                "The weapon does a lot of damage at this range."),
                "numeric/weapon anchors must survive the round trip");
    }

    private static void expectFailure(Runnable action) {
        boolean failed = false;
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            failed = true;
        }
        if (!failed) throw new AssertionError("expected alignment validation to fail");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
