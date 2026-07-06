# SelfScribe

Self-hosted, no-frills push-to-talk dictation for Windows — a Wispr Flow
replacement you own. Hold (or toggle) a hotkey, speak, and the transcript
lands at your cursor in whatever app has focus, including a Claude Code
terminal. A second "dictate-and-send" hotkey also presses Enter, so a spoken
Claude Code prompt fires hands-free.

- **STT**: Groq `whisper-large-v3-turbo` (sub-second, ~cents/hour) or a fully
  local `faster-whisper` fallback (free, offline, private).
- **Cleanup** (optional, per-target): strip filler, punctuate, fix STT slips —
  via Claude Haiku or a local Ollama model. **OFF by default on the Claude
  Code send path** (an LLM doesn't need it, and skipping it halves latency);
  ON for the general dictate path (email/docs).
- **Custom vocabulary**: your proper nouns are biased at the Whisper layer
  (`initial_prompt`) and repaired deterministically after (case/spacing +
  edit-distance-1 on capitalized words), so "HitList" never comes back
  "Hitlist".
- No server, no database, no cloud account of its own. Audio lives only in
  memory; telemetry logs latency numbers, never text or audio.

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

3. Create your config at `%USERPROFILE%\.selfscribe\config.toml` (full
   commented reference: [config.example.toml](config.example.toml)). Minimum
   viable config is just your Groq key:

   ```toml
   [keys]
   groq = "gsk_..."
   ```

4. Verify everything, then run:

   ```powershell
   .venv\Scripts\selfscribe check
   .venv\Scripts\selfscribe run
   ```

## Usage

| Binding (default)      | What it does                                               |
| ---------------------- | ---------------------------------------------------------- |
| `ctrl+win` (hold)      | **Dictate**: speak, release → cleaned text pastes at cursor |
| `ctrl+alt+win` (hold)  | **Dictate-and-send**: raw transcript pastes, then Enter — built for Claude Code |

- **Hold vs toggle**: `[hotkeys].mode = "hold"` is push-to-talk;
  `"toggle"` starts on one press and stops on the next (long-form dictation).
  Also switchable from the tray menu.
- **Tray icon**: gray dot = listening, red dot = recording. Menu switches STT
  backend (groq/local), hotkey mode, cleanup override, and quits.
- **Blip guard**: presses under 300 ms or clips that are all silence are
  discarded with a soft beep — nothing is sent anywhere.

## Backends

| | `[stt].backend = "groq"` | `[stt].backend = "local"` |
|---|---|---|
| Speed (short clip) | ~0.5–0.7 s | ~1–2 s after first load |
| Cost | ~$0.04/hr of audio | $0 |
| Privacy | audio → Groq API | never leaves the machine |

Fully-offline private mode: `backend = "local"` + `[cleanup].backend =
"ollama"` (install [Ollama](https://ollama.com), `ollama pull llama3.2:1b`).

### Per-app cleanup profiles

Override the per-target cleanup default based on which application has focus,
by process name in `[cleanup.apps]`:

```toml
[cleanup.apps]
"code.exe" = false      # editor: keep dictation raw
"outlook.exe" = true    # email: clean it up
```

Precedence: backend-off → tray override → per-app → per-target.

## Custom vocabulary

Add your names/terms to `[vocab].terms`. They are fed to Whisper as context
and enforced afterward, so they transcribe in exactly the casing you wrote.

## Dictation commands

On the general **dictate** path (not the Claude Code send path), spoken
phrases become document structure:

| Say | You get |
| --- | --- |
| "new line" | a line break |
| "new paragraph" | a blank line |
| "scratch that" | deletes the current line back to its last break |
| "code block" … "end code block" | a fenced ```` ``` ```` block |

Structural only by design — no "period"/"comma" word commands, which collide
with ordinary speech (the cleanup pass handles punctuation). Turn it off with
`[commands].enabled = false`. The send path never runs commands, so a spoken
"new line" there is just literal words and can't submit your prompt early.
Commands are also suppressed when a **terminal** has focus — a newline pasted
into a shell would submit that line, so dictate structure only takes effect in
text fields (use the send path for terminals).

## Desktop icon

Create a double-clickable launcher on your Desktop (no console window — it
opens straight to the tray, with a mic icon):

```powershell
.venv\Scripts\selfscribe shortcut install   # creates Desktop\SelfScribe.lnk
.venv\Scripts\selfscribe shortcut remove
```

Double-clicking it while SelfScribe is already running just tells you so and
exits — a single-instance guard stops a second copy from grabbing the hotkey.

## Start at login (optional)

```powershell
.venv\Scripts\selfscribe startup install   # Startup-folder shortcut, no admin
.venv\Scripts\selfscribe startup remove
```

## Development

```powershell
.venv\Scripts\python -m pytest -m "not live"   # fast, no network/hardware
.venv\Scripts\python -m pytest                 # full suite incl. live checks
.venv\Scripts\python -m ruff check .
```

Secrets never live in this repo — keys are read only from the dotfile (or
`GROQ_API_KEY` / `ANTHROPIC_API_KEY` env vars).
