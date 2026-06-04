# Poldrack Research-Software-Engineering Principles

A distilled, reusable rubric of research-software-engineering (RSE) best practices for scientific computing, organized by area. Every criterion is phrased as a checkable statement and cites at least one supporting source post.

## Provenance

These principles were mined from Russ Poldrack's research-software-engineering blog at [russpoldrack.substack.com](https://russpoldrack.substack.com). Each criterion traces to one or more specific posts (URLs listed beneath it). Where the same principle appeared across multiple posts, the entries were merged and all citations preserved. The criteria carry stable IDs (e.g. `ST-1`, `TE-14`) so the lab can reference them directly in code reviews, audits, and onboarding.

This is a reference for lab use; it is not a substitute for reading the original posts, which contain worked examples and rationale.

_Last verified 2026-06-04 against the live blog (69 posts enumerated via sitemap): every cited slug confirmed to be a real post (zero fabricated), every criterion re-checked against the post text, overstatements trimmed, miscitations corrected, and verified missing principles added. Each added/corrected criterion was confirmed by an independent re-read of the cited post._

---

## 1. Structure

- **[ST-1] Consistent, rational folder structure.** The project adopts a single consistent, rational layout applied throughout, since a consistent organization scheme is what makes a project as easily understandable as possible.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[ST-2] Standard Python package layout with `src/<projectname>`.** Python projects are initialized as a package (e.g. `uv init --package`) so importable code lives under `src/<projectname>`, making it trivial to install the code as a module.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[ST-3] Purpose-specific top-level directories.** The project provides distinct top-level directories (`data`, `notebooks`, `results`, `scripts`, `tests`) so notebooks, executable scripts, and generated outputs are physically separated from package source.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[ST-4] All directories created up front.** Supporting directories are set up at project creation time rather than retrofitted, removing the temptation to cut corners later.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[ST-5] Flat package structure preferred.** Modules live directly under the package (flat layout) rather than in deep subpackages. Flat is simpler and keeps imports short; subpackages are introduced only when many modules form clear functional groupings.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[ST-6] Notebooks kept short and targeted.** Notebooks are short and aimed at a specific function rather than combining multiple workflows into one large notebook.
  - https://russpoldrack.substack.com/p/best-practices-for-using-jupyter

- **[ST-7] Workflow built from independently testable, swappable modules.** Workflows are composed of independent, individually testable modules that can be swapped in or out, with conceptually distinct stages (loading, QC, preprocessing, analysis, etc.) separated.
  - https://russpoldrack.substack.com/p/scientific-workflow-management
  - https://russpoldrack.substack.com/p/managing-complex-scientific-workflows

- **[ST-8] Workflow code separated from output/working directories.** Code lives in its own directory (referenced via `--snakefile`); the output/working directory is set separately (`-d`), and paths relative to the workflow are anchored with a stable prefix (e.g. `workflow.basedir`).
  - https://russpoldrack.substack.com/p/best-practices-for-snakemake-workflows

- **[ST-9] Standard workflow directory layout followed.** New workflows conform to the established standard directory layout for their workflow type.
  - https://russpoldrack.substack.com/p/best-practices-for-snakemake-workflows

- **[ST-10] No code in `__init__.py`.** `__init__.py` files are kept empty of logic, because code placed there is a common source of confusion when debugging.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[ST-11] Ordered workflow folders are numbered.** When a workflow has discrete, ordered steps, the folders are numbered (zero-padded, per SN-3) so they sort and read in execution order.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

---

## 2. Testing

- **[TE-1] Tests verify scientific correctness.** A thorough test suite exists for all important functions, with the primary goal of confirming the code produces correct answers (incorrect code can yield invalid scientific claims).
  - https://russpoldrack.substack.com/p/software-testing
  - https://russpoldrack.substack.com/p/defensive-coding

- **[TE-2] Tests provide a measure of task completion.** A test suite gives the coder an objective measure of when a task is done and helps prevent generating excessive or extraneous code.
  - https://russpoldrack.substack.com/p/software-testing

- **[TE-3] Unit tests for individual components.** Unit tests assess whether individual components behave as expected, isolating failures to a specific piece of code.
  - https://russpoldrack.substack.com/p/software-testing

- **[TE-4] Boundary and problematic inputs tested.** Tests cover boundary conditions and malformed inputs, aiming for "garbage in, exception out" — invalid input raises an exception rather than returning a wrong answer, and the test asserts that the expected exception is raised.
  - https://russpoldrack.substack.com/p/software-testing
  - https://russpoldrack.substack.com/p/defensive-coding

- **[TE-5] Integration and smoke tests exist.** Integration tests exercise the whole application with all components together, including simple smoke tests that confirm it runs without crashing. Scientific workflows are tested with both unit tests and an end-to-end integration test on a minimal test dataset.
  - https://russpoldrack.substack.com/p/software-testing
  - https://russpoldrack.substack.com/p/workflow-testing-strategies

- **[TE-6] Bugs get regression tests.** Every encountered bug gets a regression test that reproduces it so it can never silently return. (Writing the test before the fix is covered under TE-18/TDD.)
  - https://russpoldrack.substack.com/p/software-testing

- **[TE-7] Given/when/then structure; one thing per test.** Each test sets up a situation, performs an action, then asserts the outcome, and tests only one thing so failures are unambiguous.
  - https://russpoldrack.substack.com/p/the-structure-of-a-good-software

- **[TE-8] Correctness validated against an oracle.** Correctness is checked using whatever ground truth is available: known input/output pairs, a trusted reference implementation, a parallel independent implementation, or statistical behavior over repeated runs.
  - https://russpoldrack.substack.com/p/the-structure-of-a-good-software
  - https://russpoldrack.substack.com/p/property-based-testing

- **[TE-9] Black-box tests independent of internals.** Tests depend only on the input/output relationship, not internal implementation details, so harmless refactors do not break them.
  - https://russpoldrack.substack.com/p/the-structure-of-a-good-software

- **[TE-10] Tests are independent and isolated.** Tests set up their needed structure locally, share no mutable state, and run in any order (and in parallel) without affecting each other.
  - https://russpoldrack.substack.com/p/the-structure-of-a-good-software
  - https://russpoldrack.substack.com/p/optimizing-the-testing-workflow

- **[TE-11] Fast/slow test separation and fast feedback loop.** Fast unit tests run frequently during development (often only the tests for the function under work), slow integration tests less often; `pytest --ff` (failed-first — preferred over `--lf` for general use because it still runs all tests while prioritizing the previous failures) shortens the debug loop.
  - https://russpoldrack.substack.com/p/optimizing-the-testing-workflow

- **[TE-12] Minimal mock datasets for speed.** Small synthetic/mock datasets exercise functions without the runtime cost of full real data.
  - https://russpoldrack.substack.com/p/optimizing-the-testing-workflow

- **[TE-13] Continuous integration on a clean machine.** CI runs the suite automatically on every push on a clean VM, catching regressions and "works on my machine" problems, across all supported language versions.
  - https://russpoldrack.substack.com/p/automated-testing-with-github-actions

- **[TE-14] Property-based testing for problematic/numerical inputs.** Property-based testing generates many random in-domain inputs to check the code handles edge cases gracefully (e.g. division by zero), using `assume()`/range restriction to keep cases realistic; especially valuable for mathematical code.
  - https://russpoldrack.substack.com/p/property-based-testing
  - https://russpoldrack.substack.com/p/workflow-testing-strategies

- **[TE-15] Parameterized tests instead of duplicated cases.** When checking a function across many known input combinations, `@pytest.mark.parametrize` is used rather than duplicating test code.
  - https://russpoldrack.substack.com/p/parameterized-testing

- **[TE-16] Fixtures for shared/expensive setup, never mutated.** Pytest fixtures create a single shared instance of expensive setup; a shared/session-scope fixture is copied before any modification to preserve isolation.
  - https://russpoldrack.substack.com/p/test-fixtures-and-mocking
  - https://russpoldrack.substack.com/p/workflow-testing-strategies

- **[TE-17] External systems mocked in unit tests, real in integration tests.** Live external APIs/systems are mocked in unit tests (for speed and reliability), but integration and smoke tests run without mocking so real interaction errors are caught.
  - https://russpoldrack.substack.com/p/parameterized-testing
  - https://russpoldrack.substack.com/p/test-fixtures-and-mocking

- **[TE-18] TDD practiced.** Tests are written first, an empty implementation confirms they fail, then code is written to pass; for each function, valid, empty, and exception-raising cases are tested (e.g. via `pytest.raises`).
  - https://russpoldrack.substack.com/p/test-driven-development-and-ai-assisted

- **[TE-19] Coverage not chased as a goal.** 100% coverage is not treated as proof of correctness; instead the most likely real-world cases are tested.
  - https://russpoldrack.substack.com/p/test-driven-development-and-ai-assisted

- **[TE-20] AI-generated tests reviewed by a domain expert.** A knowledgeable human reviews AI-generated tests in detail to confirm the expected values are correct and that the tests actually exercise the relevant functions (AI emits plausible-but-wrong assertions).
  - https://russpoldrack.substack.com/p/the-challenges-of-ai-generated-tests
  - https://russpoldrack.substack.com/p/workflow-testing-strategies

- **[TE-21] No "happy path" tests.** Tests do not merely confirm success; they assert that the intended operation actually occurred and cover realistic failure cases, using domain knowledge to choose them.
  - https://russpoldrack.substack.com/p/workflow-testing-strategies

- **[TE-22] Reliability vs validity distinguished; validity established via simulation.** Reproducible results (reliability) are distinguished from correct results (validity); simulations with known ground truth are used to confirm the code recovers true parameters.
  - https://russpoldrack.substack.com/p/validating-scientific-software-using-26c

- **[TE-23] Precondition assertions on bounded variables.** Assertions check preconditions wherever a variable has bounded acceptable values (counts non-negative, times positive, discrete values in an allowed set).
  - https://russpoldrack.substack.com/p/defensive-coding

- **[TE-24] Workflows linted and dry-run before execution.** Workflow files are linted and a dry run inspects the execution graph before any real execution, catching structural problems early.
  - https://russpoldrack.substack.com/p/workflow-management-using-snakemake
  - https://russpoldrack.substack.com/p/best-practices-for-snakemake-workflows

- **[TE-25] Validation procedures built into the workflow.** The workflow includes validation procedures guarding against known problems and edge cases.
  - https://russpoldrack.substack.com/p/scientific-workflow-management

- **[TE-26] Standard test-discovery conventions followed.** A dedicated framework (pytest) is used, and its discovery conventions are honored: test files are named `test_*.py`/`*_test.py` and test functions are prefixed with `test`.
  - https://russpoldrack.substack.com/p/the-challenges-of-ai-generated-tests

- **[TE-27] Test groups marked and selected with custom markers.** Custom markers (e.g. `unit`, `integration`) are defined in `pyproject.toml` and selected/deselected with the `-m` flag, so groups can be run independently.
  - https://russpoldrack.substack.com/p/optimizing-the-testing-workflow

- **[TE-28] Tests run in parallel across cores.** The `pytest-xdist` plugin (`-n auto`) distributes tests across available CPU cores to reduce total testing time.
  - https://russpoldrack.substack.com/p/optimizing-the-testing-workflow

- **[TE-29] Slow tests ordered last; per-test time measured.** Tests are ordered so the slowest run last (or slow tests are deselected by marker) so a quick failure is not delayed behind long-running tests; `pytest --durations` measures per-test time.
  - https://russpoldrack.substack.com/p/optimizing-the-testing-workflow

- **[TE-30] `pytest.skip()` not used to mask failures.** Skipping is reserved for genuinely inapplicable tests; outcomes that should fail trigger a real failure rather than a silent skip.
  - https://russpoldrack.substack.com/p/workflow-testing-strategies

- **[TE-31] Coverage measured as a diagnostic.** A coverage tool (e.g. `pytest-cov`) identifies code not exercised by tests, used as a diagnostic to find gaps — not as a success metric (see TE-19).
  - https://russpoldrack.substack.com/p/test-driven-development-and-ai-assisted

- **[TE-32] Unit tests at commit, integration tests on CI push.** Fast unit tests run at commit time (e.g. as pre-commit items); slower integration tests run automatically on the CI system when code is pushed.
  - https://russpoldrack.substack.com/p/optimizing-the-testing-workflow

- **[TE-33] External calls mocked via monkeypatch; mocking verified.** `monkeypatch` (or mock objects) replaces real external calls (APIs, databases) with controlled fakes returning predictable responses; the mocking is verified by confirming the test still passes with the network disabled.
  - https://russpoldrack.substack.com/p/test-fixtures-and-mocking

- **[TE-34] Fixtures do setup only; the test executes and asserts.** A fixture performs only setup/mocking; the function under test is called from the test body (not the fixture), keeping the arrange/act boundary clear.
  - https://russpoldrack.substack.com/p/test-fixtures-and-mocking

- **[TE-35] Extensions of standard code checked against the reference.** Standard-library code is not reimplemented; when existing code is extended, a test confirms the basic (reference) behavior still holds.
  - https://russpoldrack.substack.com/p/the-structure-of-a-good-software

---

## 3. Documentation

- **[DO-1] README records project-specific conventions.** A README documents any project-specific definitions/conventions (e.g. what counts as "raw" vs "preprocessed") so it is clear what goes where.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[DO-2] Workflows documented for motivation, design, and usage.** Documentation covers the scientific motivation, technical design, and how to run the workflow, so others (including your future self) can maintain, update, and extend it.
  - https://russpoldrack.substack.com/p/scientific-workflow-management

- **[DO-3] Self-contained shareable report generated.** A single self-contained report (e.g. an HTML file with embedded figures) is produced for sharing results, with relevant outputs marked for inclusion.
  - https://russpoldrack.substack.com/p/best-practices-for-snakemake-workflows

- **[DO-4] Clear code over comments; bad code rewritten, not commented.** Clear, expressive code with few comments is preferred over cluttered code with many comments; bad code is rewritten rather than explained by a comment.
  - https://russpoldrack.substack.com/p/clean-coding

- **[DO-5] Comments reserved for non-obvious rationale.** Nothing already clear from code structure or names is commented; comments are reserved for important design choices and for documenting the motivation behind chosen constant values.
  - https://russpoldrack.substack.com/p/clean-coding

- **[DO-6] Version control, not comments, records history.** Change history is tracked in version control rather than recorded in code comments.
  - https://russpoldrack.substack.com/p/clean-coding

- **[DO-7] Known issues marked with searchable TODO.** Outstanding work is marked with a searchable `TODO` heading in comments.
  - https://russpoldrack.substack.com/p/clean-coding

- **[DO-8] Single problems-tracking file during agentic coding.** Major requests/open issues are recorded in one tracked file (e.g. `problems_tbd.md`) with `[ ]`/`[x]` markers; it is cleared when moving to a different part of the code, and items are marked fixed only after the user confirms the fix worked.
  - https://russpoldrack.substack.com/p/a-better-way-to-track-problem-solving

- **[DO-9] Metadata is machine-readable and self-sufficient.** Metadata is provided in a structured, machine-readable format sufficient for someone to understand and reuse the dataset using only the metadata provided; when attributes such as units of measurement or links to ontologies are needed, JSON-LD is preferred over plain JSON to link metadata to controlled vocabularies/ontologies.
  - https://russpoldrack.substack.com/p/metadata-data-documentation-and-provenance

- **[DO-10] Data dictionaries/codebooks generated at dataset creation.** A data dictionary giving each variable's description, data type, and allowable value range is generated when the dataset is created (not later, when details are lost).
  - https://russpoldrack.substack.com/p/metadata-data-documentation-and-provenance

---

## 4. Reproducibility

- **[RE-1] Workflow rerunnable from scratch to the same answer.** The workflow can be rerun from scratch on the same data and produce the same result, allowing only for uncontrollable factors (floating-point, OS differences).
  - https://russpoldrack.substack.com/p/scientific-workflow-management

- **[RE-2] Requirements explicitly specified.** All dependencies are declared in an explicit file (`pyproject.toml`, `requirements.txt`, environment YAML, or `Dockerfile`).
  - https://russpoldrack.substack.com/p/scientific-workflow-management
  - https://russpoldrack.substack.com/p/reproducible-environments-with-snakemake

- **[RE-3] Exact package versions pinned.** Specific package versions are pinned in the environment file (e.g. `numpy=2.4.0`) to prevent dependency drift.
  - https://russpoldrack.substack.com/p/reproducible-environments-with-snakemake

- **[RE-4] Containers pin an explicit version; never `latest`.** Container image references always specify a valid explicit version and never use the floating `latest` tag (which binds the environment to the download date).
  - https://russpoldrack.substack.com/p/using-containers-for-reproducible
  - https://russpoldrack.substack.com/p/reproducible-environments-with-snakemake

- **[RE-5] Container/environment as the shareable artifact.** A container image is treated as the shareable software artifact and is the most reproducible distribution mechanism because it fixes the dependencies; a container or a managed Conda environment ensures a consistent, reproducible execution environment across systems.
  - https://russpoldrack.substack.com/p/using-containers-for-reproducible
  - https://russpoldrack.substack.com/p/reproducible-environments-with-snakemake

- **[RE-6] Code under public version control.** All code is under version control and hosted on a public repository such as GitHub.
  - https://russpoldrack.substack.com/p/scientific-workflow-management

- **[RE-7] Code is portable across machines.** Code is written to run on other machines and to be exercised by automated testing tools, without machine-specific assumptions (e.g. paths built with `pathlib`, no hardcoded OS-specific separators).
  - https://russpoldrack.substack.com/p/the-goals-of-a-scientific-software
  - https://russpoldrack.substack.com/p/coding-portably
  - https://russpoldrack.substack.com/p/automated-testing-with-github-actions

- **[RE-8] Workflows are resumable via checkpointing.** Intermediate state is stored per step so completed steps need not rerun after a failure; the engine reruns only downstream nodes affected by a change.
  - https://russpoldrack.substack.com/p/managing-complex-scientific-workflows
  - https://russpoldrack.substack.com/p/using-a-workflow-engine

- **[RE-9] Workflows are idempotent.** Steps produce the same result on repeated runs by overwriting outputs completely rather than appending.
  - https://russpoldrack.substack.com/p/managing-complex-scientific-workflows

- **[RE-10] Simulation seeds fixed and robustness checked.** Random seeds are set for exact reproducibility, and results are also verified to be robust across different seeds.
  - https://russpoldrack.substack.com/p/validating-scientific-software-using-26c

- **[RE-11] Notebook environment managed and fully re-runnable.** Notebooks use an environment manager, and a fresh-kernel full run is the definitive check that the notebook works; the `autoreload` magic is avoided because it obscures which code produced which output.
  - https://russpoldrack.substack.com/p/best-practices-for-using-jupyter

- **[RE-12] Notebooks version-controlled as plain Python.** Notebooks are converted to plain Python (e.g. jupytext `py:percent`) before committing, applied as a pre-commit hook with `.ipynb` files unstaged so only Python files enter git history.
  - https://russpoldrack.substack.com/p/version-control-and-jupyter-notebooks

- **[RE-13] Beware hidden workflow state.** Hidden state in the engine's metadata directory (e.g. `.snakemake`) is accounted for when debugging, and imported-module changes are handled by forcing a rerun since dependency tracking misses them.
  - https://russpoldrack.substack.com/p/workflow-management-using-snakemake

- **[RE-14] Parametric sweeps run through the same workflow.** All sweep runs execute inside the same single workflow (not as separate jobs), guaranteeing an identical software environment across runs for comparability.
  - https://russpoldrack.substack.com/p/managing-complex-scientific-workflows

- **[RE-15] Workflow fails fast and loudly.** When there is a problem the workflow fails quickly with explicit error messages rather than propagating bad results.
  - https://russpoldrack.substack.com/p/scientific-workflow-management

- **[RE-16] Randomness via an explicit RNG object.** Random numbers are drawn from an explicit generator object (`np.random.default_rng()`) whose methods are called, rather than the legacy global `np.random.seed()` interface, and the specific generator in use is understood.
  - https://russpoldrack.substack.com/p/validating-scientific-software-using-26c

- **[RE-17] Reuse an existing container image when one exists.** An existing public (e.g. Docker Hub) image that already contains the required dependencies is reused rather than built from scratch, since this is the easiest path to a reproducible environment.
  - https://russpoldrack.substack.com/p/reproducible-environments-with-snakemake

- **[RE-18] Expensive results pre-computed and reused.** The workflow pre-computes and caches results from expensive operations, rerunning a step only when one of its inputs changes, so reruns are fast and deterministic.
  - https://russpoldrack.substack.com/p/scientific-workflow-management

---

## 5. Scripts vs. Package

- **[SP-1] Reusable functions live in importable modules, not notebooks.** Reusable functions are moved out of notebooks into a Python module and imported, eliminating accidental access to notebook-global variables and making the functions testable. This is done as early as possible.
  - https://russpoldrack.substack.com/p/best-practices-for-using-jupyter
  - https://russpoldrack.substack.com/p/computational-notebooks

- **[SP-2] Notebooks used only for prototyping and visualization.** Notebooks are used for rapid prototyping/exploration and to visualize results, not as the home of production analysis code; once a piece of code is worth keeping, it is transitioned into a Python script or module.
  - https://russpoldrack.substack.com/p/computational-notebooks

- **[SP-3] Implementation lives in modules, not the notebook.** When a notebook drives a workflow, the components (including visualization code) are implemented as separate, standalone, importable modules, so the notebook contains little implementation itself.
  - https://russpoldrack.substack.com/p/computational-notebooks

- **[SP-4] Notebooks converted to scripts for pipeline use.** Exploratory notebooks are converted to plain Python (e.g. via jupytext) for use in a workflow, replacing blocking interactive calls (`plt.show()`) with non-interactive equivalents (`plt.savefig()`).
  - https://russpoldrack.substack.com/p/managing-complex-scientific-workflows
  - https://russpoldrack.substack.com/p/computational-notebooks

- **[SP-5] Executable scripts kept in scripts/.** Standalone executable drivers (e.g. bash scripts) live in a dedicated `scripts/` directory, distinct from the importable package.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[SP-6] Python scripts exposed as package entrypoints.** Standalone Python scripts are wired through uv's `project.scripts`, pointing at a specific function within a module as the entrypoint, rather than left as loose runnable files.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[SP-7] Pure Python preferred over running notebooks as literate programs.** When operationalizing notebook code, pure Python is generated (e.g. jupytext `py:percent`) rather than executing the `.ipynb` itself as a literate program via nbconvert.
  - https://russpoldrack.substack.com/p/computational-notebooks

---

## 6. Data Management

- **[DM-1] Use a consistent, machine-readable, standard organization scheme.** A consistent data organization scheme is used; if a standard exists in the field (e.g. BIDS), it is strongly preferred over inventing one. Both workflow files and data files follow established standards.
  - https://russpoldrack.substack.com/p/data-organization-schemes
  - https://russpoldrack.substack.com/p/scientific-workflow-management

- **[DM-2] Standard file formats for inputs and outputs.** Workflow inputs and outputs use established standard file formats rather than invented ones.
  - https://russpoldrack.substack.com/p/scientific-workflow-management

- **[DM-3] Data location chosen by size.** Small data may live in a subdirectory of the project; large datasets are kept separate from the code in a dedicated storage location to avoid filesystem/space problems.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[DM-4] File granularity matches access pattern.** Many small files are used when only small portions are accessed; data is consolidated into larger files when typically combined. On HPC systems with inode quotas, fewer/larger files are favored to avoid millions of small files.
  - https://russpoldrack.substack.com/p/data-organization-schemes

- **[DM-5] Original/raw data stored read-only.** Input/original data is stored in a dedicated read-only ("locked") location so modifications require an explicit permissions change, applying least privilege to data access.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific
  - https://russpoldrack.substack.com/p/managing-original-data-and-data-access
  - https://russpoldrack.substack.com/p/version-control-for-data

- **[DM-6] Original-data integrity verified by checksums.** A checksum (a fingerprint of the file contents that changes if the data change) is computed for each original file, and the checksum method used (e.g. MD5 vs SHA-1) is documented, since different methods yield different values.
  - https://russpoldrack.substack.com/p/managing-original-data-and-data-access

- **[DM-7] Redundant, geographically separate backups; RAID is not backup.** Original data (and anything not recreatable from it) is stored on at least two independent systems, with a geographically separate backup; RAID is never treated as a substitute for backup and is actively monitored if used.
  - https://russpoldrack.substack.com/p/managing-original-data-and-data-access
  - https://russpoldrack.substack.com/p/storing-research-data

- **[DM-8] Never rely solely on a personal computer.** Research data is never stored solely on a researcher's own computer; data not recreatable from originals lives on at least two independent systems, and code is stored on a center-backed partition and also pushed to GitHub.
  - https://russpoldrack.substack.com/p/storing-research-data

- **[DM-9] Long-term archiving in a preservation repository.** Data is archived as long as possible (meeting funder requirements) in a location with a long-term preservation policy and verifiability (institutional/domain repositories); single physical drives and sole commercial-cloud reliance are avoided.
  - https://russpoldrack.substack.com/p/archiving-research-data

- **[DM-10] Data management plan from project inception.** A data management plan is created at the start of every project, and saved data is independently loaded and checked rather than assuming the saving code worked.
  - https://russpoldrack.substack.com/p/data-management

- **[DM-11] Data made FAIR.** Data is Findable (persistent DOI, searchable repository, machine-readable metadata), Accessible (standard protocols, metadata exposed even when raw data restricted, clear access requirements), Interoperable (standard formats and vocabularies), and Reusable (clear license, comprehensive provenance description).
  - https://russpoldrack.substack.com/p/data-management

- **[DM-12] Sensitive data protected.** Sensitive data is encrypted at rest, transferred only over encrypted channels, and kept on IT-run security-certified systems (e.g. NIST SP 800-171 where a DUA requires it) with controlled access; HIPAA Safe Harbor deidentification is applied, and differential privacy is considered for large datasets.
  - https://russpoldrack.substack.com/p/handling-sensitive-data

- **[DM-13] Data versioned with the right tool.** Small text datasets (under a few MB, CSV/TSV) are versioned with git; large/binary datasets use a tool built for them (DataLad). Ad-hoc filename versioning (`dataset_new_fixed_v2.tsv`) is avoided.
  - https://russpoldrack.substack.com/p/version-control-for-data

- **[DM-14] Quality control established at study start.** Data quality-control measures are put in place at the very beginning of a study, because problems not caught at the start may not be discovered until it is too late.
  - https://russpoldrack.substack.com/p/data-management

- **[DM-15] New-study data checklist.** A checklist is developed for each new study to ensure data are collected and stored properly.
  - https://russpoldrack.substack.com/p/data-management

- **[DM-16] Read-only protection even on single-user systems.** Read-only restrictions are applied to original data even on single-user systems, to prevent accidental modification or deletion.
  - https://russpoldrack.substack.com/p/managing-original-data-and-data-access

- **[DM-17] Redundant copies on different drive models.** When redundant archival copies are kept on physical drives, different drive models are used so a common hardware defect cannot take out all copies at once.
  - https://russpoldrack.substack.com/p/archiving-research-data

- **[DM-18] Obsolescence-prone media avoided.** Archival media prone to format obsolescence (DVDs, cartridge disks) are avoided except as a redundant backup.
  - https://russpoldrack.substack.com/p/archiving-research-data

- **[DM-19] Safeguards for non-ACID databases.** When a non-ACID-compliant (e.g. NoSQL) database is used, appropriate safeguards are put in place to protect data integrity.
  - https://russpoldrack.substack.com/p/storing-research-data

- **[DM-20] Cloud object stores accessed from co-located compute.** A cloud object store is accessed from compute hosted by the same provider/datacenter rather than from a local machine, because remote access is slow and costly.
  - https://russpoldrack.substack.com/p/storing-research-data

- **[DM-21] File format matched to the data type.** A standard file format appropriate to the data's structure is chosen — tabular formats (e.g. Parquet/Arrow) for tables, array formats (e.g. HDF5/Zarr/NetCDF) for multidimensional data, and dedicated formats for graph/network and other specialized data — rather than forcing all data into one format.
  - https://russpoldrack.substack.com/p/data-formats-and-file-types-tabular
  - https://russpoldrack.substack.com/p/data-formats-and-file-types-multidimensional
  - https://russpoldrack.substack.com/p/networkgraph-data-and-other-specialized

---

## 7. Style & Naming

- **[SN-1] BIDS-style key-value names.** Files/folders use key-value pairs separated by underscores with a type suffix (`<key>-<value>_<key>-<value>_suffix.extension`), used whenever more than one parameter varies, so names parse automatically.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific
  - https://russpoldrack.substack.com/p/data-organization-schemes

- **[SN-2] Delimiters reserved.** The delimiter characters `-` and `_` never appear inside values, keeping names unambiguously parseable.
  - https://russpoldrack.substack.com/p/data-organization-schemes
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[SN-3] Zero-padded numbers.** Numbers in names are zero-padded with enough width to cover all possible values so files sort correctly (e.g. `figure-01`).
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[SN-4] Specific, accurately-used folder names.** Folder names are as specific and accurate as possible, and each folder is used only for its stated purpose.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[SN-5] One concept, one name.** Each concept is represented by a single unique name (no synonyms for the same thing).
  - https://russpoldrack.substack.com/p/clean-coding

- **[SN-6] Explicit imports, no wildcards.** Specific functions are imported explicitly rather than via wildcard imports, keeping dependencies transparent and avoiding namespace collisions.
  - https://russpoldrack.substack.com/p/clean-coding

- **[SN-7] Readability prioritized.** Code is written primarily for humans to read and understand (which also helps language models infer its intent); readability is treated as one of the most important features of good code.
  - https://russpoldrack.substack.com/p/the-goals-of-a-scientific-software
  - https://russpoldrack.substack.com/p/clean-coding

- **[SN-8] Workflow files linted and auto-formatted.** Workflow/config files are linted (`snakemake --lint`) and auto-formatted (`snakefmt`), analogous to how a linter like `ruff`/`flake8` checks Python.
  - https://russpoldrack.substack.com/p/best-practices-for-snakemake-workflows

- **[SN-9] Pipeline steps formatted explicitly.** Method-chained/pipeline code is formatted to make each step explicit (e.g. wrapping in parentheses, one step per line) for readability.
  - https://russpoldrack.substack.com/p/streaming-workflows-and-method-chaining

- **[SN-10] Names describe the concept accurately.** A name describes the concept it represents — neither too vague nor too specific, neither too short nor too long, easy to use in speech, and not clever or reliant on temporary/culturally-specific concepts.
  - https://russpoldrack.substack.com/p/clean-coding

- **[SN-11] Verbs for functions, nouns for variables.** Functions are named with verbs and variables/classes with nouns; a function's name highlights its intended use rather than its implementation details.
  - https://russpoldrack.substack.com/p/clean-coding

- **[SN-12] Name length scaled to scope; correct pluralization.** A variable name's length is proportional to the size of its scope, and a pluralized name is used only for a variable that holds more than one item.
  - https://russpoldrack.substack.com/p/clean-coding

- **[SN-13] Vertical whitespace separates concepts.** Vertical empty space is used judiciously to separate conceptually distinct sections of code, without spreading code needlessly across many pages.
  - https://russpoldrack.substack.com/p/clean-coding

- **[SN-14] Names are machine-readable.** File and folder names are machine-readable so automated tools can parse and process large datasets (the foundation behind SN-1/SN-2).
  - https://russpoldrack.substack.com/p/data-organization-schemes

- **[SN-15] Global mutable variables avoided.** State is passed explicitly through function arguments and return values rather than via global variables, which create hidden dependencies and make code hard to test and reason about.
  - https://russpoldrack.substack.com/p/global-variables

- **[SN-16] Formatting, linting, and type-checking automated.** Python is auto-formatted and linted (e.g. `ruff`/`black`/`flake8`) and optionally type-checked, with these tools run automatically (e.g. as pre-commit hooks) so style is enforced consistently rather than by hand.
  - https://russpoldrack.substack.com/p/code-formatting-tools
  - https://russpoldrack.substack.com/p/essential-tools-for-writing-better

---

## 8. Refactoring

- **[RF-1] Modularity via defined interfaces and information hiding.** Code is decomposed based on information hiding (hiding decisions behind interfaces) rather than mirroring the problem's logical flowchart, into components that interact only through defined interfaces with internal details encapsulated — because information-hiding decomposition is far easier to modify.
  - https://russpoldrack.substack.com/p/modularity-and-the-god-object

- **[RF-2] Single responsibility.** Each function or class has a single, cohesive purpose at the appropriate level of abstraction.
  - https://russpoldrack.substack.com/p/modularity-and-the-god-object

- **[RF-3] No "God object".** Large classes that couple all processing to their internal state are avoided; configuration/data is held in data classes while processing lives in standalone functions.
  - https://russpoldrack.substack.com/p/modularity-and-the-god-object

- **[RF-4] No coupling that defeats independent testing.** Components avoid direct file/external-system access, temporal dependencies on earlier steps having run, and coupling of processing to mutable class state — so each operation can be tested independently.
  - https://russpoldrack.substack.com/p/modularity-and-the-god-object

- **[RF-5] Large functions broken into smaller ones.** Large functions are split into several smaller functions so the logical structure is clear.
  - https://russpoldrack.substack.com/p/principles-of-software-engineering

- **[RF-6] DRY: no duplication, no magic numbers.** Repeated logic is extracted into reusable functions (a change is made in one place); numbered-variable patterns are replaced by a function over a collection, and magic numbers are assigned to named variables.
  - https://russpoldrack.substack.com/p/clean-coding

- **[RF-7] No in-place mutation; copy inputs.** Functions copy any object passed in and operate on the copy rather than mutating inputs in place; where mutation is unavoidable it is signaled loudly (e.g. `inplace` in the name), and immutable types are used to prevent it entirely.
  - https://russpoldrack.substack.com/p/managing-complex-scientific-workflows

- **[RF-8] No complex functions inside method chains.** Complex functions are kept out of method chains because chains are very hard to debug.
  - https://russpoldrack.substack.com/p/streaming-workflows-and-method-chaining

- **[RF-9] Dependency maintenance health evaluated before adoption.** Before relying on a third-party package, its maintenance quality is assessed (multiple active contributors, automated testing with high coverage, testing across recent language versions, responsive issues page), with more scrutiny the more the code will be reused, and a plan for what happens if it is abandoned.
  - https://russpoldrack.substack.com/p/managing-technical-debt
  - https://russpoldrack.substack.com/p/optimizing-the-testing-workflow
  - https://russpoldrack.substack.com/p/test-driven-development-and-ai-assisted

- **[RF-10] Refactoring preserves external behavior.** Refactoring means modifying code (e.g. breaking large functions into smaller ones) to improve internal structure and clarity while keeping its input/output behavior unchanged.
  - https://russpoldrack.substack.com/p/principles-of-software-engineering

- **[RF-11] A solid test suite precedes refactoring.** Refactoring (especially when delegated to AI tools) is undertaken only once a solid testing program exists to catch any behavior changes.
  - https://russpoldrack.substack.com/p/principles-of-software-engineering

- **[RF-12] Constructors hold configuration, not setup work.** Constructors carry only high-level configuration; time-consuming operations and distinct setup steps are extracted into their own methods/functions so initialization stays cheap and does not mix levels of abstraction.
  - https://russpoldrack.substack.com/p/modularity-and-the-god-object

- **[RF-13] Standalone functions preferred over class methods for processing.** Processing operations are implemented as separate standalone functions rather than methods coupled to class state, separating responsibilities and letting each operation be tested in isolation.
  - https://russpoldrack.substack.com/p/modularity-and-the-god-object

---

## 9. Config

- **[CF-1] No hardcoded data paths; location parameterized.** Data locations are parameterized (e.g. a `.env` or local config file) rather than hardcoded, so the code can let the data live in an arbitrary location without edits.
  - https://russpoldrack.substack.com/p/project-structure-for-scientific

- **[CF-2] Long parameter lists replaced by a config object.** A configuration object (e.g. a Python dataclass) holds parameters instead of long function-signature parameter lists, keeping configuration separate from data.
  - https://russpoldrack.substack.com/p/clean-coding
  - https://russpoldrack.substack.com/p/modularity-and-the-god-object

- **[CF-3] Notebook parameters centralized at the top.** All notebook parameters/settings are defined in a single cell at the top so changes propagate consistently.
  - https://russpoldrack.substack.com/p/best-practices-for-using-jupyter

- **[CF-4] Smart defaults, easy overrides.** The workflow uses smart defaults but lets users easily change the configuration, and supports parameterized runs whose outputs are separately tracked.
  - https://russpoldrack.substack.com/p/scientific-workflow-management

- **[CF-5] Config files hold configuration, not runtime parameters.** Durable workflow configuration is stored in config files (e.g. `config.yaml`); per-run runtime parameters (core count, output directory) are passed via command-line arguments, keeping the config file an accurate single source of truth. Example configuration files are included in the repository.
  - https://russpoldrack.substack.com/p/best-practices-for-snakemake-workflows
  - https://russpoldrack.substack.com/p/scientific-workflow-management

- **[CF-6] Environment/container defined once and referenced.** The container image or environment is defined once in config and referenced from the workflow rather than repeated.
  - https://russpoldrack.substack.com/p/reproducible-environments-with-snakemake

- **[CF-7] Sweep outputs organized for downstream processing.** Outputs of parametric sweeps are organized so they can be easily processed downstream.
  - https://russpoldrack.substack.com/p/managing-complex-scientific-workflows

- **[CF-8] Module code reads from the config file.** Workflow parameters live in a separate (e.g. YAML) configuration file rather than hardcoded; each module is wrapped in a script that reads its settings from that config so every step stays configuration-driven.
  - https://russpoldrack.substack.com/p/workflow-management-using-snakemake

- **[CF-9] Sweeps expressed in config, expanded by wildcards.** Parametric sweeps are implemented by listing the parameter values in the configuration file and expanding them with wildcards in rule inputs/outputs, rather than by editing code or hand-spawning separate jobs.
  - https://russpoldrack.substack.com/p/managing-complex-scientific-workflows

---

## 10. Provenance (cross-cutting; reproducibility/data-management)

- **[PV-1] Provenance recorded for every output.** For each generated file, provenance is captured: origin of original data, specific input files, exact software versions, and the exact settings used; and how each file came to be and what it depended on.
  - https://russpoldrack.substack.com/p/metadata-data-documentation-and-provenance
  - https://russpoldrack.substack.com/p/tracking-provenance-in-workflows

- **[PV-2] Automatic provenance capture preferred.** A workflow engine that automatically stores rich provenance metadata is preferred over manual documentation, ideally emitting a standard representation (e.g. PROV); all operations are logged.
  - https://russpoldrack.substack.com/p/tracking-provenance-in-workflows
  - https://russpoldrack.substack.com/p/scientific-workflow-management

- **[PV-3] Data-producing commands captured.** Data-producing commands are run in a way that records them — `datalad run` auto-fetches/unlocks the inputs, runs the command, recommits the outputs, and records the exact command — and source URLs are logged (e.g. `datalad download-url`) for traceability.
  - https://russpoldrack.substack.com/p/version-control-for-data

- **[PV-4] Derived-data changes tracked in version control.** Changes to derived/working data are recorded in version control capturing the what, when, and why of every change, rather than encoded into filenames (`dataset_new_fixed_v2.tsv`), so it is always known exactly which data an analysis used.
  - https://russpoldrack.substack.com/p/version-control-for-data

---

## 11. General Engineering (cross-cutting)

- **[GE-1] YAGNI.** Only code that solves the problem at hand is built — no speculative features.
  - https://russpoldrack.substack.com/p/principles-of-software-engineering

- **[GE-2] MVP first, then refactor and document.** Development is iterative: get a minimum viable product working that solves the problem at hand (no more, no less), then — especially for code that will be reused — spend time refactoring for clarity and robustness and adding documentation.
  - https://russpoldrack.substack.com/p/the-goals-of-a-scientific-software
  - https://russpoldrack.substack.com/p/principles-of-software-engineering

- **[GE-3] Reuse existing tools before building your own.** The first inclination is to find an existing tool (e.g. a workflow engine) that solves the problem rather than building custom infrastructure; well-established, actively maintained, broadly adopted tools are preferred.
  - https://russpoldrack.substack.com/p/managing-complex-scientific-workflows
  - https://russpoldrack.substack.com/p/using-a-workflow-engine
  - https://russpoldrack.substack.com/p/workflow-management-using-snakemake

- **[GE-4] Fail loudly on errors.** Code detects errors and announces them loudly (raising exceptions / failing fast) rather than silently returning `None` or a default, so problems are caught immediately. Common scientific error sources are actively guarded against: the wrong algorithm chosen so the data violate its assumptions; estimation that fails to converge or returns boundary estimates; and incorrect assumptions about the data structure or variable meaning.
  - https://russpoldrack.substack.com/p/defensive-coding
  - https://russpoldrack.substack.com/p/property-based-testing
  - https://russpoldrack.substack.com/p/the-goals-of-a-scientific-software

- **[GE-5] DAG-based execution with graceful failure and caching.** A DAG workflow engine is used to run independent paths in parallel, continue executing nodes not depending on a failed node, and cache/checkpoint intermediates; domain-specific engines are preferred when the community uses one, otherwise a well-maintained general-purpose engine. Targets are defined backward from final outputs.
  - https://russpoldrack.substack.com/p/using-a-workflow-engine
  - https://russpoldrack.substack.com/p/workflow-management-using-snakemake

- **[GE-6] Routine commands captured (e.g. Makefile) for simple workflows.** Regularly-run commands are captured as targets (e.g. a `Makefile` with file-based targets, explicit dependencies, `.PHONY` for non-file targets, timestamp-based incremental rebuilds); make is recognized as sufficient only for simple workflows, with a fuller engine used for complex ones.
  - https://russpoldrack.substack.com/p/running-a-simple-workflow-using-gnu

- **[GE-7] Coding agents sandboxed.** Coding agents are run inside a container without internet access before any permissive flags are granted.
  - https://russpoldrack.substack.com/p/using-containers-for-reproducible

- **[GE-8] Working software is the measure of progress.** Development uses short, Agile-style planning-and-development cycles (working software as the primary progress measure) rather than a waterfall that fixes all requirements before any code is written.
  - https://russpoldrack.substack.com/p/principles-of-software-engineering

- **[GE-9] Features justified by user stories.** Each feature is motivated by a concrete user story (user / functionality / problem solved); if no such story can be articulated, the feature is probably not needed (a YAGNI check, see GE-1).
  - https://russpoldrack.substack.com/p/principles-of-software-engineering

- **[GE-10] Dependencies treated as technical debt.** Every adopted third-party dependency is treated as an explicit assumption of risk and a form of technical debt; managing that risk (scrutiny scaled to expected reuse, a plan for abandonment — see RF-9) is a core part of building good software.
  - https://russpoldrack.substack.com/p/managing-technical-debt

- **[GE-11] No gold plating / over-engineering.** Extra polish and speculative engineering beyond what solves the problem are avoided, since the added work rarely pays off in the longer term (the rationale behind GE-1/YAGNI).
  - https://russpoldrack.substack.com/p/principles-of-software-engineering

- **[GE-12] Clean code lowers onboarding cost.** Code is kept clean and readable specifically so new developers can join the project without prohibitive startup costs — reducing bus-factor risk.
  - https://russpoldrack.substack.com/p/principles-of-software-engineering
