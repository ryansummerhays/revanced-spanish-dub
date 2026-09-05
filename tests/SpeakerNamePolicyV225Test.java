package app.spanishstudy.vot;

public final class SpeakerNamePolicyV225Test {
    public static void main(String[] args) {
        acceptsSupportedName();
        rejectsUnsupportedIdentityGuess();
        rejectsLowConfidence();
        rejectsGenericRole();
        System.out.println("SpeakerNamePolicyV225Test passed");
    }

    private static void acceptsSupportedName() {
        String transcript = "Welcome back. My guest today is Peter Attia. Peter, thanks for joining us.";
        eq("Peter Attia", SpeakerNamePolicy.acceptedName(
                "Peter Attia", 0.96, "My guest today is Peter Attia.", transcript));
    }

    private static void rejectsUnsupportedIdentityGuess() {
        String transcript = "Welcome back. Thanks for having me. It is great to be here.";
        eq("", SpeakerNamePolicy.acceptedName(
                "Peter Attia", 0.99, "Thanks for having me.", transcript));
    }

    private static void rejectsLowConfidence() {
        String transcript = "Welcome Sarah. Sarah, thanks for coming.";
        eq("", SpeakerNamePolicy.acceptedName("Sarah", 0.60, "Welcome Sarah.", transcript));
    }

    private static void rejectsGenericRole() {
        String transcript = "The host says hello to the guest.";
        eq("", SpeakerNamePolicy.acceptedName("Host", 0.99, "The host says hello", transcript));
    }

    private static void eq(String a, String b) { if (!a.equals(b)) throw new AssertionError("expected <" + a + "> got <" + b + ">"); }
}
