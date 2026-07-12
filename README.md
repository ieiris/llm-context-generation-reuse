# Research Files — LLM Code-Generation Pipeline

This repo runs an experiment that asks Gemini to generate Java code for features of
small game projects (ApoBot, ApoMario, ApoIcarus, ApoSimple), then automatically
compiles the generated code against the real game source and runs JUnit tests
against it. Results (compilation status, test pass/fail, error categories, token
usage, etc.) are recorded to JSON for analysis.

## Layout

```
Pipeline/
  run.py               Main experiment driver (prompts Gemini, compiles, tests)
  Context_gen.py        Generates Structural/Functional/Behavioral JSON "context" files from a game's source zip
  autonomous_runner.py  Re-grades already-generated code against a stricter, hidden "autonomous" test suite
  invoked_runner.py     Re-grades already-generated code against an "invoked" test suite (ApoMario only)
  project_config.json   Paths, game project locations, Gemini model/params
  task_config.json      Per-task target game/package/test-class settings
  Features.csv          One row per feature/task (description, effort, unit test skeleton, ...)
  Prompts.csv           One row per prompt variant (task, method, context types, files to attach, prompt text)
Contexts/                Pre-generated *_Structural.json / *_Functional.json / *_Behavioral.json context files
Results/                 Output: experiment_results.json, raw_responses/, xlsx report, autonomous/invoked results
Tests/                   JUnit test sources (regular, Autonomous, Invoked variants) + IntegrationDriver.java
```

The actual game projects (`ApoBot`, `ApoMario`, `ApoIcarus`, `ApoSimple`) are **not**
part of this repo — they live in an external directory pointed to by
`APOGAMES_PROJECT_BASE` (see below).

## Prerequisites

- Python 3.10+
- `google-genai` Python package: `pip install google-genai`
- A JDK on `PATH` (`javac`/`java`) — used to compile and run generated code
- A Gemini API key
- The game projects (ApoBot/ApoMario/ApoIcarus/ApoSimple source trees) available on disk

`run.py` auto-downloads `junit-4.13.2.jar` and `hamcrest-core-1.3.jar` into the
configured `lib_dir` on first run if they aren't already there (requires internet
access).

## Configuration

### Environment variables

```
export GEMINI_API_KEY="your-key-here"
export APOGAMES_PROJECT_BASE="/path/to/folder/containing/ApoBot/ApoMario/ApoIcarus/ApoSimple"
```

`run.py` reads `PROJECT_BASE` from `APOGAMES_PROJECT_BASE`, then joins it with the
relative paths configured in `Pipeline/project_config.json` (`game_projects`,
`features_csv`, `prompts_csv`, `context_jsons_dir`, `output_dir`, `lib_dir`).

### `Pipeline/project_config.json`

Controls where inputs live, which game projects are available, and Gemini call
parameters (`num_runs`, `delay_between_calls`, `gemini_model`, `temperature`,
`max_output_tokens`). Adjust `game_projects` to match the folder names under
`APOGAMES_PROJECT_BASE`, and `context_jsons_dir`/`output_dir`/`lib_dir` if you want
different locations than the defaults (`contexts`, `Results`, `lib` — note the repo's
context folder is actually named `Contexts`, so update this value or rename the
folder to match on case-sensitive filesystems).

### `Pipeline/task_config.json`

One entry per task (e.g. `Options`, `Highscore`, `Achievements`) describing which
game the generated code targets, the package/directory it should land in, the name
of the JUnit test class to compile against, and any import patterns that should be
stripped from copied source before compiling.

### `Pipeline/Features.csv` / `Pipeline/Prompts.csv`

- **Features.csv** — one row per feature/task: description, detailed description,
  high-level test cases, and a JUnit "unit tests skeleton" (`unit_tests`) that gets
  compiled against the generated code.
- **Prompts.csv** — one row per prompt variant: `Task`, `Method`, `Source`/`Target`
  game, the `Prompt` text itself, which context types to attach (`Structural`,
  `Functional`, `Behavioral` columns — any non-empty value names the source game
  whose context JSON to attach), and `Reuse Files`/`Source Code` (semicolon- or
  newline-separated `Game.ClassName` refs) of existing `.java` files to attach as-is.

## Running the main experiment

```bash
cd Pipeline
python run.py
```

This will, in order:
1. Validate the API key, `javac`, config files, game project paths, and CSVs.
2. Download JUnit/Hamcrest jars if missing.
3. Load `Features.csv` and `Prompts.csv`, pre-upload every referenced context JSON
   and source `.java` file to the Gemini Files API.
4. For each prompt × `num_runs`, send the prompt (+ attachments) to Gemini, extract
   any ` ```java filename=X.java ` code blocks from the response, copy the target
   game project to a temp dir, drop the generated file(s) in, auto-fix/inject
   imports, compile with `javac`, compile the task's JUnit test class against it,
   and run the tests with `JUnitCore`.
5. Append one JSON entry per (prompt, run) to `Results/experiment_results.json`
   after every call, and save the raw model response to
   `Results/raw_responses/p<id>_r<run>.txt`.

The run is resumable: it skips any `(prompt_id, run)` pair already present in
`experiment_results.json`, so re-running `run.py` continues where it left off.

Each result entry records: compilation success/errors (with an auto-classified
`primary_error` category), per-test pass/fail with failure messages, response
timing/length, token usage, and whether the response was truncated.

## Generating/updating context files

`Context_gen.py` parses a game's `.java` sources (from a zip) with regexes to build
per-class metadata (fields, methods, signatures, call graphs, javadocs, roles),
then splits it into `Structural` / `Functional` / `Behavioral` JSON views used as
prompt context. Run it directly:

```bash
# Full context + all Structural/Functional/Behavioral subtype files
python Pipeline/Context_gen.py generate ApoMario /path/to/ApoMario.zip Contexts/

# Combine specific subtypes (e.g. S_hierarchy + F_roles) into one file
python Pipeline/Context_gen.py combine ApoMario Contexts/ApoMario_Context.json --subtypes S_hierarchy F_roles --out Contexts/

# Slice the context down to a set of classes (+ their dependencies)
python Pipeline/Context_gen.py slice Contexts/ApoMario_Context.json HighscorePanel --out Contexts/slice.json
```

The resulting `<Game>_Structural.json` / `<Game>_Functional.json` /
`<Game>_Behavioral.json` files are what `Prompts.csv`'s Structural/Functional/
Behavioral columns reference (matched by game name).

## Grading generated code further (optional, after `run.py`)

`autonomous_runner.py` and `invoked_runner.py` re-run already-generated,
already-compiled code from `Results/experiment_results.json` against a second,
stricter set of hidden tests (the `*AutonomousTest.java` / `*InvokedTest.java`
files in `Tests/`). Both scripts have their path variables hardcoded as empty
strings at the top of the file (`BASE`, `RESULTS_DIR`, `TESTS_DIR`/`INVOKED_DIR`,
`GEN`, `LIB`, etc.) — fill these in before running, e.g.:

```python
# autonomous_runner.py
BASE        = "/path/to/game/projects/root"
RESULTS_DIR = "/path/to/Results"
TESTS_DIR   = "/path/to/Tests"
GEN         = "/path/to/Pipeline/run.py"
LIB         = "/path/to/Pipeline/lib"
```

Then run:

```bash
python Pipeline/autonomous_runner.py   # writes Results/autonomous_results.json
python Pipeline/invoked_runner.py      # writes Results/invoked_results.json (ApoMario Highscore/Achievements only)
```

Both only process entries whose `compilation_success` was already `true` in
`experiment_results.json`, and print a pass-rate summary broken down by task ×
context type (and, for `invoked_runner.py`, by individual test).

## Output files

| File | Produced by | Contents |
|---|---|---|
| `Results/experiment_results.json` | `run.py` | Per (prompt, run): compile/test outcome, error categories, timing, tokens |
| `Results/raw_responses/p<id>_r<run>.txt` | `run.py` | Full raw Gemini response text |
| `Results/autonomous_results.json` | `autonomous_runner.py` | Pass/fail against hidden autonomous tests |
| `Results/invoked_results.json` | `invoked_runner.py` | Pass/fail against invoked tests |
| `Results/experiment_results_report.xlsx` | (manual/external analysis) | Spreadsheet summary of results |
