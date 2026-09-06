#!/usr/bin/env python3
"""v2.32.2 control build: known-good v2.31 runtime with only the VOT study label simplified."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2322_label_only.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    bottom_sheet = pkg / "VotBottomSheet.java"
    sheet = study / "SpanishStudySheet.java"
    controller = study / "SpanishStudyController.java"

    rep(
        bottom_sheet,
        "        LinearLayout studyRow = makeValueRow(context, fg, \"Spanish study\");\n"
        "        ((TextView) studyRow.getTag()).setText(\"Subtitles · local speakers · deep diagnostics\");\n",
        "        LinearLayout studyRow = makeValueRow(context, fg, \"Spanish Dub Study\");\n"
        "        ((TextView) studyRow.getTag()).setText(\"\");\n",
        "simplify VOT study entry",
    )
    rep(sheet, 'title.setText("Spanish study");', 'title.setText("Spanish Dub Study");',
        "rename custom settings sheet")
    rep(controller,
        'report.append("Spanish Dub Study v2.31.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.2 control diagnostics\\n");',
        "mark label-only control build")

    print("v2.32.2 label-only control patch complete")


if __name__ == "__main__":
    main()
