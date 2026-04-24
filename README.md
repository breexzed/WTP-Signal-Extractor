# WTP Signal Extractor

This CLI analyzes transcripts from either:
- a YouTube video URL
- transcript text pasted directly into the terminal

It now runs two extraction passes:
- willingness-to-pay signals
- FGP pipeline intelligence

## Setup

1. Add a Gemini API key to `.env`:
   - `GEMINI_API_KEY=your_key`
   - or `GOOGLE_API_KEY=your_key`
2. Run the app:
   - `uv run python main.py`
   - or `.venv\Scripts\python.exe main.py`

## Notes

- The YouTube flow requires a video with an available transcript.
- If you paste a larger note containing multiple YouTube links, the CLI will use the first valid YouTube URL it finds.
- The project now uses the current `google-genai` SDK instead of the deprecated `google.generativeai` package.
- After transcript capture or fetch, the CLI prints status updates so you can see when the request is being routed to Gemini and when analysis is actively running.
- Model output is normalized before display so the CLI always prints the same multi-pass section layout even if Gemini drifts a little in formatting.
