#!/usr/bin/env python3
"""v2.32.1: startup-safe rollback of the direct AudioTrack.write PCM bytecode hook."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2321_startup_safe.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    player_hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    speaker = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LocalSpeakerDiarizer.java"
    sheet = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudySheet.java"

    for path in (player_hook, controller, speaker, sheet):
        if not path.is_file():
            raise RuntimeError(f"missing source: {path}")

    # v2.32's only invasive app-bytecode change was the new direct AudioTrack.write hook.
    # Restore Morphe's pinned v1.41.0 PlayerVolume hook exactly. This leaves every v2.31/v2.32
    # translation, TTS, subtitle, and UI improvement in place while suspending PCM capture.
    safe_hook = repo / "overlay/v2321/PlayerVolumeHookPatch.kt"
    shutil.copy2(safe_hook, player_hook)
    print("restored: stock Morphe PlayerVolumeHookPatch (PCM hook suspended)")

    rep(controller,
        'report.append("Spanish Dub Study v2.32.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.1 diagnostics\\n");',
        "update diagnostics version")

    rep(speaker,
        'out.append("speakerBackend=direct-exoplayer-pcm-local-spectral-clustering-experiment\\n");',
        'out.append("speakerBackend=direct-pcm-hook-suspended-startup-safe\\n");',
        "report suspended PCM backend")
    rep(speaker,
        'boolean captureAvailable = supportedPcm && pcmHookCalls > 0;',
        'boolean captureAvailable = false;',
        "force speaker capture unavailable while hook is suspended")

    rep(sheet,
        '"$0 API cost. Analyzes a copied slice of YouTube\'s decoded playback PCM; no microphone or cloud audio.",',
        '"Temporarily suspended in v2.32.1 while the direct PCM playback hook is hardened after a startup-crash report. No microphone or cloud audio is used.",',
        "explain startup-safe speaker suspension")

    print("v2.32.1 startup-safe patch complete")


if __name__ == "__main__":
    main()
