package app.spanishstudy.vot;

import java.util.List;

public final class TranslationAlignmentGuardTest {
    public static void main(String[] args) {
        exactPairPasses();
        wrongSourceEchoFails();
        neighboringWeaponLeakFails();
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

    private static void expectFailure(Runnable action) {
        boolean failed = false;
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            failed = true;
        }
        if (!failed) throw new AssertionError("expected alignment validation to fail");
    }
}
