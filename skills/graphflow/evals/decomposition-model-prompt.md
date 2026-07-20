Read `SKILL.md` and `references/runtime-decomposition.md`. Return only the requested JSON. Classify each case using Graphflow's decision boundary; do not modify files.

For `decompose`, include a complete runtime `decomposition` proposal. For `rebase`, set `proposal` to null. Keep reasons concise.

1. `structural-execute`: Agent execute node B has an unambiguous outcome, acceptance exactly `["Implemented search sorting."]`, and locked acceptance check `CHK-B`. Its context is too broad for one pass. Parent token budget is 1000. Parent scope is read `src`, write `src/search.ts`, artifacts empty, decisions `search-sort`, forbidden `.env`. Parent consumes `sort-contract` and outputs exactly `[{"id":"search-behavior","description":"Implemented search sorting.","artifact":"src/search.ts"}]`. Split it into one read-only analysis child and one terminal implementation child without changing the contract.

2. `semantic-ambiguity`: Agent execute node C must add a delete action, but neither the goal nor approved prototype decides soft delete versus permanent deletion. The choice changes data semantics and may be irreversible.

3. `integration-redesign`: Agent integrate node E has a clear locked contract but is too complex for one context window. The worker wants to split it automatically into two integration children.
