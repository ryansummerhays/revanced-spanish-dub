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

/** Displays small rolling chunks from the exact Spanish string sent to TTS. */
final class SpanishSubtitleOverlay {
    private static final Pattern TOKEN = Pattern.compile("\\S+");
    private static Activity activity;
    private static TextView textView;
    private static List<TranscriptSegment> segments=new ArrayList<>();
    private static int cursor;

    private SpanishSubtitleOverlay(){}

    static void setSegments(List<TranscriptSegment> snapshot){
        segments=snapshot==null?new ArrayList<>():new ArrayList<>(snapshot);
        cursor=0;
    }

    static void update(Activity a,long timeMs){
        if(a==null||a.isFinishing()||a.isDestroyed())return;
        if(!SpanishStudyPrefs.showSubtitles(a)){hide();return;}
        ensureAttached(a);
        TranscriptSegment active=find(timeMs);
        if(active==null||active.text==null||active.text.isBlank()){
            textView.setVisibility(View.GONE);
            return;
        }
        String lang=active.lang==null?"":active.lang.toLowerCase();
        if(!lang.startsWith("es")){
            textView.setVisibility(View.GONE);
            return;
        }
        String chunk=rollingChunk(a,active,timeMs);
        if(chunk.isBlank()){
            textView.setVisibility(View.GONE);
            return;
        }
        if(!chunk.contentEquals(textView.getText()))textView.setText(chunk);
        textView.setVisibility(View.VISIBLE);
    }

    static void hide(){if(textView!=null)textView.setVisibility(View.GONE);}

    private static TranscriptSegment find(long timeMs){
        List<TranscriptSegment> local=segments;
        if(local.isEmpty())return null;
        if(cursor>=local.size())cursor=local.size()-1;
        while(cursor>0&&timeMs<local.get(cursor).playbackStartMs)cursor--;
        while(cursor+1<local.size()&&timeMs>=local.get(cursor).playbackEndMs)cursor++;
        TranscriptSegment s=local.get(cursor);
        return timeMs>=s.playbackStartMs&&timeMs<s.playbackEndMs?s:null;
    }

    private static String rollingChunk(Activity a,TranscriptSegment segment,long timeMs){
        List<String> tokens=new ArrayList<>();
        Matcher matcher=TOKEN.matcher(segment.text);
        while(matcher.find())tokens.add(matcher.group());
        if(tokens.isEmpty())return "";

        int tokenIndex=estimatedTokenIndex(segment,timeMs,tokens.size());
        SpanishWordTimingStore.Snapshot timing=SpanishWordTimingStore.get(segment.text);
        if(timing!=null&&timing.size()>0){
            long relative=Math.max(0,timeMs-segment.playbackStartMs);
            int boundaryIndex=0;
            for(int i=0;i<timing.size();i++){
                if(timing.startMs[i]<=relative)boundaryIndex=i;
                else break;
            }
            // Edge metadata counts spoken words. Scale to whitespace tokens so punctuation remains
            // exactly as it appears in the master Spanish text rather than rebuilding subtitles.
            tokenIndex=Math.min(tokens.size()-1,
                    (int)Math.floor(boundaryIndex*(tokens.size()/(double)Math.max(1,timing.size()))));
        }

        int perChunk=SpanishStudyPrefs.subtitleWords(a);
        int start=(tokenIndex/perChunk)*perChunk;
        int end=Math.min(tokens.size(),start+perChunk);
        StringBuilder out=new StringBuilder();
        for(int i=start;i<end;i++){
            if(out.length()>0)out.append(' ');
            out.append(tokens.get(i));
        }
        return out.toString();
    }

    private static int estimatedTokenIndex(TranscriptSegment segment,long timeMs,int tokenCount){
        long span=Math.max(1,segment.playbackEndMs-segment.playbackStartMs);
        double progress=Math.max(0,Math.min(0.999,(timeMs-segment.playbackStartMs)/(double)span));
        return Math.min(tokenCount-1,(int)Math.floor(progress*tokenCount));
    }

    private static void ensureAttached(Activity a){
        if(textView!=null&&activity==a&&textView.getParent()!=null)return;
        if(textView!=null&&textView.getParent() instanceof ViewGroup)
            ((ViewGroup)textView.getParent()).removeView(textView);
        activity=a;
        textView=new TextView(a);
        textView.setTextColor(Color.WHITE);
        textView.setTextSize(18);
        textView.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        textView.setGravity(Gravity.CENTER);
        textView.setMaxLines(2);
        int ph=dp(a,12),pv=dp(a,7);
        textView.setPadding(ph,pv,ph,pv);
        GradientDrawable bg=new GradientDrawable();
        bg.setColor(0xCC000000);
        bg.setCornerRadius(dp(a,8));
        textView.setBackground(bg);
        textView.setElevation(dp(a,8));
        FrameLayout.LayoutParams lp=new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL);
        lp.leftMargin=dp(a,20);
        lp.rightMargin=dp(a,20);
        lp.bottomMargin=dp(a,92);
        a.addContentView(textView,lp);
        textView.setVisibility(View.GONE);
    }

    private static int dp(Activity a,int v){
        return Math.round(v*a.getResources().getDisplayMetrics().density);
    }
}
