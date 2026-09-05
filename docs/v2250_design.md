# v2.25 design

- Reuse the existing OpenRouter API key for speaker analysis.
- First-pass speaker model: google/gemini-2.5-flash-lite through Google AI Studio, one full-video YouTube request.
- Escalate once to google/gemini-3.7-flash only if the cheap pass is unusable/low-confidence.
- Speaker names may only come from explicit transcript/caption evidence; never infer a real identity from voice or face.
- Keep anonymous A/B/C when a name is not supported.
- Retain v2.24 13-word/~88-character synchronized bilingual cards.
- Restyle subtitles toward common timed-text practice: white primary text, subdued English secondary text, max two lines per language, centered lower-safe-area placement, one coherent dark rounded card, and compact speaker identifier treatment.
