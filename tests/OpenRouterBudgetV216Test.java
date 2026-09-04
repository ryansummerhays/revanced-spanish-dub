package app.spanishstudy.vot;

public final class OpenRouterBudgetV216Test {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        check(OpenRouterBudget.maxOutputTokens(0, 1) == 192, "floor");
        int medium = OpenRouterBudget.maxOutputTokens(900, 8);
        check(medium > 192 && medium < 640, "dynamic middle budget");
        check(OpenRouterBudget.maxOutputTokens(1500, 20) == 640, "native Morphe max batch safely capped");
    }
}
