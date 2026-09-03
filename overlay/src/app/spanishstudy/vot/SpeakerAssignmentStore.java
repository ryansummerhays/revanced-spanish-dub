package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Conservative per-video speaker clustering side-data.
 *
 * The expensive acoustic decision is made remotely from the video's digital audio, never from the
 * phone microphone or room sound. This store makes those proposals stable and cheap at runtime:
 * labels are committed with hysteresis, high-confidence anchors become short reference clips for
 * later windows, and unanalysed subtitle slots may inherit the most recent confirmed profile for a
 * bounded interval instead of flickering between labelled/unlabelled states.
 */
final class SpeakerAssignmentStore {
    static final class Proposal {
        final String label;
        final float confidence;
        Proposal(String label,float confidence){this.label=label;this.confidence=confidence;}
    }

    static final class Reference {
        final String label;
        final long startMs;
        Reference(String label,long startMs){this.label=label;this.startMs=startMs;}
    }

    private static final class Assignment {
        final String label;
        final float confidence;
        Assignment(String label,float confidence){this.label=label;this.confidence=confidence;}
    }

    private static final class Profile {
        final String label;
        int assignments;
        long firstMs=Long.MAX_VALUE;
        long lastMs;
        float bestConfidence;
        Profile(String label){this.label=label;}
        void observe(long startMs,float confidence){
            assignments++;
            firstMs=Math.min(firstMs,startMs);
            lastMs=Math.max(lastMs,startMs);
            bestConfidence=Math.max(bestConfidence,confidence);
        }
    }

    private static final int MAX_ASSIGNMENTS=5000;
    private static final int MAX_ANCHORS_PER_SPEAKER=3;
    private static final long PROPAGATE_PROFILE_MAX_MS=90_000L;

    private static final Map<String,Assignment> ASSIGNMENTS=
            new LinkedHashMap<String,Assignment>(256,0.75f,true){
                @Override protected boolean removeEldestEntry(Map.Entry<String,Assignment> e){
                    return size()>MAX_ASSIGNMENTS;
                }
            };
    private static final TreeMap<Long,Assignment> TIMELINE=new TreeMap<>();
    private static final Map<String,List<Long>> ANCHORS=new LinkedHashMap<>();
    private static final Map<String,Profile> PROFILES=new LinkedHashMap<>();
    private static String lastAcceptedSpeaker="";

    private SpeakerAssignmentStore(){}

    static synchronized void clear(){
        ASSIGNMENTS.clear();
        TIMELINE.clear();
        ANCHORS.clear();
        PROFILES.clear();
        lastAcceptedSpeaker="";
    }

    static synchronized void commitBatch(List<TranscriptSegment> segments,List<Proposal> proposals){
        if(segments==null||proposals==null)return;
        int n=Math.min(segments.size(),proposals.size());
        Map<String,Integer> committedThisBatch=new LinkedHashMap<>();
        for(int i=0;i<n;i++){
            TranscriptSegment seg=segments.get(i);
            Proposal p=proposals.get(i);
            if(seg==null||p==null)continue;
            String candidate=normalizeLabel(p.label);
            float confidence=clamp01(p.confidence);
            if(candidate.isEmpty()||confidence<0.70f)continue;

            String previous=lastAcceptedSpeaker;
            boolean sameAsPrevious=!previous.isEmpty()&&previous.equals(candidate);
            boolean nextAgrees=false;
            if(i+1<n){
                Proposal next=proposals.get(i+1);
                nextAgrees=next!=null&&candidate.equals(normalizeLabel(next.label))&&next.confidence>=0.80f;
            }
            boolean alreadyEstablished=PROFILES.containsKey(candidate);

            // New identities need stronger evidence than continuity. This is deliberately biased
            // against false speaker changes caused by yelling, whispering, laughter or mic effects.
            boolean accept;
            if(previous.isEmpty())accept=confidence>=0.80f;
            else if(sameAsPrevious)accept=confidence>=0.70f;
            else if(alreadyEstablished)accept=confidence>=0.86f||(confidence>=0.80f&&nextAgrees);
            else accept=confidence>=0.94f||(confidence>=0.85f&&nextAgrees);

            if(!accept){
                if(!previous.isEmpty())put(seg,previous,Math.min(confidence,0.74f));
                continue;
            }

            put(seg,candidate,confidence);
            lastAcceptedSpeaker=candidate;
            committedThisBatch.put(candidate,committedThisBatch.getOrDefault(candidate,0)+1);
            if(confidence>=0.90f&&Math.max(0L,seg.endMs-seg.startMs)>=450L)addAnchor(candidate,seg.startMs);
        }

        if(!committedThisBatch.isEmpty()){
            StringBuilder msg=new StringBuilder("profiles ");
            boolean first=true;
            for(Map.Entry<String,Integer> e:committedThisBatch.entrySet()){
                if(!first)msg.append(' ');
                first=false;
                msg.append(e.getKey()).append('+').append(e.getValue());
            }
            msg.append(" total=").append(profileSummary());
            SpanishStudyDiagnostics.record("SPEAKER",msg.toString());
        }
    }

    static synchronized String speakerLabel(TranscriptSegment seg){
        if(seg==null)return "";
        Assignment exact=ASSIGNMENTS.get(key(seg.startMs,seg.endMs));
        if(exact!=null)return exact.label;

        // Lightweight profile propagation fills the gaps between acoustic windows. It is bounded so
        // a stale host label cannot silently cover an entire long video after analysis has stopped.
        Map.Entry<Long,Assignment> floor=TIMELINE.floorEntry(seg.startMs);
        if(floor!=null&&seg.startMs-floor.getKey()<=PROPAGATE_PROFILE_MAX_MS)return floor.getValue().label;
        return "";
    }

    /** -1 means no trustworthy speaker label has been committed yet. */
    static synchronized int speakerIndex(TranscriptSegment seg){
        String label=speakerLabel(seg);
        if(label.isEmpty())return -1;
        char c=label.charAt(0);
        return c>='A'&&c<='H'?c-'A':-1;
    }

    static synchronized int profileCount(){return PROFILES.size();}

    static synchronized String profileSummary(){
        if(PROFILES.isEmpty())return "none yet";
        StringBuilder out=new StringBuilder();
        for(Profile p:PROFILES.values()){
            if(out.length()>0)out.append(" · ");
            out.append(p.label).append(" (").append(p.assignments).append(")");
        }
        return out.toString();
    }

    /** One recent high-confidence acoustic reference per established speaker, up to four speakers. */
    static synchronized List<Reference> references(){
        ArrayList<Reference> out=new ArrayList<>();
        for(Map.Entry<String,List<Long>> e:ANCHORS.entrySet()){
            List<Long> values=e.getValue();
            if(!values.isEmpty())out.add(new Reference(e.getKey(),values.get(values.size()-1)));
            if(out.size()>=4)break;
        }
        return out;
    }

    static synchronized String rosterPrompt(){
        if(ANCHORS.isEmpty())return "No previously confirmed speakers. Start with A for the first clearly established voice, then B, C, etc. only when a genuinely different person is heard.";
        StringBuilder out=new StringBuilder("Established acoustic speaker profiles: ");
        boolean first=true;
        for(Map.Entry<String,List<Long>> e:ANCHORS.entrySet()){
            List<Long> v=e.getValue();
            if(v.isEmpty())continue;
            if(!first)out.append(", ");
            first=false;
            out.append(e.getKey()).append("@ ").append(formatTime(v.get(v.size()-1)));
        }
        out.append(". If named reference clips are attached, compare voice identity against them before creating a new label. Do not create a new speaker merely because the same person yells, whispers, laughs, changes accent/prosody, or comes through a different microphone effect.");
        return out.toString();
    }

    private static void put(TranscriptSegment seg,String label,float confidence){
        String k=key(seg.startMs,seg.endMs);
        Assignment previous=ASSIGNMENTS.get(k);
        Assignment next=new Assignment(label,confidence);
        ASSIGNMENTS.put(k,next);
        TIMELINE.put(seg.startMs,next);
        if(previous==null||!previous.label.equals(label)){
            Profile profile=PROFILES.computeIfAbsent(label,Profile::new);
            profile.observe(seg.startMs,confidence);
        }
    }

    private static void addAnchor(String label,long startMs){
        List<Long> values=ANCHORS.computeIfAbsent(label,k->new ArrayList<>());
        for(long existing:values)if(Math.abs(existing-startMs)<1500L)return;
        if(values.size()>=MAX_ANCHORS_PER_SPEAKER)values.remove(0);
        values.add(startMs);
    }

    private static String normalizeLabel(String raw){
        if(raw==null)return "";
        String s=raw.trim().toUpperCase(Locale.ROOT);
        if(s.startsWith("SPEAKER_"))s=s.substring(8);
        if(s.startsWith("SPEAKER "))s=s.substring(8).trim();
        if(s.matches("[1-8]"))return String.valueOf((char)('A'+Integer.parseInt(s)-1));
        return s.matches("[A-H]")?s:"";
    }

    private static float clamp01(float v){return Math.max(0f,Math.min(1f,v));}
    private static String key(long startMs,long endMs){return startMs+":"+endMs;}
    private static String formatTime(long ms){
        long total=Math.max(0L,ms)/1000L,h=total/3600L,m=(total%3600L)/60L,s=total%60L;
        return h>0?String.format(Locale.ROOT,"%d:%02d:%02d",h,m,s)
                :String.format(Locale.ROOT,"%02d:%02d",m,s);
    }
}
