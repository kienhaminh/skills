# Coding-agent entrypoints

Use this contract only when the user requests a coding-agent entrypoint or the selected tooling
requires one. The repository and tool documentation own filenames, format, scope, and precedence.

## Discover ownership

Inventory existing root and nested instruction files, generated sections, tool configuration, and
repository rules that name an authoritative owner. Read every entrypoint affected by the change.
Preserve formats and scope boundaries that are already coherent; create a new entrypoint only with
user authority or a proved tool requirement.

Complete discovery when each affected file has a named audience, scope, precedence, owner, and
generation status.

## Build the operating map

Keep always-loaded instructions compact. Link to durable owners for detail and include only the
facts an agent needs before its first action:

- repository scope and source-of-truth order;
- source areas and dependency boundaries;
- canonical setup, run, check, test, and inspection surfaces;
- repository-specific safety and authority gates;
- routing to deeper conventions, security, debugging, operations, and planning guidance.

Derive names, commands, and paths from the final checkout. Separate shared repository rules from
tool-specific protocol. A nested entrypoint should contain only a real subtree override and state how
it inherits parent rules.

Complete the map when an unfamiliar agent can select its first read and verification command without
duplicating the linked owners.

## Merge and synchronize

Apply `Read → Extract → Compare → Merge → Verify`:

1. Extract each existing rule with its intent, scope, authority, and owner.
2. Preserve stricter compatible rules and surface genuine conflicts instead of guessing precedence.
3. Put each shared fact in one durable owner and link to it from other entrypoints where the format
   supports links.
4. Keep equivalent shared sections synchronized only when repository policy requires a synchronized
   set; isolate necessary tool-specific differences under a named owner.
5. Refresh paths and commands after structural work is stable, then run repository-provided schema,
   generation, link, and drift checks.

Synchronization is complete when every changed statement is checkout-derived, each entrypoint still
matches its tool's contract, and no shared rule has conflicting active copies.
