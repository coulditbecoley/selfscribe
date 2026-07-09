# Agent Guide (AGENTS.md)

> For Codex and other AGENTS.md-aware tools. Created 2026-07-09. This repo has no `CLAUDE.md`. Notes about the project live in Coley's Fenrir Vault (this is the notes-about layer). Follow the standing preferences below.

## Standing preferences (Coley)
- **No em dashes** in any prose you write, anywhere. Use a period, comma, colon, or parentheses instead. Write like a human, not AI.
- **Go with your recommendation.** After giving your own rec, do not ask "does this look right?"; decide, state it, and keep moving. Still ask about genuine forks (which option, budget, scope, anything that spends money or uses outside resources).

## Notes for Codex
- Any reference to Claude Code "skills" or a "REQUIRED SUB-SKILL" (e.g. `superpowers:*`) is Claude Code specific. Ignore the skill machinery; the underlying specs, plans, and TDD steps are tool-agnostic and you can execute them directly.
- Never print a secret value into logs or output. Keep secrets out of the repo.
