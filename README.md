# revanced-spanish-dub

Custom Morphe/ReVanced patch bundle for Spanish dubbing and study tools.

## v2.2

The current build moves the Gemini path toward native AutoDub behavior:

- Fetch the complete YouTube source transcript first.
- Gemini receives the complete transcript as context and the canonical translation is completed before playback uses it.
- Source and translated segments keep a stable 1:1 index and immutable YouTube start/end timestamps.
- Seeking only retargets playback/TTS prefetch; it does not cancel or reprioritize translation.
- TTS synthesis no longer rewrites segment boundaries.
- Seeking inside a segment maps video progress proportionally into the generated Spanish clip.
- English and Spanish custom subtitles both follow the same immutable source timeline.
- Separate subtitle visibility, size and vertical-position controls remain available.
- Gemini appears in the normal translation-provider picker.
- The Spanish study interface uses Morphe's sliding bottom-sheet UI.

For very long videos Gemini output is requested in large blocks, but each block receives the complete transcript as context and all blocks finish before playback receives the translated transcript.

The project pins Morphe patches v1.41.0 and builds an `.mpp` bundle through GitHub Actions.
