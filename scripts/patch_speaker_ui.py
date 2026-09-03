#!/usr/bin/env python3
from pathlib import Path
import sys

def rep(path,old,new,label):
    t=path.read_text(); c=t.count(old)
    if c!=1: raise RuntimeError(f"{label}: expected 1 anchor, found {c}")
    path.write_text(t.replace(old,new,1)); print("patched:",label)

def main():
    root=Path(sys.argv[1]).resolve(); pkg=root/"extensions/youtube/src/main/java/app/spanishstudy/vot"
    sheet=pkg/"SpanishStudySheet.java"; ctl=pkg/"SpanishStudyController.java"; ov=pkg/"SpanishSubtitleOverlay.java"

    rep(sheet,
'''        geminiRow.setOnClickListener(v->SpanishStudyController.configureGemini(activity));
        content.addView(geminiRow);

        content.addView(section(activity,"Playback & study",secondary));''',
'''        geminiRow.setOnClickListener(v->SpanishStudyController.configureGemini(activity));
        content.addView(geminiRow);
        content.addView(switchRow(activity,fg,"Use video/audio context",
                "Gemini may inspect the public YouTube video around the current phrase to correct unclear auto-captions and jargon",
                SpanishStudyPrefs.videoGroundingEnabled(activity),
                checked->SpanishStudyPrefs.setVideoGroundingEnabled(activity,checked)));
        content.addView(switchRow(activity,fg,"Recognize different speakers",
                "Conservative voice identity; uncertain changes keep the established speaker",
                SpanishStudyPrefs.speakerRecognitionEnabled(activity),
                checked->SpanishStudyPrefs.setSpeakerRecognitionEnabled(activity,checked)));
        content.addView(switchRow(activity,fg,"Different Spanish voice per speaker",
                "Uses stable alternate Spanish voices for confirmed speakers",
                SpanishStudyPrefs.speakerVoicesEnabled(activity),
                checked->SpanishStudyPrefs.setSpeakerVoicesEnabled(activity,checked)));
        content.addView(switchRow(activity,fg,"Show speaker labels",
                "Shows A, B, C… on the bilingual subtitle pair when a speaker is confidently known",
                SpanishStudyPrefs.speakerLabelsEnabled(activity),
                checked->SpanishStudyPrefs.setSpeakerLabelsEnabled(activity,checked)));

        content.addView(section(activity,"Playback & study",secondary));''',"speaker controls")

    rep(ctl,
'''        TranscriptCorrectionStore.clear();
        DubEventStateStore.clear();''',
'''        TranscriptCorrectionStore.clear();
        SpeakerAssignmentStore.clear();
        DubEventStateStore.clear();''',"clear speaker state per video")

    rep(ctl,
'''    public static String dubBufferStatus(){
        return VoiceOverTranslationPatch.getDubBufferStatusForStudy();
    }
''',
'''    public static String dubBufferStatus(){
        return VoiceOverTranslationPatch.getDubBufferStatusForStudy();
    }

    public static String speakerLabel(TranscriptSegment segment){
        return SpeakerAssignmentStore.speakerLabel(segment);
    }

    public static int speakerIndex(TranscriptSegment segment){
        return SpeakerAssignmentStore.speakerIndex(segment);
    }
''',"speaker APIs")

    rep(ov,
'''        String spanishText = spanish == null || spanish.text == null ? "" : spanish.text.trim();

        if (SpanishStudyPrefs.showSubtitles(a)''',
'''        String spanishText = spanish == null || spanish.text == null ? "" : spanish.text.trim();
        String speaker = SpanishStudyPrefs.speakerLabelsEnabled(a)
                ? SpanishStudyController.speakerLabel(english) : "";
        String speakerPrefix = speaker.isBlank() ? "" : speaker + " · ";

        if (SpanishStudyPrefs.showSubtitles(a)''',"speaker label lookup")

    rep(ov,
'''            if (!spanishText.contentEquals(spanishView.getText())) spanishView.setText(spanishText);''',
'''            String shownSpanish = speakerPrefix + spanishText;
            if (!shownSpanish.contentEquals(spanishView.getText())) spanishView.setText(shownSpanish);''',"show label on Spanish line")

    rep(ov,
'''            if (!englishText.contentEquals(englishView.getText())) englishView.setText(englishText);''',
'''            String shownEnglish = (spanishView.getVisibility() == View.VISIBLE ? "" : speakerPrefix) + englishText;
            if (!shownEnglish.contentEquals(englishView.getText())) englishView.setText(shownEnglish);''',"show label when English-only")

if __name__=="__main__": main()
