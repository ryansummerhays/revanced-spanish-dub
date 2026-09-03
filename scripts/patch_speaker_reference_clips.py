#!/usr/bin/env python3
from pathlib import Path
import sys

def main():
    root=Path(sys.argv[1]).resolve()
    p=root/"extensions/youtube/src/main/java/app/spanishstudy/vot/GeminiVideoGrounding.java"
    t=p.read_text()
    old='''        video.put("processing",processing);\n        input.put(video);\n\n        JSONObject text=new JSONObject();'''
    new='''        video.put("processing",processing);\n        video.put("name","current_clip");\n        input.put(video);\n\n        // Give Gemini tiny, named acoustic reference clips for already-confirmed speakers. This\n        // lets separate progressive requests compare actual voices rather than guessing that a\n        // yell/whisper/accent change is a different person. Each reference is only ~3 seconds.\n        if(SpanishStudyPrefs.speakerRecognitionEnabled(context)){\n            for(SpeakerAssignmentStore.Reference ref:SpeakerAssignmentStore.references()){\n                JSONObject reference=new JSONObject();\n                reference.put("type","video");\n                reference.put("name","speaker_"+ref.label+"_reference");\n                reference.put("uri","https://www.youtube.com/watch?v="+videoId);\n                double rs=Math.max(0.0,ref.startMs/1000.0-1.25);\n                JSONObject rp=new JSONObject();\n                rp.put("type","static");\n                rp.put("start_offset",rs);\n                rp.put("end_offset",rs+3.0);\n                rp.put("fps",0.5);\n                reference.put("processing",rp);\n                input.put(reference);\n            }\n        }\n\n        JSONObject text=new JSONObject();'''
    if t.count(old)!=1: raise RuntimeError(f"speaker reference anchor count={t.count(old)}")
    p.write_text(t.replace(old,new,1))
    print("Speaker acoustic reference clip integration complete")

if __name__=="__main__": main()
