# Named methods

Use these names as leading keywords. Combine only methods that answer a concrete uncertainty.

| Keyword | Use it for | Operational rule |
| --- | --- | --- |
| **GQM** | Measurable improvement | State a goal, derive questions, then define metrics that answer only those questions. Baseline before changing. |
| **Software Reflexion Model** | Architecture reconstruction | Write the hypothesized module/dependency model, map source entities to it, compute convergences, divergences, and absences, then iterate. |
| **Characterization Tests** | Legacy behavior preservation | Capture what the system currently does before changing seams or structure; distinguish preservation from desired-behavior tests. |
| **Information Hiding** | Module decomposition | Group design decisions likely to change behind stable interfaces; do not group only by processing sequence. |
| **Bounded Context** | Domain decomposition | Keep a model and its vocabulary internally consistent; make relationships between contexts explicit. |
| **High Cohesion / Low Coupling** | Source boundaries | Group strongly related behavior and minimize knowledge crossing the boundary. |
| **KISS / YAGNI** | Simplicity | Implement the smallest observed requirement; reject hypothetical flexibility, layers, and APIs. |
| **AHA / Rule of Three** | Abstraction timing | Search and reuse exact contracts, but delay new abstractions until real cases expose one stable concept. |
| **DRY** | Canonical knowledge | Keep each invariant or item of knowledge authoritative in one owner. |
| **Common Closure / Common Reuse** | Symbol placement | Place code by shared change reason and actual reuse set; avoid packages whose consumers need only fragments. |
| **SOLID / Law of Demeter** | OO boundary review | Apply to demonstrated object relationships and extension points; reject speculative interfaces and leaked collaborator graphs. |
| **Cyclomatic / Cognitive Complexity** | Readability and test-path risk | Use control-flow metrics as review signals, calibrated by GQM; do not optimize the score independently of behavior. |
| **CK Metrics** | OO design diagnostics | Review WMC, DIT, NOC, CBO, RFC, and LCOM as class-level prompts for complexity, coupling, inheritance, and cohesion. |
| **Ratcheting** | Legacy improvement | Freeze or improve the measured baseline; prevent new violations before attempting broad cleanup. |
| **C4** | Architecture zoom | Route readers through Context → Container → Component; use Code level only where it adds value. Never mix zoom levels. |
| **arc42 Building Block View** | Hierarchical decomposition | Describe each source boundary as a black box, then zoom into its white-box children and dependencies. |
| **ADR** | Decision provenance | Record Context, Decision, Status, and Consequences. Supersede; never erase architectural history. |
| **Diátaxis** | Documentation architecture | Separate Tutorial, How-to, Reference, and Explanation. Do not mix learning, action, lookup, and rationale in one owner. |
| **Information Foraging Theory** | Navigation efficiency | Increase information scent with precise names, paths, symbols, ownership, tests, and links; minimize navigation cost and irrelevant reads. |
| **Repository Map** | Token-bounded global context | Rank files and key symbols using the dependency graph; expose the highest-value definitions within a fixed token budget. |
| **LSP / SCIP** | Precise navigation | Prefer compiler-derived definitions, references, and symbols over lexical guesses. Fall back to structural tags, then `rg`. |

## GQM gate

Write one compact block before material setup or restructuring:

```text
Goal: <quality outcome, object, viewpoint, context>
Questions: <what must be true or improve?>
Metrics: <commands, counts, timings, graph properties, or behavior checks>
Baseline: <measured current state>
Target: <acceptance threshold>
Stop/Rollback: <condition that halts or reverses the change>
```

Do not use vanity metrics. A metric must answer a declared question and remain reproducible from the checkout or runtime.

## Reflexion loop

1. **Hypothesize:** define allowed modules and dependency directions.
2. **Map:** assign source files and symbols to those modules.
3. **Extract:** use compiler/LSP/SCIP, build metadata, or imports to recover actual relations.
4. **Compare:** label convergence, divergence, and absence.
5. **Act:** change code or revise the model with explicit evidence.
6. **Repeat:** stop only when remaining differences are intentional or recorded debt.

## Primary sources

- [Goal Question Metric, Basili et al.](https://www.cs.toronto.edu/~sme/CSC444F/handouts/GQM-paper.pdf)
- [Software Reflexion Models, Murphy, Notkin, and Sullivan](https://www.cs.ubc.ca/~murphy/papers/rm/fse95.html)
- [Working Effectively with Legacy Code, Michael Feathers](https://www.informit.com/bookstore/product.asp?isbn=9780132931755)
- [On the Criteria To Be Used in Decomposing Systems into Modules, D. L. Parnas](https://doi.org/10.1145/361598.361623)
- [Bounded Context, Martin Fowler](https://martinfowler.com/bliki/BoundedContext.html)
- [A Metrics Suite for Object Oriented Design, Chidamber and Kemerer](https://doi.org/10.1109/32.295895)
- [A Complexity Measure, Thomas McCabe](https://doi.org/10.1109/TSE.1976.233837)
- [Law of Demeter bibliography and original papers](https://www2.ccs.neu.edu/research/demeter/biblio/LoD.html)
- [Design Principles and Design Patterns, Robert C. Martin](https://web.archive.org/web/20191116231621/http://fi.ort.edu.uy/innovaportal/file/2032/1/design_principles.pdf)
- [Principles and Patterns: Common Closure and Common Reuse, Robert C. Martin](https://objectmentor.com/resources/articles/Principles_and_Patterns.pdf)
- [The Pragmatic Programmer: DRY](https://media.pragprog.com/titles/tpp20/dry.pdf)
- [AHA Programming: Avoid Hasty Abstractions, Kent C. Dodds](https://kentcdodds.com/blog/aha-progra)
- [Cognitive Complexity, SonarSource](https://www.sonarsource.com/resources/cognitive-complexity/)
- [C4 model diagrams](https://c4model.com/diagrams)
- [arc42 Building Block View](https://docs.arc42.org/section-5/)
- [Documenting Architecture Decisions, Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [Diátaxis](https://diataxis.fr/)
- [Information Foraging Theory for programmer navigation](https://web.engr.oregonstate.edu/~burnett/Reprints/TSE-IFT-2013-asprinted.pdf)
- [Aider Repository Map](https://aider.chat/docs/repomap.html)
- [Language Server Protocol](https://microsoft.github.io/language-server-protocol/)
- [SCIP Code Intelligence Protocol](https://scip-code.org/)
