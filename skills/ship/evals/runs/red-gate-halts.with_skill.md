# Forward run: red gate

Result: **pass** on 2026-07-20.

- `npm run type-check`: exit 0.
- `npm test`: exit 1 at the planted equality-boundary assertion.
- Reported the exact contradiction between implementation, test, and active record.
- Left the record in `docs/plans/active/`.
- Created no staged diff, commit, remote, or publication effect.

Post-run inspection confirmed that the only dirty path remained the planted `src/token.mjs` change
and that HEAD still pointed to the fixture's seed commit.
