# LLM-assisted Code Generation and Reuse: An Exploratory Study on Contextual Information

Replication package for the paper *"LLM-assisted Code Generation and Reuse: An Exploratory Study on Contextual Information"* by Iris Reinhartz-Berger, Nurit Gal-Oz, Marina Litvak, and Aviram Morad, published at **VARIABILITY 2026**.

The study investigates how different **types of contextual information** (structural, behavioral, functional) affect the effectiveness of **LLM-assisted code generation and reuse**, when the produced code must be integrated into an existing Java system rather than written as a standalone artifact. It is instantiated on the [apo-games](https://doi.org/10.1145/3233027.3236403) product-line benchmark (Krüger et al., SPLC 2018).

---

## 1. Study at a glance

| Dimension | Levels |
|---|---|
| **Tasks** (3) | Achievements (ApoIcarus → ApoMario), Options (ApoSimple → ApoBot), Highscore (ApoIcarus → ApoMario) |
| **Strategies** (2) | Generation (implement the feature from scratch), Reuse (adapt the source game's feature implementation) |
| **Contexts** (8) | None, S, F, B, S+F, S+B, F+B, S+F+B |
| **Repetitions** | 5 runs per condition |
| **Total** | 3 × 2 × 8 × 5 = **240 single-shot runs** |
| **Model** | Gemini 3.1 Flash Lite (temperature 0.7) |
| **Dependent variables** | Syntactic validity (project compiles) and semantic correctness (percentages of automated tests passed, conditional on compilation) |
| **Tests** | Unit tests (`Test`) and integration tests (`InvokedTest`: use of real game objects and values; `AutonomousTest`: activation through the live game loop) |
 
Context types:

- **S — Structural**: class hierarchy, parent, fields, constants, assets, method signatures.
- **B — Behavioral**: per-method call graphs, logic hints, numeric literals, execution flow.
- **F — Functional**: inferred role tags, method capabilities, documented intent.

---

## 2. Repository structure

```
.
├── Pipeline/                       # experiment code and inputs
│   ├── Context_gen.py              # static-analysis context extractor (S/F/B JSONs + feature slicing)
│   ├── run.py                      # main driver: prompt → Gemini → integrate → compile → JUnit
│   ├── autonomous_runner.py        # supplementary grading: feature integrated into the live game loop
│   ├── invoked_runner.py           # supplementary grading: feature integrated into (invoked from) real game objects
│   ├── project_config.json         # model, #runs, paths to games/contexts/libs
│   ├── task_config.json            # per-task target game, package, test class
│   ├── Features.csv                # the 3 feature specifications (descriptions, test skeletons)
│   └── Prompts.csv                 # the 48 assembled prompts (one per condition) + attachment refs
├── Contexts/                       # extracted typed contexts for the two target games
│   ├── ApoBot_{Structural,Functional,Behavioral}.json
│   └── ApoMario_{Structural,Functional,Behavioral}.json
├── Tests/                          # evaluation suites
│   ├── ApoMarioAchievements{Test, InvokedTest, AutonomousTest}.java
│   ├── ApoMarioHighscore{Test, InvokedTest, AutonomousTest}.java
│   ├── ApoBotOptions{Test, AutonomousTest}.java
│   └── IntegrationDriver.java		# integration test driver
└── Results/                        # outputs of the reported experiment
    ├── raw_responses/p{ID}_r{RUN}.txt   # verbatim LLM responses (240 files)
    ├── experiment_results.json     # 240 runs: prompts, tokens, compilation, tests, error categories
    ├── autonomous_results.json     # supplementary wiring evaluation
    └── invoked_results.json        # supplementary coupling evaluation
```

### Not included

The apo-games sources themselves (`ApoBot`, `ApoMario`, `ApoIcarus`, `ApoSimple`) are **not** shipped here — obtain them from the apo-games benchmark and place them under a project base directory (see below). 

---

## 3. Prerequisites

- **Python** 3.14.2 
- **JDK** 
- A **Gemini API key**.
- Internet access on the first run: `run.py` downloads `junit-4.13.2.jar` and `hamcrest-core-1.3.jar` from Maven Central into the configured `lib_dir` if they are not already there.

```bash
pip install google-genai
```

## 4. Setup

1. Lay out a project base directory that contains the game sources, the libraries, and this package's inputs:

```
$APOGAMES_PROJECT_BASE/
├── ApoBot/  ApoMario/  ApoIcarus/  ApoSimple/    # game sources (not included)
├── lib/                                          # JUnit + Hamcrest jars (auto-downloaded on first run)
├── Features.csv, Prompts.csv                     # from Pipeline/
├── contexts/                                     # from Contexts/  (name must match project_config.json)
└── Results/                                      # output dir (raw_responses/ is created inside)
```

Paths are resolved from `Pipeline/project_config.json` relative to `APOGAMES_PROJECT_BASE`. Note that `context_jsons_dir` is declared there as `contexts` (lowercase) — on case-sensitive file systems, either rename the directory or edit the config.

2. Export the environment variables and point `run.py` at the two config files (the `PROJECT_CONFIG_FILE` and `TASK_CONFIG_FILE` constants at the top of the script are intentionally left blank):

```bash
export GEMINI_API_KEY="..."
export APOGAMES_PROJECT_BASE="/path/to/project_base"
```

```python
PROJECT_CONFIG_FILE = "/path/to/Pipeline/project_config.json"
TASK_CONFIG_FILE    = "/path/to/Pipeline/task_config.json"
```

No manual test setup is needed: the unit-test suite of each task is stored in the `Unit tests skeleton` column of `Features.csv`, and `run.py` materializes it inside the temporary project as `<test_class>.java` (`task_config.json`: `ApoBotOptionsTest`, `ApoMarioHighscoreTest`, `ApoMarioAchievementsTest`), fixing its package and imports on the fly. The same suites are also kept as readable standalone files in `Tests/`.

## 5. Running

### 5.1 Regenerating the typed contexts (optional — the JSONs are provided)

```bash
# full context + the Structural / Functional / Behavioral views
python Pipeline/Context_gen.py generate ApoMario /path/to/ApoMario.zip Contexts/

# merge selected subtypes into a single context file
python Pipeline/Context_gen.py combine ApoMario Contexts/ApoMario_Context.json --subtypes S_hierarchy F_roles --out Contexts/

# narrow a context to a set of classes and their dependencies
python Pipeline/Context_gen.py slice Contexts/ApoMario_Context.json Highscore --out Contexts/slice.json
```

`generate` parses every `.java` file, propagates inherited fields, and writes `<Game>_{Context,Structural,Functional,Behavioral}.json`. `slice` narrows a context to the classes relevant to a feature (used to build the reuse attachments), and `combine` merges selected subtypes into one file.

### 5.2 Main experiment

```bash
python Pipeline/run.py
```

For each of the 48 prompts × 5 runs, the script: assembles the prompt text with its context JSONs and Java attachments (Gemini Files API), calls the model, extracts the ```java fenced files from the response, sanitizes them (package fixing, import auto-fix/injection, reserved-keyword and brace checks), copies the target game into a temp workspace, integrates the generated files, compiles with `javac`, runs the task's JUnit suite, and appends one record to `Results/experiment_results.json`.

The run is **resumable**: completed `(prompt_id, run)` pairs found in `experiment_results.json` are skipped, so the script can be interrupted and restarted. Rate limiting (HTTP 429) is retried with exponential backoff, and `delay_between_calls` (7 s) throttles requests.

No manual post-processing, correction, or iterative prompting is performed — this is a deliberately single-shot setting.

### 5.3 Supplementary integration grading

In addition to the unit tests, the repository stores integration-oriented evaluations separately: InvokedTest checks whether the feature uses real game objects and values, while AutonomousTest checks whether it is activated through the live game loop. Both scripts re-grade only the runs that compiled and require their path constants (`BASE`, `RESULTS_DIR`, `TESTS_DIR`, `GEN`, `LIB`, …) to be filled in at the top of the file:

```python
# e.g. autonomous_runner.py
BASE        = "/path/to/project_base"   # holds ApoBot/, ApoMario/, ...
RESULTS_DIR = "/path/to/Results"        # experiment_results.json + raw_responses/
TESTS_DIR   = "/path/to/Tests"          # *AutonomousTest.java, IntegrationDriver.java
GEN         = "/path/to/Pipeline/run.py"
LIB         = "/path/to/lib"
```

```bash
python Pipeline/autonomous_runner.py   # *AutonomousTest: feature reacts to the live game loop (via IntegrationDriver)
                                       # → Results/autonomous_results.json
python Pipeline/invoked_runner.py      # *InvokedTest: feature invoked with the real game's objects/values
                                       # → Results/invoked_results.json (ApoMario Highscore/Achievements only)
```

Both print a pass-rate summary broken down by task × context type.

## 6. Data formats

### `Pipeline/Prompts.csv`

One row per condition; the row index is the `prompt_id` used throughout the results (`0–47`). Columns: `Task, Method, Source, Target, Prompt, Structural, Functional, Behavioral, Reuse Files, Source Code`. The three context columns hold the *game name* whose context JSON is attached (empty = that context type is not supplied), which is how the eight context configurations are encoded. `Reuse Files` and `Source Code` list `Game.Class` references that are uploaded as attachments.

Prompt-ID layout (each block of 8 walks the contexts None, S, F, B, S+B, F+B, S+F, S+F+B):

| IDs | Task | Strategy |
|---|---|---|
| 0–7 | Highscore | Reuse |
| 8–15 | Highscore | Generation |
| 16–23 | Achievements | Reuse |
| 24–31 | Achievements | Generation |
| 32–39 | Options | Reuse |
| 40–47 | Options | Generation |

### `Results/experiment_results.json`

A list of 240 records, one per run:

| Field | Meaning |
|---|---|
| `prompt_id`, `run` | condition identifier and repetition (1–5); the pair keys `raw_responses/p{prompt_id}_r{run}.txt` |
| `task`, `method`, `source_game`, `target_game` | condition metadata |
| `context_label`, `context_types` | e.g. `"S+F"`, `["S","F"]` |
| `prompt_length`, `prompt_tokens`, `output_tokens`, `thinking_tokens`, `response_time_sec`, `finish_reason`, `response_truncated` | delivery metrics |
| `generated_files` | class files extracted from the response |
| `compilation_success` | **syntactic validity** |
| `compile_error_type`, `primary_error`, `error_categories`, `total_errors`, `compilation_errors` | categorized `javac` diagnostics (e.g. missing symbols, type mismatches, unresolved references) |
| `tests_run`, `tests_passed`, `tests_failed`, `test_results` | **semantic correctness**, per-test PASS/FAIL |

### Where each output comes from

| File | Produced by | Contents |
|---|---|---|
| `Results/experiment_results.json` | `run.py` | Per (prompt, run): compilation and test outcome, error categories, timing, tokens |
| `Results/raw_responses/p{ID}_r{RUN}.txt` | `run.py` | Verbatim Gemini response |
| `Results/autonomous_results.json` | `autonomous_runner.py` | Integration outcome against the autonomous suite (activation through the live game loop; compiled runs only) |
| `Results/invoked_results.json` | `invoked_runner.py` | Integration outcome against the invoked suite (use of real game objects and values; compiled runs only) |

## 7. Reproducibility notes

- LLM responses are non-deterministic; exact numbers will not reproduce run-for-run, and the model version may drift. `raw_responses/` therefore contains the verbatim outputs behind the reported results.
- Contexts were extracted automatically with regex-based static analysis, which may introduce noise (a threat to validity discussed in the paper).

## 8. Citation

```bibtex
@inproceedings{ReinhartzBerger2026LLMContext,
  author    = {Reinhartz-Berger, Iris and Gal-Oz, Nurit and Litvak, Marina and Morad, Aviram},
  title     = {{LLM}-assisted Code Generation and Reuse: An Exploratory Study on Contextual Information},
  booktitle = {VARIABILITY 2026},
  year      = {2026}
}
```

The apo-games benchmark should be cited as: J. Krüger, W. Fenske, T. Thüm, D. Aporius, G. Saake, T. Leich. *Apo-games: A Case Study for Reverse Engineering Variability from Cloned Java Variants*. SPLC 2018, 251–256.
