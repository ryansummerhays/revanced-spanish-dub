# AutoDub-style v2.2 invariants

The v2.2 path is intentionally built around a stable video timeline:

1. Fetch the complete source transcript first.
2. When Gemini is selected, translate the complete transcript before exposing it to playback.
3. Keep a 1:1 segment index mapping between source and translated text.
4. Never mutate `startMs` / `endMs` or use translation progress to choose what gets translated after a seek.
5. TTS synthesis may be prefetched near the playhead, but synthesis must not rewrite segment timestamps.
6. Seeking maps the current source-segment progress proportionally into the generated TTS clip.
7. English and Spanish subtitle lookup both use source timestamps.
