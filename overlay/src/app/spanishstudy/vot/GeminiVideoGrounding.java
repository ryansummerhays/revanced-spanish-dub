package app.spanishstudy.vot;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import app.morphe.extension.shared.Logger;
import app.morphe.extension.shared.Utils;
import app.morphe.extension.shared.translation.TextTranslator;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Optional audiovisual grounding for progressive Gemini translation.
 *
 * Instead of trusting YouTube ASR text alone, this path gives Gemini the public YouTube URL plus the
 * exact immutable caption slots currently being translated. Gemini can listen to the original audio
 * and inspect video context around those timestamps to resolve unclear words, names, jargon and
 * speaker changes. It never captures the phone microphone or analyzes room/speaker output.
 *
 * The existing text-only Gemini translator remains the automatic fallback when YouTube-URL video
 * processing is unavailable, times out, or fails validation.
 */
final class GeminiVideoGrounding {
    private static final String INTERACTIONS_URL="https://generativelanguage.googleapis.com/v1beta/interactions";
    private static final int CONNECT_TIMEOUT_MS=7_000;
    private static final int READ_TIMEOUT_MS=24_000;

    private GeminiVideoGrounding(){}

    static List<String> translateBatch(String videoId,List<TranscriptSegment> segments,String targetLang){
        Context context=Utils.getContext();
        if(context==null||segments==null||segments.isEmpty()||videoId==null||videoId.isBlank())return null;
        if(!SpanishStudyPrefs.videoGroundingEnabled(context))return null;
        if(!targetLang.toLowerCase(Locale.ROOT).startsWith("es"))return null;
        String apiKey=SpanishStudyPrefs.geminiApiKey(context).trim();
        if(apiKey.isEmpty())return null;

        try{
            String model=SpanishStudyPrefs.geminiModel(context).trim().replaceAll("[^A-Za-z0-9._-]","");
            if(model.isEmpty())model=SpanishStudyPrefs.DEFAULT_GEMINI_MODEL;

            JSONObject request=buildRequest(videoId,segments,targetLang,model,context);
            HttpURLConnection conn=(HttpURLConnection)new URL(INTERACTIONS_URL).openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(READ_TIMEOUT_MS);
            conn.setRequestProperty("Content-Type","application/json; charset=utf-8");
            conn.setRequestProperty("x-goog-api-key",apiKey);
            conn.setRequestProperty("Api-Revision","2026-05-20");
            conn.setDoOutput(true);
            try(OutputStream out=conn.getOutputStream()){
                out.write(request.toString().getBytes(StandardCharsets.UTF_8));
            }

            int code=conn.getResponseCode();
            String response=readAll(code>=200&&code<300?conn.getInputStream():conn.getErrorStream());
            if(code<200||code>=300)throw new Exception("Gemini video grounding HTTP "+code+": "+compact(response));
            String jsonText=extractText(new JSONObject(response));
            if(jsonText==null||jsonText.isBlank())throw new Exception("Gemini video grounding returned no text");
            return validateAndCommit(segments,targetLang,new JSONObject(jsonText),context);
        }catch(Exception ex){
            Logger.printDebug(()->"Audiovisual Gemini grounding unavailable; falling back to transcript-only Gemini: "
                    +ex.getClass().getSimpleName()+": "+ex.getMessage());
            return null;
        }
    }

    private static JSONObject buildRequest(String videoId,List<TranscriptSegment> segments,String targetLang,
                                           String model,Context context)throws Exception{
        JSONObject root=new JSONObject();
        root.put("model",model);

        JSONArray input=new JSONArray();
        JSONObject video=new JSONObject();
        video.put("type","video");
        video.put("uri","https://www.youtube.com/watch?v="+videoId);
        video.put("processing","agentic");
        input.put(video);

        JSONObject text=new JSONObject();
        text.put("type","text");
        text.put("text",buildPrompt(segments,targetLang,context));
        input.put(text);
        root.put("input",input);

        JSONObject generation=new JSONObject();
        generation.put("temperature",0.05);
        root.put("generation_config",generation);

        // Structured JSON dramatically reduces positional/speaker-label drift. Keep the schema small
        // enough to remain compatible with fast Gemini models.
        JSONObject itemProps=new JSONObject();
        itemProps.put("id",new JSONObject().put("type","integer"));
        itemProps.put("source",new JSONObject().put("type","string"));
        itemProps.put("correctedSource",new JSONObject().put("type","string"));
        itemProps.put("translation",new JSONObject().put("type","string"));
        itemProps.put("speaker",new JSONObject().put("type","string"));
        itemProps.put("speakerConfidence",new JSONObject().put("type","number"));
        JSONObject itemSchema=new JSONObject().put("type","object").put("properties",itemProps)
                .put("required",new JSONArray().put("id").put("source").put("correctedSource")
                        .put("translation").put("speaker").put("speakerConfidence"));
        JSONObject schema=new JSONObject().put("type","object")
                .put("properties",new JSONObject().put("items",
                        new JSONObject().put("type","array").put("items",itemSchema)))
                .put("required",new JSONArray().put("items"));
        root.put("response_format",new JSONObject().put("type","text")
                .put("mime_type","application/json").put("schema",schema));
        return root;
    }

    private static String buildPrompt(List<TranscriptSegment> segments,String targetLang,Context context){
        long start=segments.get(0).startMs;
        long end=segments.get(segments.size()-1).endMs;
        StringBuilder p=new StringBuilder();
        p.append("You are grounding bilingual study subtitles against the ACTUAL public YouTube video. ")
                .append("Inspect/listen specifically from ").append(formatTime(start)).append(" to ")
                .append(formatTime(end)).append(". The raw English lines below come from YouTube ASR and may contain errors.\n\n")
                .append("For every input id return exactly one output object with the same id and exact raw source echo. ")
                .append("correctedSource must remain IDENTICAL unless the audio, sentence context, visible video context, recurring subject matter, or proper-noun/jargon context gives strong evidence of a real ASR error. ")
                .append("Correct what was actually said, not what would merely sound plausible. Examples include a poorly enunciated game/item name, acronym, player name, technical term, slang, homophone, or merged word. Do not rewrite style or grammar.\n")
                .append("Translate the intended meaning into concise natural Spanish for dubbing. Do not add facts from video context that were not spoken in this subtitle event. Preserve numbers/names and normal Spanish spaces.\n\n");

        if(SpanishStudyPrefs.speakerRecognitionEnabled(context)){
            p.append("SPEAKERS: listen to voice identity, not merely wording. Label speakers A-H. ")
                    .append("Use the same label whenever the same person returns. A person yelling, whispering, laughing, changing emotion/accent/prosody, or sounding different through voice chat remains the SAME speaker. ")
                    .append("If speaker identity is uncertain, prefer the established previous speaker rather than inventing a switch. speakerConfidence is 0..1 and should reflect voice-identity confidence.\n")
                    .append(SpeakerAssignmentStore.rosterPrompt()).append("\n\n");
        }else{
            p.append("Set speaker to an empty string and speakerConfidence to 0.\n\n");
        }

        p.append("INPUT EVENTS:\n");
        for(int i=0;i<segments.size();i++){
            TranscriptSegment s=segments.get(i);
            p.append(i).append(" | ").append(formatTime(s.startMs)).append("-")
                    .append(formatTime(s.endMs)).append(" | ")
                    .append(s.text==null?"":s.text.replace('\n',' ')).append('\n');
        }
        return p.toString();
    }

    private static List<String> validateAndCommit(List<TranscriptSegment> segments,String targetLang,
                                                   JSONObject response,Context context)throws Exception{
        JSONArray arr=response.optJSONArray("items");
        if(arr==null||arr.length()!=segments.size())throw new Exception("grounded item count mismatch");

        List<String> translations=new ArrayList<>(segments.size());
        List<String> intended=new ArrayList<>(segments.size());
        List<SpeakerAssignmentStore.Proposal> speakers=new ArrayList<>(segments.size());
        for(int i=0;i<segments.size();i++){translations.add(null);intended.add(null);speakers.add(null);}

        for(int n=0;n<arr.length();n++){
            JSONObject item=arr.optJSONObject(n);
            if(item==null)throw new Exception("grounded item is not object");
            int id=item.optInt("id",-1);
            if(id<0||id>=segments.size())throw new Exception("grounded id out of range: "+id);
            TranscriptSegment src=segments.get(id);
            String sourceEcho=item.optString("source","");
            String corrected=item.optString("correctedSource",sourceEcho).trim();
            String translation=TranslationAlignmentGuard.normalize(item.optString("translation",""));

            TranslationAlignmentGuard.validate(src.text,sourceEcho,translation,neighbors(segments,id));
            TranscriptCorrectionStore.put(src.startMs,src.endMs,src.text,corrected);
            String accepted=TranscriptCorrectionStore.get(src.startMs,src.endMs,src.text);
            intended.set(id,accepted);
            translations.set(id,translation);

            if(SpanishStudyPrefs.speakerRecognitionEnabled(context)){
                speakers.set(id,new SpeakerAssignmentStore.Proposal(item.optString("speaker",""),
                        (float)item.optDouble("speakerConfidence",0.0)));
            }
        }

        // Independent semantic check exactly like the text-only path. A video-aware answer still is
        // model output and does not get to bypass hallucination defenses.
        List<Integer> ids=new ArrayList<>();
        List<String> spanish=new ArrayList<>();
        for(int i=0;i<translations.size();i++)if(translations.get(i)!=null&&!translations.get(i).isBlank()){
            ids.add(i);spanish.add(translations.get(i));
        }
        try{
            List<String> back=TextTranslator.translate(spanish,"en");
            for(int i=0;i<Math.min(ids.size(),back.size());i++){
                int id=ids.get(i);
                if(!TranslationAlignmentGuard.isGroundedByBackTranslation(intended.get(id),back.get(i))){
                    translations.set(id,null);
                    TranscriptSegment src=segments.get(id);
                    TranscriptCorrectionStore.remove(src.startMs,src.endMs);
                    intended.set(id,src.text);
                }
            }
        }catch(Exception verifier){
            Logger.printDebug(()->"Audiovisual grounding back-translation verifier unavailable: "+verifier.getMessage());
        }

        // Rescue only failed Spanish lines with the conservative ordinary translator. Speaker side
        // data can still be useful even if one translation candidate was rejected.
        List<Integer> rescueIds=new ArrayList<>();
        List<String> rescueSource=new ArrayList<>();
        for(int i=0;i<translations.size();i++)if(translations.get(i)==null||translations.get(i).isBlank()){
            rescueIds.add(i);rescueSource.add(intended.get(i)==null?segments.get(i).text:intended.get(i));
        }
        if(!rescueSource.isEmpty()){
            List<String> rescued=TextTranslator.translate(rescueSource,targetLang);
            for(int i=0;i<Math.min(rescueIds.size(),rescued.size());i++){
                int id=rescueIds.get(i);
                String candidate=TranslationAlignmentGuard.normalize(rescued.get(i));
                if(TranslationAlignmentGuard.isSafeSpanishTranslation(rescueSource.get(i),candidate))translations.set(id,candidate);
            }
        }

        for(int i=0;i<translations.size();i++)if(translations.get(i)==null||translations.get(i).isBlank())
            throw new Exception("no safe translation for grounded slot "+i);

        if(SpanishStudyPrefs.speakerRecognitionEnabled(context))SpeakerAssignmentStore.commitBatch(segments,speakers);
        return translations;
    }

    private static List<String> neighbors(List<TranscriptSegment> segments,int id){
        List<String> out=new ArrayList<>();
        for(int i=Math.max(0,id-2);i<=Math.min(segments.size()-1,id+2);i++)if(i!=id){
            String t=segments.get(i).text;if(t!=null&&!t.isBlank())out.add(t);
        }
        return out;
    }

    private static String extractText(JSONObject root){
        String direct=root.optString("output_text","");
        if(!direct.isBlank())return direct;
        JSONArray steps=root.optJSONArray("steps");
        if(steps!=null){
            StringBuilder out=new StringBuilder();
            for(int i=0;i<steps.length();i++){
                JSONObject step=steps.optJSONObject(i);if(step==null)continue;
                JSONArray content=step.optJSONArray("content");if(content==null)continue;
                for(int j=0;j<content.length();j++){
                    JSONObject c=content.optJSONObject(j);if(c==null)continue;
                    if("text".equals(c.optString("type"))){String t=c.optString("text","");if(!t.isBlank())out.append(t);}
                }
            }
            if(out.length()>0)return out.toString();
        }
        JSONArray outputs=root.optJSONArray("outputs");
        if(outputs!=null)for(int i=outputs.length()-1;i>=0;i--){
            JSONObject o=outputs.optJSONObject(i);if(o!=null&&!o.optString("text","").isBlank())return o.optString("text");
        }
        JSONObject interaction=root.optJSONObject("interaction");
        return interaction==null?"":extractText(interaction);
    }

    private static String readAll(InputStream in)throws Exception{
        if(in==null)return "";
        StringBuilder sb=new StringBuilder();
        try(BufferedReader r=new BufferedReader(new InputStreamReader(in,StandardCharsets.UTF_8))){
            String line;while((line=r.readLine())!=null)sb.append(line);
        }
        return sb.toString();
    }
    private static String compact(String s){
        if(s==null)return "";String x=s.replaceAll("\\s+"," ").trim();return x.length()>280?x.substring(0,280):x;
    }
    private static String formatTime(long ms){
        long total=Math.max(0L,ms)/1000L;long h=total/3600L,m=(total%3600L)/60L,s=total%60L;
        long milli=Math.max(0L,ms)%1000L;
        return h>0?String.format(Locale.ROOT,"%d:%02d:%02d.%03d",h,m,s,milli)
                :String.format(Locale.ROOT,"%02d:%02d.%03d",m,s,milli);
    }
}
