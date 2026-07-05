# SelfScribe

Self-hosted, no-frills push-to-talk dictation for Windows. Hold (or toggle) a
hotkey, speak, and the transcript lands at your cursor in whatever app has
focus — including a Claude Code terminal. A second "dictate-and-send" hotkey
also presses Enter, so a spoken Claude Code prompt fires hands-free.

- STT: Groq `whisper-large-v3-turbo` (fast, ~cents/hour) or a fully local
  `faster-whisper` fallback (free, offline, private).
- Optional cleanup pass (strip filler, punctuate) via Claude Haiku or a local
  Ollama model — **off by default on the Claude Code path** (raw is faster and
  an LLM doesn't care).
- Custom vocabulary is biased at the Whisper layer (`initial_prompt`) so proper
  nouns come out right.
- No server, no database, no cloud account of its own. Single user, local-first.

## Setup

1. Python 3.12+ on Windows 11.
2. Clone and install:

   ```powershell
   git clone https://github.com/coulditbecoley/selfscribe
   cd selfscribe
   python -m venv .venv
   .venv\Scripts\pip install -e .[dev]
   # optional offline STT backend:
   .venv\Scripts\pip install -e .[local]
   ```

3. Create your config at `%USERPROFILE%\.selfscribe\config.toml` (see
   `config.example.toml`). Minimum viable config is just your Groq key:

   ```toml
   [keys]
   groq = "gsk_..."
   ```

4. Sanity-check the install, then run:

   ```powershell
   .venv\Scripts\selfscribe check
   .venv\Scripts\selfscribe run
   ```

## Usage

| Binding (default)      | What it does                                              |
| ---------------------- | --------------------------------------------------------- |
| `ctrl+win` (hold)      | Dictate: speak, release, cleaned text pastes at cursor    |
| `ctrl+alt+win` (hold)  | Dictate-and-send: raw transcript pastes, then Enter fires |

Both bindings support hold-to-talk and press-to-toggle lock mode (for
long-form dictation) via `hotkeys.mode` in the config.

## Development

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check .
```

Secrets never live in this repo — keys are read only from the dotfile.
