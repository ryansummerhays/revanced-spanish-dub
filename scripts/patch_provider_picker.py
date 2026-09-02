#!/usr/bin/env python3
"""Expose the direct Gemini translator as a normal VoT provider choice.

Run after apply_overlay.py, which adds SpanishStudyController to VotBottomSheet.
The anchors target pinned Morphe v1.41.0 and intentionally fail if upstream changes.
"""
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched: {label}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_provider_picker.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    sheet = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VotBottomSheet.java"
    if not sheet.is_file():
        raise RuntimeError(f"VotBottomSheet.java not found: {sheet}")

    replace_once(
        sheet,
        '''        Runnable refreshTranslation = () -> ((TextView) translationRow.getTag())
                .setText(str("morphe_vot_service_" + Settings.VOT_TRANSLATION_SERVICE.get()));''',
        '''        Runnable refreshTranslation = () -> ((TextView) translationRow.getTag())
                .setText(SpanishStudyController.isGeminiEnabled(Utils.getActivity())
                        ? "Gemini"
                        : str("morphe_vot_service_" + Settings.VOT_TRANSLATION_SERVICE.get()));''',
        "show Gemini as active translation service",
    )

    replace_once(
        sheet,
        '''        String[] entries = {
                str("morphe_vot_service_google"),
                str("morphe_vot_service_mymemory"),
                str("morphe_vot_service_openrouter")
        };
        String[] values = { TRANSLATION_SERVICE_GOOGLE, TRANSLATION_SERVICE_MY_MEMORY, TRANSLATION_SERVICE_OPENROUTER };''',
        '''        String[] entries = {
                str("morphe_vot_service_google"),
                str("morphe_vot_service_mymemory"),
                str("morphe_vot_service_openrouter"),
                "Gemini"
        };
        String[] values = { TRANSLATION_SERVICE_GOOGLE, TRANSLATION_SERVICE_MY_MEMORY, TRANSLATION_SERVICE_OPENROUTER, "gemini" };''',
        "add Gemini provider row",
    )

    replace_once(
        sheet,
        '''        String selectedService = Settings.VOT_TRANSLATION_SERVICE.get();''',
        '''        String selectedService = SpanishStudyController.isGeminiEnabled(Utils.getActivity())
                ? "gemini"
                : Settings.VOT_TRANSLATION_SERVICE.get();''',
        "mark Gemini provider selected",
    )

    replace_once(
        sheet,
        '''            final String value = values[i];
            final boolean isOpenRouter = TRANSLATION_SERVICE_OPENROUTER.equals(value);''',
        '''            final String value = values[i];
            final boolean isOpenRouter = TRANSLATION_SERVICE_OPENROUTER.equals(value);
            final boolean isGemini = "gemini".equals(value);''',
        "identify Gemini provider row",
    )

    replace_once(
        sheet,
        '''            row.setOnClickListener(v -> {
                if (isOpenRouter && Settings.VOT_OPENROUTER_API_KEY.get().trim().isEmpty()) {
                    CustomDialog.create(context,
                                    str("morphe_vot_openrouter_not_configured_title"),
                                    str("morphe_vot_openrouter_not_configured_message"),
                                    null, null, () -> {}, null,
                                    null, null, false)
                            .first.show();
                    return;
                }
                Settings.VOT_TRANSLATION_SERVICE.save(value);
                VoiceOverTranslationPatch.reloadTranscript();
                VotBottomSheet.show(context);
                pickerDialog.dismiss();
            });''',
        '''            row.setOnClickListener(v -> {
                if (isGemini) {
                    android.app.Activity activity = Utils.getActivity();
                    if (!SpanishStudyController.hasGeminiApiKey(activity)) {
                        pickerDialog.dismiss();
                        SpanishStudyController.configureGemini(activity);
                        return;
                    }
                    SpanishStudyController.setGeminiEnabled(activity, true);
                    VoiceOverTranslationPatch.reloadTranscript();
                    VotBottomSheet.show(context);
                    pickerDialog.dismiss();
                    return;
                }
                if (isOpenRouter && Settings.VOT_OPENROUTER_API_KEY.get().trim().isEmpty()) {
                    CustomDialog.create(context,
                                    str("morphe_vot_openrouter_not_configured_title"),
                                    str("morphe_vot_openrouter_not_configured_message"),
                                    null, null, () -> {}, null,
                                    null, null, false)
                            .first.show();
                    return;
                }
                SpanishStudyController.setGeminiEnabled(Utils.getActivity(), false);
                Settings.VOT_TRANSLATION_SERVICE.save(value);
                VoiceOverTranslationPatch.reloadTranscript();
                VotBottomSheet.show(context);
                pickerDialog.dismiss();
            });''',
        "wire Gemini provider selection",
    )

    print("Gemini provider picker integration complete")


if __name__ == "__main__":
    main()
