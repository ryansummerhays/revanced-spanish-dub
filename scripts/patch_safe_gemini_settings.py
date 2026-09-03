#!/usr/bin/env python3
"""Make the Gemini settings dialog safe to open/save without changing anything.

Previously, tapping Save always called reloadTranscript(), even when the API key and model were
unchanged. reloadTranscript() stops the active dub, clears the translated segment list/TTS state, and
starts a fresh network translation pass. If Gemini is currently rate-limited or the fallback is slow,
merely touching the settings dialog can therefore make a working dub appear to die.

v2.7.1 treats an unchanged Save as a true no-op. Whitespace-only edits are normalized away, and the
current transcript/TTS state is preserved. A genuine key/model change still reloads so the new
configuration takes effect. Diagnostics record only whether a setting changed, never the API key.
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

                    // Merely opening/touching the dialog must never tear down a working dub.
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

    # patch_diagnostics_version.py has already labeled the report v2.7.0 in this build chain.
    rep(controller,
'''        report.append("Spanish Dub Study v2.7.0 diagnostics\\n");''',
'''        report.append("Spanish Dub Study v2.7.1 diagnostics\\n");''',
        "label v2.7.1 diagnostics")

    print("Safe Gemini settings integration complete")


if __name__ == "__main__":
    main()
