package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Conservative side-data store for speaker diarization.
 *
 * Speaker identity never changes source timing/text. We only accept a speaker switch when Gemini's
 * audiovisual grounding is confident enough, and we retain a few high-confidence timestamp anchors
 * so later batches can compare voices against earlier examples from the same YouTube video.
 */
final class SpeakerAssignmentStore {
    static final class Proposal {
        final String label;
        final float confidence;
        Proposal(String label,float confidence){this.label=label;this.confidence=confidence;}
    }

    private static final int MAX_ASSIGNMENTS=5000;
    private static final int MAX_ANCHORS_PER_SPEAKER=3;
    private static final Map<String,Assignment> ASSIGNMENTS=
            new LinkedHashMap<String,Assignment>(256,0.75f,true){
                @Override protected boolean removeEldestEntry(Map.Entry<String,Assignment> e){
                    return size()>MAX_ASSIGNMENTS;
                }
            };
    private static final Map<String,List<Long>> ANCHORS=new LinkedHashMap<>();
    private static String lastAcceptedSpeaker="";

    private SpeakerAssignmentStore(){}

    static synchronized void clear(){
        ASSIGNMENTS.clear();
        ANCHORS.clear();
        lastAcceptedSpeaker="";
    }

    static synchronized void commitBatch(List<TranscriptSegment> segments,List<Proposal> proposals){
        if(segments==null||proposals==null)return;
        int n=Math.min(segments.size(),proposals.size());
        for(int i=0;i<n;i++){
            TranscriptSegment seg=segments.get(i);
            Proposal p=proposals.get(i);
            if(seg==null||p==null)continue;
            String candidate=normalizeLabel(p.label);
            float confidence=clamp01(p.confidence);
            if(candidate.isEmpty()||confidence<0.72f)continue;

            String previous=lastAcceptedSpeaker;
            boolean sameAsPrevious=!previous.isEmpty()&&previous.equals(candidate);
            boolean nextAgrees=false;
            if(i+1<n){
                Proposal next=proposals.get(i+1);
                nextAgrees=next!=null&&candidate.equals(normalizeLabel(next.label))&&next.confidence>=0.78f;
            }

            // Fail conservative. Continuing a known speaker requires modest confidence; introducing
            // a new speaker needs either very strong evidence or support from the following segment.
            boolean accept;
            if(previous.isEmpty()) accept=confidence>=0.78f;
            else if(sameAsPrevious) accept=confidence>=0.72f;
            else accept=confidence>=0.92f||(confidence>=0.82f&&nextAgrees);

            if(!accept){
                // A doubtful switch is more likely a yell, whisper, bad channel, or overlap than a
                // truly new person. Keep the previous stable identity rather than inventing one.
                if(!previous.isEmpty())put(seg,previous,Math.min(confidence,0.74f));
                continue;
            }

            put(seg,candidate,confidence);
            lastAcceptedSpeaker=candidate;
            if(confidence>=0.90f&&Math.max(0L,seg.endMs-seg.startMs)>=450L)addAnchor(candidate,seg.startMs);
        }
    }

    static synchronized String speakerLabel(TranscriptSegment seg){
        if(seg==null)return "";
        Assignment a=ASSIGNMENTS.get(key(seg.startMs,seg.endMs));
        return a==null?"":a.label;
    }

    /** -1 means no trustworthy speaker label has been committed yet. */
    static synchronized int speakerIndex(TranscriptSegment seg){
        String label=speakerLabel(seg);
        if(label.isEmpty())return -1;
        char c=label.charAt(0);
        return c>='A'&&c<='H'?c-'A':-1;
    }

    static synchronized String rosterPrompt(){
        if(ANCHORS.isEmpty())return "No previously confirmed speakers. Start with A for the first clearly established voice, then B, C, etc. only when a genuinely different person is heard.";
        StringBuilder out=new StringBuilder("Previously confirmed speaker anchors from this same video. Compare current voices against these timestamps before creating a new label:\n");
        for(Map.Entry<String,List<Long>> e:ANCHORS.entrySet()){
            out.append(e.getKey()).append(": ");
            for(int i=0;i<e.getValue().size();i++){
                if(i>0)out.append(", ");
                out.append(formatTime(e.getValue().get(i)));
            }
            out.append('\n');
        }
        out.append("Do not create a new speaker merely because the same person yells, whispers, laughs, changes accent/prosody, or comes through a different microphone effect.");
        return out.toString();
    }

    private static void put(TranscriptSegment seg,String label,float confidence){
        ASSIGNMENTS.put(key(seg.startMs,seg.endMs),new Assignment(label,confidence));
    }

    private static void addAnchor(String label,long startMs){
        List<Long> values=ANCHORS.computeIfAbsent(label,k->new ArrayList<>());
        for(long existing:values)if(Math.abs(existing-startMs)<1500L)return;
        if(values.size()<MAX_ANCHORS_PER_SPEAKER)values.add(startMs);
    }

    private static String normalizeLabel(String raw){
        if(raw==null)return "";
        String s=raw.trim().toUpperCase(Locale.ROOT);
        if(s.startsWith("SPEAKER_"))s=s.substring(8);
        if(s.startsWith("SPEAKER "))s=s.substring(8).trim();
        if(s.matches("[1-8]"))return String.valueOf((char)('A'+Integer.parseInt(s)-1));
        if(s.matches("[A-H]"))return s;
        return "";
    }

    private static float clamp01(float v){return Math.max(0f,Math.min(1f,v));}
    private static String key(long startMs,long endMs){return startMs+":"+endMs;}
    private static String formatTime(long ms){
        long total=Math.max(0L,ms)/1000L;
        long h=total/3600L,m=(total%3600L)/60L,s=total%60L;
        return h>0?String.format(Locale.ROOT,"%d:%02d:%02d",h,m,s):String.format(Locale.ROOT,"%02d:%02d",m,s);
    }

    private static final class Assignment{
        final String label; final float confidence;
        Assignment(String label,float confidence){this.label=label;this.confidence=confidence;}
    }
}
