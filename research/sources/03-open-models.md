# Open models that can do each job (checked 2026-11-04)

- ACE-Step 1.5 (github.com/ace-step/ACE-Step-1.5): MIT licence. Full songs with vocals from caption +
  lyrics, 10 s to 10 min, batch up to 8, 50+ lyric languages, cover/repaint/extract/complete tasks, LoRA
  personalisation from a few songs, under 4 GB VRAM, REST server (`acestep-api`, port 8001):
  POST /release_task, POST /query_result, GET /v1/audio.
- ACE-Step v1 (github.com/ace-step/ACE-Step): Apache-2.0, older 3.5B model.
- YuE and DiffRhythm: other open full-song-with-vocals models; reported to trail commercial vocals.
- MusicGen (Meta AudioCraft): instrumental only; weights CC-BY-NC.
- Demucs / HT-Demucs (Meta): MIT; splits a mix into vocals, drums, bass, other.
- An LLM (Claude via the Anthropic API) for lyric drafting with [Verse]/[Chorus] structure tags.
