package app.spanishstudy.vot;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/** Displays independently configurable Spanish dub and English source subtitles. */
final class SpanishSubtitleOverlay {
    private static final Pattern TOKEN = Pattern.compile("\\S+");
    private static Activity activity;
    private static TextView spanishView;
    private static TextView englishView;
    private static List<TranscriptSegment> spanishSegments=new ArrayList<>();
    private static List<TranscriptSegment> englishSegments=new ArrayList<>();
    private static int spanishCursor;
    private static int englishCursor;

    private SpanishSubtitleOverlay(){}

    static void setSegments(List<TranscriptSegment> snapshot){
        spanishSegments=snapshot==null?new ArrayList<>():new ArrayList<>(snapshot);
        spanishCursor=0;
    }

    static void setSourceSegments(List<TranscriptSegment> snapshot){
        englishSegments=snapshot==null?new ArrayList<>():new ArrayList<>(snapshot);
        englishCursor=0;
    }

    static void update(Activity a,long timeMs){
        if(a==null||a.isFinishing()||a.isDestroyed())return;
        ensureAttached(a);
        updateLayout(a);
        updateSpanish(a,timeMs);
        updateEnglish(a,timeMs);
    }

    private static void updateSpanish(Activity a,long timeMs){
        if(!SpanishStudyPrefs.showSubtitles(a)){
            spanishView.setVisibility(View.GONE);
            return;
        }
        TranscriptSegment active=findSpanish(timeMs);
        if(active==null||active.text==null||active.text.isBlank()){
            spanishView.setVisibility(View.GONE);
            return;
        }
        String lang=active.lang==null?"":active.lang.toLowerCase();
        if(!lang.startsWith("es")){
            spanishView.setVisibility(View.GONE);
            return;
        }
        String chunk=rollingChunk(a,active,timeMs,true);
        if(chunk.isBlank()){
            spanishView.setVisibility(View.GONE);
            return;
        }
        if(!chunk.contentEquals(spanishView.getText()))spanishView.setText(chunk);
        spanishView.setVisibility(View.VISIBLE);
    }

    private static void updateEnglish(Activity a,long timeMs){
        if(!SpanishStudyPrefs.showEnglishSubtitles(a)){
            englishView.setVisibility(View.GONE);
            return;
        }
        TranscriptSegment active=findEnglish(timeMs);
        if(active==null||active.text==null||active.text.isBlank()){
            englishView.setVisibility(View.GONE);
            return;
        }
        String lang=active.lang==null?"":active.lang.toLowerCase();
        if(!lang.startsWith("en")){
            englishView.setVisibility(View.GONE);
            return;
        }
        String chunk=rollingChunk(a,active,timeMs,false);
        if(chunk.isBlank()){
            englishView.setVisibility(View.GONE);
            return;
        }
        if(!chunk.contentEquals(englishView.getText()))englishView.setText(chunk);
        englishView.setVisibility(View.VISIBLE);
    }

    static void hide(){
        if(spanishView!=null)spanishView.setVisibility(View.GONE);
        if(englishView!=null)englishView.setVisibility(View.GONE);
    }

    /** Both languages are indexed by the immutable YouTube source timeline. */
    private static TranscriptSegment findSpanish(long timeMs){
        List<TranscriptSegment> local=spanishSegments;
        if(local.isEmpty())return null;
        if(spanishCursor>=local.size())spanishCursor=local.size()-1;
        while(spanishCursor>0&&timeMs<local.get(spanishCursor).startMs)spanishCursor--;
        while(spanishCursor+1<local.size()&&timeMs>=local.get(spanishCursor).endMs)spanishCursor++;
        TranscriptSegment s=local.get(spanishCursor);
        return timeMs>=s.startMs&&timeMs<s.endMs?s:null;
    }

    private static TranscriptSegment findEnglish(long timeMs){
        List<TranscriptSegment> local=englishSegments;
        if(local.isEmpty())return null;
        if(englishCursor>=local.size())englishCursor=local.size()-1;
        while(englishCursor>0&&timeMs<local.get(englishCursor).startMs)englishCursor--;
        while(englishCursor+1<local.size()&&timeMs>=local.get(englishCursor).endMs)englishCursor++;
        TranscriptSegment s=local.get(englishCursor);
        return timeMs>=s.startMs&&timeMs<s.endMs?s:null;
    }

    private static String rollingChunk(Activity a,TranscriptSegment segment,long timeMs,boolean spanish){
        List<String> tokens=new ArrayList<>();
        Matcher matcher=TOKEN.matcher(segment.text);
        while(matcher.find())tokens.add(matcher.group());
        if(tokens.isEmpty())return "";

        // Subtitle selection always follows source video time. Edge word timings are used only
        // within the active Spanish segment; they never move the segment itself.
        int tokenIndex=estimatedTokenIndex(segment.startMs,segment.endMs,timeMs,tokens.size());

        if(spanish){
            SpanishWordTimingStore.Snapshot timing=SpanishWordTimingStore.get(segment.text);
            if(timing!=null&&timing.size()>0){
                long relative=Math.max(0,timeMs-segment.startMs);
                long sourceSpan=Math.max(1,segment.endMs-segment.startMs);
                long timingEnd=Math.max(1,timing.startMs[timing.size()-1]);
                long mappedRelative=Math.round((relative/(double)sourceSpan)*timingEnd);
                int boundaryIndex=0;
                for(int i=0;i<timing.size();i++){
                    if(timing.startMs[i]<=mappedRelative)boundaryIndex=i;
                    else break;
                }
                tokenIndex=Math.min(tokens.size()-1,
                        (int)Math.floor(boundaryIndex*(tokens.size()/(double)Math.max(1,timing.size()))));
            }
        }

        int perChunk=SpanishStudyPrefs.subtitleWords(a);
        int chunkStart=(tokenIndex/perChunk)*perChunk;
        int chunkEnd=Math.min(tokens.size(),chunkStart+perChunk);
        StringBuilder out=new StringBuilder();
        for(int i=chunkStart;i<chunkEnd;i++){
            if(out.length()>0)out.append(' ');
            out.append(tokens.get(i));
        }
        return out.toString();
    }

    private static int estimatedTokenIndex(long start,long end,long timeMs,int tokenCount){
        long span=Math.max(1,end-start);
        double progress=Math.max(0,Math.min(0.999,(timeMs-start)/(double)span));
        return Math.min(tokenCount-1,(int)Math.floor(progress*tokenCount));
    }

    private static void ensureAttached(Activity a){
        if(spanishView!=null&&englishView!=null&&activity==a
                &&spanishView.getParent()!=null&&englishView.getParent()!=null)return;
        detach(spanishView);
        detach(englishView);
        activity=a;
        spanishView=createTextView(a);
        englishView=createTextView(a);
        addView(a,spanishView,SpanishStudyPrefs.spanishSubtitleBottom(a));
        addView(a,englishView,SpanishStudyPrefs.englishSubtitleBottom(a));
    }

    private static TextView createTextView(Activity a){
        TextView view=new TextView(a);
        view.setTextColor(Color.WHITE);
        view.setTypeface(Typeface.DEFAULT,Typeface.NORMAL);
        view.setGravity(Gravity.CENTER);
        view.setMaxLines(2);
        view.setPadding(dp(a,8),dp(a,4),dp(a,8),dp(a,4));
        GradientDrawable bg=new GradientDrawable();
        bg.setColor(0xB8000000);
        bg.setCornerRadius(dp(a,6));
        view.setBackground(bg);
        view.setElevation(dp(a,6));
        view.setVisibility(View.GONE);
        return view;
    }

    private static void addView(Activity a,TextView view,int bottomDp){
        FrameLayout.LayoutParams lp=new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL);
        lp.leftMargin=dp(a,28);
        lp.rightMargin=dp(a,28);
        lp.bottomMargin=dp(a,bottomDp);
        a.addContentView(view,lp);
    }

    private static void updateLayout(Activity a){
        spanishView.setTextSize(SpanishStudyPrefs.subtitleTextSize(a));
        englishView.setTextSize(SpanishStudyPrefs.englishSubtitleTextSize(a));
        updateBottomMargin(a,spanishView,SpanishStudyPrefs.spanishSubtitleBottom(a));
        updateBottomMargin(a,englishView,SpanishStudyPrefs.englishSubtitleBottom(a));
    }

    private static void updateBottomMargin(Activity a,TextView view,int bottomDp){
        ViewGroup.LayoutParams raw=view.getLayoutParams();
        if(raw instanceof FrameLayout.LayoutParams){
            FrameLayout.LayoutParams lp=(FrameLayout.LayoutParams)raw;
            int wanted=dp(a,bottomDp);
            if(lp.bottomMargin!=wanted){
                lp.bottomMargin=wanted;
                view.setLayoutParams(lp);
            }
        }
    }

    private static void detach(TextView view){
        if(view!=null&&view.getParent() instanceof ViewGroup)
            ((ViewGroup)view.getParent()).removeView(view);
    }

    private static int dp(Activity a,int v){
        return Math.round(v*a.getResources().getDisplayMetrics().density);
    }
}
