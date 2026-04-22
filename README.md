# SolCuts - Creator Economy Hardened Protocol

SolCuts is a decentralized protocol on Solana focused on the Creator Economy. It enables influencers to create **Clip Pools** with SOL prizes, rewarding video editors based on real performance metrics (views, likes, comments) tracked by oracles.

This version is **fully hardened** against fraud, supports multiple clips per editor, and uses an ultra-scalable individual claim model.

---

## Architecture Overview

SolCuts leverages Program Derived Addresses (PDAs) to ensure only the program and authorized authorities can manipulate funds and state.

### Account PDAs

| Account | Seed | Purpose |
|---------|------|---------|
| `ParticipantEntry` | `["entry", pool_pda, link_hash]` | Entry ticket for a specific clip. `link_hash` is SHA-256 of the clip URL, enabling multiple clips per user per pool. |
| `VideoPool` | `["pool", video_id_string]` | Manages prize pool, score weights, and expiration deadlines. |
| `UserProfile` | `["user_profile", authority]` | User governance state, including ban status (`is_banned`). |
| `PrizeVault` | `["vault", pool_pda]` | Holds SOL prize funds in secure custody until pool expiration. |
| `StakeAccount` | `["stake", user_pda]` | User stake for pool participation (anti-spam). |

---

## Security & Anti-Fraud

SolCuts implements immediate punishment mechanisms:

- **Slash & Ban:** The `slash_user` instruction can be invoked by Oracle or Admin upon fraud detection (e.g., botting, third-party channel links).
- **Consequences:**
  - User profile marked as `is_banned`.
  - User stake may be transferred to treasury.
  - Active pool participations are excluded from prize calculation.

### Score Weights

Pools define weighted scoring:
- Views (configurable weight)
- Likes (configurable weight)
- Comments (configurable weight)

---

## Fee Economics

| Fee Type | Value | Description |
|----------|-------|------------|
| **Creation** | 0% - 3% | Based on Creator Tier (Bronze to Platinum). |
| **Processing** | 2.5% | Retained from vault before prize distribution. |
| **Minimum Stake** | 0.15 SOL | Protects against spam and malicious behavior. |

---

## Integration Flow

### 1. Editor Participation (`join_pool`)

Pre-calculate the link hash in the frontend:

```typescript
import * as crypto from "node:crypto";

const link = "https://youtube.com/clip/abc123";
const linkHash = Array.from(crypto.createHash("sha256").update(link).digest());

await program.methods
  .joinPool(linkHash, link, "CHANNEL_ID")
  .accounts({ pool: poolPda, ... })
  .rpc();
```

### 2. Prize Claim (`claim_prize`)

Individual claim model:
1. Oracle calls `close_and_payout` to finalize pool and calculate global scores.
2. Each participant calls `claim_prize` to receive their share from `PrizeVault`.
3. Program calculates exact proportion: `(UserScore / TotalScore) * VaultBalance`.

---

## Instructions

| Instruction | Description |
|-------------|-------------|
| `create_pool` | Create a new clip pool with prize amount and score weights. |
| `join_pool` | Editor joins pool with a specific clip. |
| `update_scores` | Oracle updates scores for pool participants. |
| `close_and_payout` | Oracle closes expired pool and calculates payouts. |
| `claim_prize` | Participant claims their prize share. |
| `slash_user` | Oracle/Admin slashes fraudulent user. |
| `initialize_user` | Initialize user profile. |

---

## Local Development

This project uses a custom patch for `anchor-syn` to ensure build stability.

### Prerequisites

- Anchor CLI `>= 0.30.1`
- Solana Toolsuite

### Build & Test

```bash
# Build the program
anchor build

# Run automated tests (Localnet)
anchor test
```

---

## Project Structure

```
programs_colosseum_Hackathon/
├── programs/colosseum-hackathon/
│   ├── src/
│   │   ├── state/           # Account state definitions
│   │   ├── errors.rs       # Custom errors
│   │   └── lib.rs          # Program entrypoint
│   └── Cargo.toml
├── tests/                  # Integration tests
├── runbooks/              # Deployment runbooks
├── docs/                  # Documentation
└── migrations/            # Anchor migrations
```

---

## Documentation

- Business Rules: `docs/business-rules.md`
- Deployment Checklist: `docs/checklist.md`

---

## License

Project developed for the Colosseum Solana Hackathon.