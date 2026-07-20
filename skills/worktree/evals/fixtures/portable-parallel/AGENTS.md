# Repository contract

- Parallel feature work starts from `integration`; `develop` is the operator checkout.
- Worktrees use sibling paths and branches prefixed `task/`.
- Install with `npm ci` only when dependencies are absent or the lock changed.
- Verify with `npm test`.
- Keep the operator checkout's unrelated dirty files untouched.
- Worktree removal, pruning, and branch deletion require separate approval after clean-state proof.
