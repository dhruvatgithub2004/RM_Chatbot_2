# Run the RM Co-pilot

Run everything from VS Code's task menu. Each task opens its own integrated terminal; leave the service terminals running while using the app.

## First-time setup

Make sure Python, Node.js, and the Ollama desktop app are installed. In VS Code, press `Ctrl+Shift+P`, choose **Tasks: Run Task**, then run these tasks as needed:

1. **Setup: Pull Qwen3 8B**. Downloads the base model; skip if already present.
2. **Setup: Create Qwen3 8K variant**. Creates `qwen3:8b-rm` from the base weights; the original `qwen3:8b` is unchanged.
3. **Setup: Create Python environment**. Run once if the workspace `venv` does not exist.
4. **Setup: Install backend packages**. Run after creating the venv or when backend dependencies change.
5. **Setup: Install frontend packages**. Run once or when frontend dependencies change.

If Node.js was just installed, restart VS Code before running the npm setup task so VS Code can find `npm`.

## Start the app

1. Press `Ctrl+Shift+P`, choose **Tasks: Run Task**, and run **Ollama: Start 8K service**. Leave its terminal open.
2. If this is a fresh database, run **Backend: Initialize data (first run)** once. It skips only bulk suggestion generation; Qwen remains enabled for co-pilot chats. Skip this task if data is already loaded.
3. Run **Backend: Start API** and leave its terminal open.
4. Run **Frontend: Start Next.js** and leave its terminal open.
5. Open [http://localhost:3000](http://localhost:3000).

No commands need to be typed into PowerShell; select each named task from the VS Code task menu.

## Caching

The first backend start initializes ChromaDB's local MiniLM embedding model for semantic caching; this one-time download runs in the background. Exact-response caching works immediately. Cache data is stored locally in `backend/.cache/chroma`, expires after 24 hours, and is capped at 500 entries. Semantic reuse is restricted to close matches with identical model and prompt/data context, and cached answers still pass output guardrails. Ollama keeps the model warm for 30 minutes and reuses its prompt prefix where possible.

To tune or disable caching, set `CHAT_CACHE_TTL_SECONDS`, `CHAT_CACHE_MAX_ENTRIES`, or `CHAT_CACHE_SEMANTIC_DISTANCE` in `backend/.env`; set `CHAT_CACHE_ENABLED=0` to turn it off.

## Stop

Use **Terminal → Terminate Task** for each running task, or press `Ctrl+C` in its VS Code terminal.