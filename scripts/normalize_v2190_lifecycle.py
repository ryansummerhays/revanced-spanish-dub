#!/usr/bin/env python3
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: normalize_v2190_lifecycle.py <patch-script>")
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")

    text = text.replace(
        "        return value.replace('\\\\n', ' ').replace('\\\\r', ' ');",
        "        return value.replace((char)10, ' ').replace((char)13, ' ');")

    marker = "    rep(telemetry,\n        '''                + \"subtitleMaxTtsOverrunMs=\" + subtitleTtsOverrunMaxMs.get()"
    start = text.index(marker)
    end_marker = "    rep(telemetry,\n        '''        subtitleTtsOverrunMaxMs.set(0);"
    end = text.index(end_marker, start)
    lines = [
        "    rep(telemetry,",
        "        '''                + \"subtitleMaxTtsOverrunMs=\" + subtitleTtsOverrunMaxMs.get()''',",
        "        '''                + \"subtitleMaxTtsOverrunMs=\" + subtitleTtsOverrunMaxMs.get() + System.lineSeparator()",
        "                + \"translationWorkerEpoch=\" + translationWorkerEpoch + System.lineSeparator()",
        "                + \"translationWorkerState=\" + translationWorkerState + System.lineSeparator()",
        "                + \"translationWorkerStarts=\" + translationWorkerStarts.get() + System.lineSeparator()",
        "                + \"translationWorkerStops=\" + translationWorkerStops.get() + System.lineSeparator()",
        "                + \"translationWorkerRestartRequests=\" + translationWorkerRestartRequests.get() + System.lineSeparator()",
        "                + \"translationWorkerStaleDrops=\" + translationWorkerStaleDrops.get() + System.lineSeparator()",
        "                + \"translationWorkerLastStartReason=\" + translationWorkerLastStartReason + System.lineSeparator()",
        "                + \"translationWorkerLastStopReason=\" + translationWorkerLastStopReason + System.lineSeparator()",
        "                + \"translationWorkerLastRestartReason=\" + translationWorkerLastRestartReason + System.lineSeparator()",
        "                + \"ttsStartAttempts=\" + ttsStartAttempts.get() + System.lineSeparator()",
        "                + \"ttsRepeatedStartAttempts=\" + ttsRepeatedStartAttempts.get() + System.lineSeparator()",
        "                + \"ttsLateSkips=\" + ttsLateSkips.get() + System.lineSeparator()",
        "                + \"ttsMaxLateStartMs=\" + ttsMaxLateStartMs.get()''',",
        "        \"publish worker and TTS telemetry\")",
        "",
        "",
    ]
    new_block = "\n".join(lines)
    text = text[:start] + new_block + text[end:]
    path.write_text(text, encoding="utf-8")
    print("normalized: v2.19 Java newline literals")


if __name__ == "__main__":
    main()
