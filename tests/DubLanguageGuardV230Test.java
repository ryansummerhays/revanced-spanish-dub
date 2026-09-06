package app.spanishstudy.vot;

public final class DubLanguageGuardV230Test {
    private static void expectSafe(String source, String translated) {
        String reason = DubLanguageGuard.reason(source, translated, "es-ES");
        if (reason != null) throw new AssertionError("expected safe but got " + reason + ": " + translated);
    }

    private static void expectBlocked(String source, String translated) {
        String reason = DubLanguageGuard.reason(source, translated, "es-ES");
        if (reason == null) throw new AssertionError("expected blocked: " + translated);
    }

    public static void main(String[] args) {
        expectSafe("Prepare my ship now, Director Barsha.",
                "Prepare mi nave ahora, director Barsha.");
        expectSafe("Do you remember Lord Vader?", "¿Recuerdas a Lord Vader?");
        expectSafe("The Rebel Alliance is waiting.", "La Alianza Rebelde está esperando.");

        expectBlocked("I know exactly what I have done.", "Sé exactly what he hecho.");
        expectBlocked("An army whose mindless show of force allowed a rebel fleet to escape from Hoth.",
                "Un ejército whose mindless show of force allowed a rebel Fleet to escape from Hoth.");
        expectBlocked("You still don't understand what you have done.",
                "You still don't understand what you have done.");

        System.out.println("DubLanguageGuardV230Test passed");
    }
}
