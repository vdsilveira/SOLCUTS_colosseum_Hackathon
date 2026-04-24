# AGENTS.md - SolCuts Colosseum Hackathon

## Project Overview

This repo is a **git submodule container** — the actual code lives in submodules:

| Submodule | Path | Description |
|-----------|------|-------------|
| `programs_colosseum_Hackathon` | `programs_colosseum_Hackathon/` | Solana on-chain program (Anchor) |
| `AI_agente-Oracle` | `AI_agente-Oracle_colosseum_Hackathon/` | Off-chain video validation agent |

**Each submodule has its own `AGENTS.md`** — read those for detailed per-project guidance.

---

## Quick Commands

```bash
# Solana program (inside programs_colosseum_Hackathon/)
cd programs_colosseum_Hackathon && anchor build && anchor test

# Oracle agent (inside AI_agente-Oracle_colosseum_Hackathon/)
cd AI_agente-Oracle_colosseum_Hackathon && pip install -r requirements.txt && python -m src.main
```

---

## Submodule Setup (after clone)

```bash
git submodule update --init --recursive
```

---

## Cross-Cutting Rules

### Anti-Fraud Thresholds
- **Transcript**: ≥70% match required
- **Frames**: ≥3 of 5 must pass (SSIM ≥0.70)
- **Wrong channel**: No points, log reason, frontend alert
- **Foreign video**: Flag for manual slash + ban user

### Environment
- `.env` files should never be committed (each submodule has its own)
- Oracle keypair: `./keys/oracle.json` (generate separately)

---

## Key Files

| File | Purpose |
|------|---------|
| `programs_colosseum_Hackathon/programs/colosseum-hackathon/src/lib.rs` | Solana program entrypoint |
| `programs_colosseum_Hackathon/Anchor.toml` | Anchor config (devnet, wallet path) |
| `AI_agente-Oracle_colosseum_Hackathon/PLAN.md` | Full oracle workflow & thresholds |
| `AI_agente-Oracle_colosseum_Hackathon/.opencode/skills/` | Validator skills |

---

## Available Skills (Oracle Project)

| Skill | Purpose |
|-------|---------|
| `transcript-validator` | Compare video transcripts |
| `frame-validator` | Compare video frames (SSIM) |
| `channel-validator` | Verify channel ownership |