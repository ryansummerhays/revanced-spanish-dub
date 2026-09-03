#!/usr/bin/env python3
"""Make Gemini configuration/re-selection safe when nothing actually changed.

Previously, tapping Save in the Gemini settings dialog always called reloadTranscript(), even when the
API key and model were unchanged. Re-tapping Gemini in the provider picker did the same. The upstream
reload path stops the active dub, clears translated segments/TTS state, and starts a fresh network
translation pass. If Gemini is rate-limited, merely touching settings can therefore make a working dub
appear to die.

v2.7.1 treats unchanged settings and re-selecting the already-active provider as true no-ops.
Whitespace-only edits are normalized away. Genuine key/model/provider changes still reload so the new
configuration takes effect. Diagnostics never expose the API key.
"""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_safe_gemini_settings.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    picker = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VotBottomSheet.java"

    rep(controller,
'''        EditText key=new EditText(activity);
        key.setHint("Gemini API key");
        key.setSingleLine(true);
        key.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        key.setText(SpanishStudyPrefs.geminiApiKey(activity));
        box.addView(key);

        EditText model=new EditText(activity);
        model.setHint("Gemini model");
        model.setSingleLine(true);
        model.setText(SpanishStudyPrefs.geminiModel(activity));
        box.addView(model);''',
'''        final String originalGeminiKey=SpanishStudyPrefs.geminiApiKey(activity).trim();
        final String originalGeminiModel=SpanishStudyPrefs.geminiModel(activity).trim();

        EditText key=new EditText(activity);
        key.setHint("Gemini API key");
        key.setSingleLine(true);
        key.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        key.setText(originalGeminiKey);
        box.addView(key);

        EditText model=new EditText(activity);
        model.setHint("Gemini model");
        model.setSingleLine(true);
        model.setText(originalGeminiModel);
        box.addView(model);''',
        "capture original Gemini settings")

    rep(controller,
'''                .setPositiveButton("Save",(d,w)->{
                    SpanishStudyPrefs.setGeminiApiKey(activity,key.getText().toString());
                    SpanishStudyPrefs.setGeminiModel(activity,model.getText().toString());
                    boolean ready=!SpanishStudyPrefs.geminiApiKey(activity).trim().isEmpty();
                    SpanishStudyPrefs.setGeminiEnabled(activity,ready);
                    Toast.makeText(activity,ready?"Gemini translation enabled":"Gemini disabled: no API key",Toast.LENGTH_SHORT).show();
                    if(ready)VoiceOverTranslationPatch.reloadTranscript();
                })''',
'''                .setPositiveButton("Save",(d,w)->{
                    final String enteredKey=key.getText().toString().trim();
                    final String enteredModelRaw=model.getText().toString().trim();
                    final String enteredModel=enteredModelRaw.isEmpty()
                            ? SpanishStudyPrefs.DEFAULT_GEMINI_MODEL : enteredModelRaw;
                    final boolean keyChanged=!originalGeminiKey.equals(enteredKey);
                    final boolean modelChanged=!originalGeminiModel.equals(enteredModel);

                    if(!keyChanged&&!modelChanged){
                        SpanishStudyDiagnostics.record("SETTINGS","Gemini settings unchanged; active dub preserved");
                        Toast.makeText(activity,"Gemini settings unchanged",Toast.LENGTH_SHORT).show();
                        return;
                    }

                    SpanishStudyPrefs.setGeminiApiKey(activity,enteredKey);
                    SpanishStudyPrefs.setGeminiModel(activity,enteredModel);
                    boolean ready=!SpanishStudyPrefs.geminiApiKey(activity).trim().isEmpty();
                    SpanishStudyPrefs.setGeminiEnabled(activity,ready);
                    SpanishStudyDiagnostics.record("SETTINGS","Gemini configuration changed key="
                            +keyChanged+" model="+modelChanged+"; reload="+ready);
                    Toast.makeText(activity,ready?"Gemini settings saved":"Gemini disabled: no API key",Toast.LENGTH_SHORT).show();
                    if(ready)VoiceOverTranslationPatch.reloadTranscript();
                })''',
        "avoid destructive reload when Gemini settings are unchanged")

    # patch_provider_picker.py has already wired this block. Re-selecting the current provider should
    # simply close the picker rather than discarding a working transcript/TTS session.
    rep(picker,
'''                if (isGemini) {
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
                }''',
'''                if (isGemini) {
                    android.app.Activity activity = Utils.getActivity();
                    if (!SpanishStudyController.hasGeminiApiKey(activity)) {
                        pickerDialog.dismiss();
                        SpanishStudyController.configureGemini(activity);
                        return;
                    }
                    if (SpanishStudyController.isGeminiEnabled(activity)) {
                        VotBottomSheet.show(context);
                        pickerDialog.dismiss();
                        return;
                    }
                    SpanishStudyController.setGeminiEnabled(activity, true);
                    VoiceOverTranslationPatch.reloadTranscript();
                    VotBottomSheet.show(context);
                    pickerDialog.dismiss();
                    return;
                }''',
        "avoid reload when Gemini provider is already selected")

    rep(picker,
'''                SpanishStudyController.setGeminiEnabled(Utils.getActivity(), false);
                Settings.VOT_TRANSLATION_SERVICE.save(value);
                VoiceOverTranslationPatch.reloadTranscript();''',
'''                if (!SpanishStudyController.isGeminiEnabled(Utils.getActivity())
                        && Settings.VOT_TRANSLATION_SERVICE.get().equals(value)) {
                    VotBottomSheet.show(context);
                    pickerDialog.dismiss();
                    return;
                }
                SpanishStudyController.setGeminiEnabled(Utils.getActivity(), false);
                Settings.VOT_TRANSLATION_SERVICE.save(value);
                VoiceOverTranslationPatch.reloadTranscript();''',
        "avoid reload when non-Gemini provider is already selected")

    # patch_diagnostics_version.py has already labeled the report v2.7.0 in this build chain.
    rep(controller,
'''        report.append("Spanish Dub Study v2.7.0 diagnostics\\n");''',
'''        report.append("Spanish Dub Study v2.7.1 diagnostics\\n");''',
        "label v2.7.1 diagnostics")

    print("Safe Gemini settings/provider integration complete")


if __name__ == "__main__":
    main()
