#!/usr/bin/env python3
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: normalize_v2190_lifecycle.py <patch-script>")
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")

    old_clean = "        return value.replace('\\n', ' ').replace('\\r', ' ');"
    if old_clean not in text:
        raise RuntimeError("v2.19 clean helper escape anchor not found in patch script")
    text = text.replace(
        old_clean,
        "        return value.replace((char)10, ' ').replace((char)13, ' ');",
        1)

    old_import = '''    rep(vot,\n        \'\'\'import app.spanishstudy.vot.SpanishStudyRuntimeTelemetry;\'\'\',\n        \'\'\'import app.spanishstudy.vot.SpanishStudyRuntimeTelemetry;\nimport app.spanishstudy.vot.WorkerLifecyclePolicy;\'\'\',\n        "import worker lifecycle policy")'''
    new_import = '''    rep(vot,\n        \'\'\'import app.spanishstudy.vot.SpanishStudyDiagnostics;\'\'\',\n        \'\'\'import app.spanishstudy.vot.SpanishStudyDiagnostics;\nimport app.spanishstudy.vot.SpanishStudyRuntimeTelemetry;\nimport app.spanishstudy.vot.WorkerLifecyclePolicy;\'\'\',\n        "import worker lifecycle policy")'''
    if old_import not in text:
        raise RuntimeError("v2.19 lifecycle import patch anchor not found in patch script")
    text = text.replace(old_import, new_import, 1)

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
    print("normalized: v2.19 Java newline literals and import anchor")


if __name__ == "__main__":
    main()
