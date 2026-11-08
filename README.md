# SelfScribe

Self-hosted, no-frills push-to-talk dictation for Windows and macOS. A Wispr Flow
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

## Download

Grab the latest version from the
[Releases page](https://github.com/coulditbecoley/selfscribe/releases/latest)
and pick the zip for your computer:

| Your computer | Download |
| --- | --- |
| Windows 10 or 11 | `SelfScribe-Windows-x64.zip` |
| Mac with an Apple M chip (M1 and newer) | `SelfScribe-macOS-arm64.zip` |
| Older Intel Mac | `SelfScribe-macOS-x86_64.zip` |

Either way you'll need a free **Groq API key** (sign up at
[console.groq.com](https://console.groq.com), then API Keys, Create API Key).
The app asks for it the first time it opens and keeps it only on your computer.

## Windows (download and run)

1. Download `SelfScribe-Windows-x64.zip`, right-click it, **Extract All**,
   and move the `SelfScribe` folder somewhere permanent (for example
   `Documents`).
2. Open the folder and double-click **SelfScribe.exe**. Windows SmartScreen
   may warn that the app is unrecognized (it isn't code-signed): click
   **More info**, then **Run anyway**.
3. Paste your Groq API key when asked.
4. A mic icon appears in the system tray (bottom right; check the ^ overflow).

**Hotkeys on Windows:** hold **Ctrl+Win**, speak, release: the text pastes
where your cursor is. Hold **Ctrl+Alt+Win** to paste and press Enter.

**Start at login:** press Win+R, type `shell:startup`, and put a shortcut to
SelfScribe.exe in that folder. Logs are in `%USERPROFILE%\.selfscribe\selfscribe.log`.

## macOS (download and run)

For someone who just wants to use it on a Mac. macOS 12 or newer.

1. Download `SelfScribe-macOS-arm64.zip` (Apple Silicon: M1 and newer) or
   `SelfScribe-macOS-x86_64.zip` (older Intel Macs). Not sure? Apple menu >
   About This Mac: "Chip: Apple M..." means arm64.
2. Double-click the zip, then drag **SelfScribe.app** into **Applications**.
3. Open it. The first time, macOS says it can't verify the developer (the app
   isn't notarized). Click **Done**, then go to **System Settings > Privacy &
   Security**, scroll down, click **Open Anyway** next to SelfScribe, and
   confirm. You only do this once.
4. Paste your **Groq API key** when asked. It's free: sign up at
   [console.groq.com](https://console.groq.com), then API Keys, Create API Key.
   The key is saved only on that Mac, in `~/.selfscribe/config.toml`.
5. Grant permissions in **System Settings > Privacy & Security**:
   - **Accessibility**: turn on SelfScribe (needed to paste text).
   - **Input Monitoring**: turn on SelfScribe (needed to hear the hotkey).
   - **Microphone**: click Allow the first time you dictate.

   Then quit SelfScribe from its menu-bar mic icon and open it again.

**Hotkeys on Mac:** hold **Control+Command**, speak, release: the text pastes
where your cursor is. Hold **Control+Option+Command** to paste and press
Return (for chat boxes and Claude Code). SelfScribe lives in the menu bar
(no Dock icon); the mic turns red while it's recording.

**Start at login:** System Settings > General > Login Items, add SelfScribe.

**Troubleshooting:** if the hotkey does nothing, Accessibility or Input
Monitoring is off (step 5). Logs are in `~/.selfscribe/selfscribe.log`.

### Building the apps

The `Build apps` GitHub Actions workflow builds all three zips on every push
(Actions > Build apps > Artifacts). Pushing a `v*` tag also publishes them as
a GitHub Release. To build locally: `bash packaging/macos/build.sh` on a Mac,
or `powershell -File packaging/windows/build.ps1` on Windows. Neither app is
code-signed by a paid certificate: macOS needs "Open Anyway" once (notarizing
needs an Apple Developer account) and Windows SmartScreen needs "Run anyway".

## Setup (Windows, from source)

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
- **Instant start**: the mic stream stays open while SelfScribe runs, so
  recording starts the moment the combo lands and the ~250 ms before it is
  kept (no clipped first word). Windows shows the mic-in-use indicator the
  whole time; `[audio].keep_open = false` opens the mic per press instead.

## Backends

| | `[stt].backend = "groq"` | `[stt].backend = "local"` |
|---|---|---|
| Speed (short clip) | ~0.5–0.7 s | ~1–2 s after first load |
| Cost | ~$0.04/hr of audio | $0 |
| Privacy | audio → Groq API | never leaves the machine |

If Groq times out, is unreachable, rate-limits, or has a server error and
the `local` extra is installed, that utterance finishes on local Whisper
instead of being lost (a bad API key still surfaces as an error).
`[stt].groq_model = "whisper-large-v3"` trades ~3x the cost for better
proper nouns.

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
