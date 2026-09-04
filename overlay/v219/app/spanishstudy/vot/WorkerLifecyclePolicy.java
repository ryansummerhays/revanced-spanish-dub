package app.spanishstudy.vot;

/** Pure lifecycle decisions for Morphe's single transcript/translation worker. */
public final class WorkerLifecyclePolicy {
    private WorkerLifecyclePolicy() {}

    public static boolean shouldPublish(boolean globalEnabled, boolean sessionEnabled,
                                        long workerEpoch, long currentEpoch) {
        return globalEnabled && sessionEnabled && workerEpoch == currentEpoch;
    }

    public static boolean shouldStartImmediately(boolean videoPresent, boolean loading) {
        return videoPresent && !loading;
    }

    public static boolean shouldRestartAfterFinish(boolean globalEnabled,
                                                   boolean sessionEnabled,
                                                   boolean videoPresent,
                                                   boolean restartRequested,
                                                   long workerEpoch,
                                                   long currentEpoch,
                                                   boolean videoChanged,
                                                   boolean languageChanged,
                                                   boolean providerChanged) {
        if (!globalEnabled || !sessionEnabled || !videoPresent) return false;
        return restartRequested
                || workerEpoch != currentEpoch
                || videoChanged
                || languageChanged
                || providerChanged;
    }
}