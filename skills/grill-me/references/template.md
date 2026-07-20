# Deliverable template

Use the repository's planning location and language. If none exists, return this template in chat
unless the user requested a file. In Light mode, sections may shrink, but each remains present or is
explicitly marked not applicable.

```markdown
# <Topic> — brainstorm & implementation sketch
Date: YYYY-MM-DD. Origin: grill-me session. Status: sketch (not a full plan).
Target: <repository plan path, requested file, or chat>

## Ask & sharpened goal
Initial request verbatim; sharpened goal + Done test; unknowns surfaced (Rumsfeld)
and how each was resolved or parked.

## Directions considered
Per direction: lens, 2–4 line sketch, pre-mortem verdict, kept/killed + why.

## Chosen direction — implementation on this codebase
Files to touch (path:line anchors), change per file, order, Done-test verification.

## Impact & risks
Blast radius first: every consumer of what you touch (callers, shared
schema/contracts, background jobs, tool/API surfaces, UI, test harnesses) with
file:line; "nothing else uses this" requires a search command as evidence.
Then FMEA-lite:

| Risk | Likelihood | Impact | Treatment | Detection |

H/M/L each; Treatment = mitigate/accept/avoid/transfer + the concrete action;
Detection = how you'd notice it broke. Any H×H forces a design change, not a note.

## Uncertainties & warnings
Everything assumed or unverified, each with impact-if-wrong. Leaving this empty
claims full certainty — that claim gets checked.

## Expansions parked
Adjacent ideas deliberately not done — one line each, so they aren't relitigated.
```

This sketch is lighter than a full execution plan; if work will span sessions, adapt it to the
repository's durable planning contract.
