import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request

API_KEY = os.environ.get("GEMINI_API_KEY")
PROJECT_BASE = os.environ.get("APOGAMES_PROJECT_BASE")
PROJECT_CONFIG_FILE = ""
TASK_CONFIG_FILE    = ""

features:              dict = {}
gemini_file_cache = {}
prompts:               list = []
context_cache:         dict = {}
import_index_per_game: dict = {}
EXTRA_CLASSPATH:       str  = ""   # optional dependency classpath for real build systems (default: none)


def _resolve_extra_classpath(pc) -> str:
    sep = ";" if os.name == "nt" else ":"
    parts = []
    raw = pc.get("extra_classpath", "")
    if isinstance(raw, list):
        joined = sep.join(x for x in raw if x)
        if joined:
            parts.append(joined)
    elif raw:
        parts.append(raw)                     
    cpf = pc.get("classpath_file", "")
    if cpf:
        path = cpf if os.path.isabs(cpf) else os.path.join(PROJECT_BASE, cpf)
        if os.path.exists(path):
            with open(path) as f:
                parts.append(f.read().strip())
        else:
            print(f"classpath_file not found: {path}")
    return sep.join(p for p in parts if p)


def setup():
    global FEATURES_CSV, PROMPTS_CSV, CONTEXT_JSONS_DIR, OUTPUT_DIR
    global LIB_DIR, JUNIT_JAR, HAMCREST_JAR, GAME_PROJECTS
    global NUM_RUNS, DELAY_BETWEEN_CALLS, GEMINI_MODEL, TEMPERATURE, MAX_OUTPUT_TOKENS
    global TASK_CONFIG, EXTRA_CLASSPATH

    print("=" * 60)

    if not API_KEY:
        print("No API key found")
        sys.exit(1)
    print("API key configured")

    try:
        result = subprocess.run(["javac", "-version"], capture_output=True, text=True)
        print(f"{result.stderr.strip() or result.stdout.strip()}")
    except FileNotFoundError:
        print("java not found")
        sys.exit(1)

    # Load project config
    if not os.path.exists(PROJECT_CONFIG_FILE):
        print(f"project_config.json not found at {PROJECT_CONFIG_FILE}")
        sys.exit(1)
    with open(PROJECT_CONFIG_FILE, "r") as f:
        pc = json.load(f)

    def p(key):
        return os.path.join(PROJECT_BASE, pc[key]) if not os.path.isabs(pc[key]) else pc[key]

    FEATURES_CSV      = p("features_csv")
    PROMPTS_CSV       = p("prompts_csv")
    CONTEXT_JSONS_DIR = p("context_jsons_dir")
    OUTPUT_DIR        = p("output_dir")
    LIB_DIR           = p("lib_dir")
    JUNIT_JAR         = os.path.join(LIB_DIR, "junit-4.13.2.jar")
    HAMCREST_JAR      = os.path.join(LIB_DIR, "hamcrest-core-1.3.jar")
    GAME_PROJECTS     = {
        name: os.path.join(PROJECT_BASE, rel_path)
        for name, rel_path in pc["game_projects"].items()
    }
    NUM_RUNS             = pc.get("num_runs")
    DELAY_BETWEEN_CALLS  = pc.get("delay_between_calls")
    GEMINI_MODEL         = pc.get("gemini_model")
    TEMPERATURE          = pc.get("temperature")
    MAX_OUTPUT_TOKENS    = pc.get("max_output_tokens")
    EXTRA_CLASSPATH      = _resolve_extra_classpath(pc)
    if EXTRA_CLASSPATH:
        print(f"extra classpath: {EXTRA_CLASSPATH.count(os.pathsep) + 1} entries")
    print(f"project_config.json loaded")

    # Load task config
    if not os.path.exists(TASK_CONFIG_FILE):
        print(f"task_config.json not found at {TASK_CONFIG_FILE}")
        sys.exit(1)
    with open(TASK_CONFIG_FILE, "r") as f:
        TASK_CONFIG = json.load(f)
    print(f"task_config.json: {len(TASK_CONFIG)} tasks ({', '.join(TASK_CONFIG)})")

    # Check game projects
    for name, path in GAME_PROJECTS.items():
        if os.path.exists(path):
            java_count = sum(1 for r, _, fs in os.walk(path) for f in fs if f.endswith(".java"))
            print(f"{name}: {java_count} .java files")
        else:
            print(f"{name}: NOT FOUND at {path}")

    # Check CSVs
    for f in [FEATURES_CSV, PROMPTS_CSV]:
        exists = os.path.exists(f)
        print(f"{'✅' if exists else '❌'} {os.path.basename(f)}")
        if not exists:
            sys.exit(1)

    # Check context dir
    if os.path.exists(CONTEXT_JSONS_DIR):
        json_count = len([f for f in os.listdir(CONTEXT_JSONS_DIR) if f.endswith(".json")])
        print(f"Contexts dir: {json_count} JSON files")
    else:
        print(f"Contexts dir not found: {CONTEXT_JSONS_DIR}")

    os.makedirs(LIB_DIR, exist_ok=True)
    if not os.path.exists(JUNIT_JAR):
        urllib.request.urlretrieve(
            "https://repo1.maven.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar",
            JUNIT_JAR,
        )
    if not os.path.exists(HAMCREST_JAR):
        urllib.request.urlretrieve(
            "https://repo1.maven.org/maven2/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar",
            HAMCREST_JAR,
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "raw_responses"), exist_ok=True)

def _split_refs(refs: str) -> list[str]:
    """Split a 'Game.Class; Game.Class' CSV cell into individual refs."""
    return [r.strip() for r in re.split(r"[;\n]+", refs or "") if r.strip() and "." in r.strip()]


def upload_to_gemini(client, filepath: str):
    if not client or not filepath or not os.path.exists(filepath):
        return None
    if filepath in gemini_file_cache:
        return gemini_file_cache[filepath]
    gemini_file = client.files.upload(
        file=filepath,
        config={"mime_type": "text/plain", "display_name": os.path.basename(filepath)},
    )
    for _ in range(30):
        if "PROCESSING" in str(getattr(gemini_file, "state", "")):
            time.sleep(1)
            gemini_file = client.files.get(name=gemini_file.name)
        else:
            break
    gemini_file_cache[filepath] = gemini_file
    return gemini_file


def _build_context_type_map(fieldnames: list[str]) -> dict:
    fixed = {"Task", "Method", "Source", "Target", "Prompt", "Source Code", "Reuse Files", "Reference Files"}
    mapping = {}
    for col in fieldnames:
        if col not in fixed:
            abbrev = col[0].upper()
            mapping[abbrev] = col
    return mapping  


def load_context(game_name: str, ctx_abbrev: str):
    key = f"{game_name}_{ctx_abbrev}"
    if key in context_cache:
        return context_cache[key]

    type_name = CONTEXT_TYPE_MAP.get(ctx_abbrev, ctx_abbrev)
    filepath = os.path.join(CONTEXT_JSONS_DIR, f"{game_name}_{type_name}.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            data = json.load(f)
        context_cache[key] = data
        return data
    else:
        print(f"Missing context: {filepath}")
        return None


def load_data(client=None):
    global features, prompts, CONTEXT_TYPE_MAP, gemini_file_cache

    features.clear()
    prompts.clear()
    context_cache.clear()

    with open(FEATURES_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            task = row["Task"].strip()
            if task:
                features[task] = {
                    "description":          row.get("Description", ""),
                    "detailed_description": row.get("Detailed Description", ""),
                    "test_cases_text":      row.get("High-Level Test Cases", ""),
                    "unit_tests":           row.get("Unit tests skeleton", ""),
                    "effort":               row.get("Effort Level", ""),
                    "reuse_priority":       row.get("Reuse/Generation Priority", ""),
                }
    print(f"Loaded {len(features)} features: {list(features.keys())}")

    with open(PROMPTS_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        CONTEXT_TYPE_MAP = _build_context_type_map(reader.fieldnames or [])
        print(f"Context types detected: {CONTEXT_TYPE_MAP}")

        for i, row in enumerate(reader):
            if not row.get("Task", "").strip() or not row.get("Prompt", "").strip():
                print(f"  Skipping CSV row {i}: empty Task/Prompt")
                continue
            ctx_types = []
            ctx_games = {}
            for abbrev, col_name in CONTEXT_TYPE_MAP.items():
                val = row.get(col_name, "").strip()
                if val:
                    ctx_types.append(abbrev)
                    ctx_games[abbrev] = val

            prompts.append({
                "id":               i,
                "task":             row["Task"].strip(),
                "method":           row["Method"].strip(),
                "source":           row.get("Source", "").strip(),
                "target":           row["Target"].strip(),
                "prompt_text":      row["Prompt"].strip(),
                "context_types":    ctx_types,
                "context_label":    "+".join(ctx_types) if ctx_types else "None",
                "context_games":    ctx_games,
                "reuse_code_refs":  row.get("Reuse Files", "").strip(),
                "source_code_refs": row.get("Source Code", "").strip(),
            })

    needed_contexts = set()
    needed_sources = set()
    for p in prompts:
        for abbrev, game in p["context_games"].items():
            needed_contexts.add((game, abbrev))
        for ref in _split_refs(p["reuse_code_refs"]) + _split_refs(p["source_code_refs"]):
            needed_sources.add(ref)

    print("Pre-uploading context and source files to Gemini Files API...")

    # 1. Upload JSON Contexts
    for game, abbrev in sorted(needed_contexts):
        data = load_context(game, abbrev)
        if data:
            type_name = CONTEXT_TYPE_MAP.get(abbrev, abbrev)
            filename = f"{game}_{type_name}.json"
            filepath = os.path.join(CONTEXT_JSONS_DIR, filename)
            if client and filepath not in gemini_file_cache:
                print(f"  Uploading context: {filename}")
                upload_to_gemini(client, filepath)

    # 2. Upload Reuse + Source Code Files
    for ref in sorted(needed_sources):
        parts = ref.split(".")
        game_name, class_name = parts[0], parts[-1]
        game_path = GAME_PROJECTS.get(game_name)
        if not game_path:
            print(f"  Unknown game project in ref: {ref}")
            continue
        filepath = find_java_file(game_path, class_name)
        if not filepath:
            print(f"  Not found: {class_name}.java in {game_name}")
            continue
        if client and filepath not in gemini_file_cache:
            print(f"  Uploading source: {class_name}.java")
            upload_to_gemini(client, filepath)


def find_java_file(game_project_path: str, class_name: str) -> str | None:
    target = f"{class_name}.java"
    for root, dirs, files in os.walk(game_project_path):
        for f in files:
            if f == target:
                return os.path.join(root, f)
    return None


def assemble_prompt_with_attachments(prompt_row) -> tuple[str, list]:
    attachments, seen = [], set()

    def attach(filepath):
        if filepath and filepath in gemini_file_cache and filepath not in seen:
            seen.add(filepath)
            attachments.append(gemini_file_cache[filepath])
        elif filepath and filepath not in gemini_file_cache:
            print(f"  Missing attachment (not uploaded): {os.path.basename(filepath)}")

    text_parts = [prompt_row["prompt_text"]]

    # Context JSON attachments
    for abbrev, game_name in prompt_row["context_games"].items():
        type_name = CONTEXT_TYPE_MAP.get(abbrev, abbrev)
        attach(os.path.join(CONTEXT_JSONS_DIR, f"{game_name}_{type_name}.json"))

    # Reuse-file and source-code attachments
    for ref in _split_refs(prompt_row["reuse_code_refs"]) + _split_refs(prompt_row["source_code_refs"]):
        game_name, class_name = ref.split(".")[0], ref.split(".")[-1]
        game_path = GAME_PROJECTS.get(game_name)
        if game_path:
            attach(find_java_file(game_path, class_name))

    # Trigger thinking
    text_parts.append("\n\n--- OUTPUT FORMAT ---")
    text_parts.append("First, think step-by-step through the class architecture, dependencies, ")
    text_parts.append("and potential logic edge cases. Write down your brief internal reasoning.")
    text_parts.append("Then, output the final Java source code. For each class, wrap it cleanly in this block:")
    text_parts.append("```java filename=ClassName.java")
    text_parts.append("// your code here")
    text_parts.append("```")

    return "\n".join(text_parts), attachments


def extract_java_files(response_text: str) -> dict:
    files = {}

    def normalize_filename(raw_name, code_block):
        if not raw_name:
            m = re.search(r"public\s+(?:abstract\s+)?class\s+(\w+)", code_block)
            return f"{m.group(1)}.java" if m else None
        if "/" in raw_name:
            raw_name = raw_name.rsplit("/", 1)[-1]
        parts = raw_name.rsplit(".java", 1)
        if parts[0].count(".") >= 1:
            return f"{parts[0].rsplit('.', 1)[-1]}.java"
        return raw_name

    pattern = r"```java(?:\s+filename=([^\s\n]+))?\s*\n(.*?)```"
    matches  = re.findall(pattern, response_text, re.DOTALL)

    if not matches:
        for block in re.findall(r"```java\s*\n(.*?)```", response_text, re.DOTALL):
            fname = normalize_filename(None, block)
            if fname:
                files[fname] = block.strip()
    else:
        for filename_hint, code_block in matches:
            code_block = code_block.strip()
            fname = normalize_filename(
                filename_hint.strip() if filename_hint else None, code_block
            )
            if fname:
                if fname in files and len(code_block) <= len(files[fname]):
                    continue
                files[fname] = code_block

    if not files:
        m = re.search(r"public\s+class\s+(\w+)", response_text)
        if m:
            clean = response_text.strip()
            if clean.startswith("```"):
                clean = re.sub(r"^```\w*\n", "", clean)
                clean = re.sub(r"```$", "", clean)
            files[f"{m.group(1)}.java"] = clean.strip()

    for fname in files:
        files[fname] = "\n".join(
            line for line in files[fname].splitlines()
            if line.strip() not in ("```", "```java")
        )

    return files

def build_import_index():
    global import_index_per_game
    import_index_per_game = {}
    for game_name, game_path in GAME_PROJECTS.items():
        if not os.path.exists(game_path):
            continue
        game_index = {}
        for root, dirs, files in os.walk(game_path):
            for f in files:
                if f.endswith(".java"):
                    class_name = f[:-5]
                    rel_path   = os.path.relpath(root, game_path)
                    package    = "" if rel_path == "." else rel_path.replace(os.sep, ".")
                    game_index[class_name] = f"{package}.{class_name}" if package else class_name
        import_index_per_game[game_name] = game_index


def autofix_imports(java_code: str, target_game: str) -> str:
    game_index = import_index_per_game.get(target_game, {})
    if not game_index:
        return java_code

    lines, fixes = [], 0
    for line in java_code.split("\n"):
        m = re.match(r"^(\s*import\s+)([\w.]+)\s*;", line)
        if m:
            full_import = m.group(2)
            class_name  = full_import.rsplit(".", 1)[-1]
            if class_name in game_index and game_index[class_name] != full_import:
                line  = f"{m.group(1)}{game_index[class_name]};"
                fixes += 1
        lines.append(line)
    return "\n".join(lines)


def inject_missing_imports(java_code: str, target_game: str) -> str:
    game_index = import_index_per_game.get(target_game, {})
    if not game_index:
        return java_code

    existing_imports = set(re.findall(r"import\s+([\w.]+);", java_code))
    existing_simple  = {imp.rsplit(".", 1)[-1] for imp in existing_imports}
    referenced       = set(re.findall(r"\b([A-Z]\w+)\b", java_code))

    new_imports = []
    for class_name in referenced:
        if class_name not in existing_simple and class_name in game_index:
            new_imports.append(f"import {game_index[class_name]};")

    if re.search(r"\b(ArrayList|List|HashMap|Map|HashSet|Set)\b", java_code):
        if "import java.util" not in java_code:
            new_imports.append("import java.util.*;")

    if re.search(r"\b(Color|Graphics|Graphics2D|Font|Image|BufferedImage|Dimension|Point|Rectangle)\b", java_code):
        if "import java.awt" not in java_code:
            new_imports.append("import java.awt.*;")

    if new_imports:
        lines = java_code.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("package "):
                insert_idx = i + 1
                break
        lines[insert_idx:insert_idx] = sorted(set(new_imports))
        return "\n".join(lines)

    return java_code


_JAVA_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "final", "finally", "float", "for", "goto", "if", "implements",
    "import", "instanceof", "int", "interface", "long", "native", "new",
    "package", "private", "protected", "public", "return", "short", "static",
    "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while",
}

def fix_reserved_keyword_methods(java_code: str) -> str:
    pattern = re.compile(
        r'(\b(?:public|protected|private|static|final|abstract)\s+(?:(?:static|final|abstract|synchronized)\s+)*)'
        r'(?:[\w<>\[\]]+\s+)'
        r'(\w+)'
        r'(\s*\()'
    )
    fixed_count = 0

    def replacer(m):
        nonlocal fixed_count
        name = m.group(2)
        if name in _JAVA_KEYWORDS:
            fixed_count += 1
            return m.group(1) + name + "Method" + m.group(3)
        return m.group(0)

    result = [pattern.sub(replacer, line) for line in java_code.split("\n")]
    return "\n".join(result)


def code_braces_balanced(java_code: str) -> bool:
    stripped = re.sub(r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'",
                      "", java_code, flags=re.S)
    return stripped.count("{") == stripped.count("}")


def fix_generated_package(java_code: str, target_package: str) -> str:
    code_no_pkg  = re.sub(r"^\s*package\s+[\w.]+\s*;", "", java_code, count=1).strip()
    if not target_package:
        return code_no_pkg
    return f"package {target_package};\n\n{code_no_pkg}"


def resolve_generated_placement(class_name: str, code: str, project_dir: str,
                                target_package: str, target_dir: str):
    m0 = re.search(r"^\s*package\s+([\w.]+)\s*;", code, re.M)
    if m0:
        declared_path = os.path.join(project_dir, *m0.group(1).split("."), f"{class_name}.java")
        if os.path.exists(declared_path):
            return declared_path, m0.group(1), True

    existing = find_java_file(project_dir, class_name)
    if existing:
        rel = os.path.relpath(os.path.dirname(existing), project_dir)
        pkg = "" if rel == "." else rel.replace(os.sep, ".")
        return existing, pkg, True

    m = re.search(r"^\s*package\s+([\w.]+)\s*;", code, re.M)
    declared = m.group(1) if m else None
    pkg = declared or target_package
    dest_dir = os.path.join(project_dir, *pkg.split(".")) if pkg else os.path.join(project_dir, target_dir)
    return os.path.join(dest_dir, f"{class_name}.java"), pkg, False


def convert_to_utf8(directory: str):
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".java"):
                filepath = os.path.join(root, f)
                try:
                    with open(filepath, "r", encoding="utf-8") as fh:
                        fh.read()
                except UnicodeDecodeError:
                    try:
                        with open(filepath, "r", encoding="iso-8859-1") as fh:
                            content = fh.read()
                        with open(filepath, "w", encoding="utf-8") as fh:
                            fh.write(content)
                    except Exception:
                        pass

def strip_broken_imports(directory: str, patterns: list[str]):
    for root, dirs, files in os.walk(directory):
        for f in files:
            if not f.endswith(".java"):
                continue
            filepath = os.path.join(root, f)
            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            cleaned = [
                line for line in lines
                if not any(pat in line for pat in patterns)
            ]
            if len(cleaned) != len(lines):
                with open(filepath, "w", encoding="utf-8") as fh:
                    fh.writelines(cleaned)


def _filter_compilation_output(stderr_text: str) -> str:
    lines, filtered, skipping = stderr_text.split("\n"), [], False
    for line in lines:
        if "warning:" in line or "warning]" in line:
            skipping = True
            continue
        if line.strip().startswith("Note:"):
            continue
        if skipping:
            if "error:" in line or (line.strip() and line[0] == "/" and ".java:" in line):
                skipping = False
                filtered.append(line)
            continue
        filtered.append(line)
    return "\n".join(filtered).strip()[:5000]


def classify_compilation_errors(stderr_text: str) -> dict:
    categories = {
        "wrong_import":    0,
        "missing_symbol":  0,
        "wrong_type":      0,
        "missing_method":  0,
        "missing_override":0,
        "access_error":    0,
        "syntax_error":    0,
        "duplicate":       0,
        "abstract_error":  0,
        "constructor_error":0,
        "encoding_error":  0,
        "other":           0,
    }
    for line in stderr_text.split("\n"):
        ll = line.lower()
        if "error:" not in ll:
            continue
        if "package" in ll and "does not exist" in ll:
            categories["wrong_import"] += 1
        elif "cannot find symbol" in ll:
            categories["missing_method" if "method" in ll else "missing_symbol"] += 1
        elif "incompatible types" in ll or "type mismatch" in ll:
            categories["wrong_type"] += 1
        elif "does not override" in ll or "is not abstract" in ll:
            categories["abstract_error" if "abstract" in ll else "missing_override"] += 1
        elif any(k in ll for k in ("private access", "not visible", "has protected access")):
            categories["access_error"] += 1
        elif "already defined" in ll or "duplicate class" in ll:
            categories["duplicate"] += 1
        elif "constructor" in ll and ("cannot be applied" in ll or "no suitable" in ll):
            categories["constructor_error"] += 1
        elif "unmappable character" in ll:
            categories["encoding_error"] += 1
        elif any(k in ll for k in ("';' expected", "illegal start", "reached end of file",
                                    "expected", "illegal character", "unclosed")):
            categories["syntax_error"] += 1
        else:
            categories["other"] += 1

    active  = {k: v for k, v in categories.items() if v > 0}
    primary = max(active, key=active.get) if active else "unknown"
    return {"error_categories": active, "primary_error": primary, "total_errors": sum(active.values())}


def integrate_compile_test(task: str, generated_files: dict, run_id: str = "") -> dict:
    config         = TASK_CONFIG[task]
    target_game    = config["target_game"]
    target_package = config["generated_package"]
    target_dir     = config["generated_dir"]
    test_class     = config["test_class"]
    sep            = ";" if os.name == "nt" else ":"

    result = {
        "compilation_success": False,
        "compilation_errors":  "",
        "tests_run":    0,
        "tests_passed": 0,
        "tests_failed": 0,
        "test_results": {},
        "test_output":  "",
    }

    work_dir = tempfile.mkdtemp(prefix=f"pipeline_{task}_{run_id}_")
    game_src = GAME_PROJECTS[target_game]
    original_index = import_index_per_game.get(target_game, {})

    try:
        project_dir = os.path.join(work_dir, "project")
        shutil.copytree(
            game_src, project_dir,
            ignore=shutil.ignore_patterns("*.class", ".git", ".idea", "*.iml", "Test.java"),
        )
        convert_to_utf8(project_dir)
        broken_patterns = TASK_CONFIG.get(task, {}).get("broken_import_patterns", [])
        if broken_patterns:
            strip_broken_imports(project_dir, broken_patterns)

        game_index = dict(original_index)
        import_index_per_game[target_game] = game_index
        placements = {}
        for filename, code in generated_files.items():
            cls = filename[:-5]
            dest_path, pkg, overwrote = resolve_generated_placement(
                cls, code, project_dir, target_package, target_dir
            )
            placements[filename] = (dest_path, pkg, overwrote)
            game_index[cls] = f"{pkg}.{cls}" if pkg else cls

        truncated_files = []
        written_files = {}
        for filename, code in generated_files.items():
            dest_path, pkg, overwrote = placements[filename]
            code = autofix_imports(code, target_game)
            code = inject_missing_imports(code, target_game)
            code = fix_reserved_keyword_methods(code)
            code = fix_generated_package(code, pkg)
            if broken_patterns:
                code = "\n".join(
                    line for line in code.split("\n")
                    if not any(pat in line for pat in broken_patterns)
                )
            if not code_braces_balanced(code):
                truncated_files.append(filename)
                continue
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "w") as f:
                f.write(code)
            written_files[filename] = code

        if truncated_files:
            result["truncated_files"] = truncated_files
        generated_files = written_files

        java_files = [
            os.path.join(root, fn)
            for root, dirs, files in os.walk(project_dir)
            for fn in files if fn.endswith(".java")
        ]

        classes_dir = os.path.join(work_dir, "classes")
        os.makedirs(classes_dir, exist_ok=True)
        classpath = sep.join(p for p in (JUNIT_JAR, HAMCREST_JAR, EXTRA_CLASSPATH) if p)

        compile_result = subprocess.run(
            ["javac", "-cp", classpath, "-d", classes_dir,
             "-encoding", "UTF-8", "-nowarn"]
            + java_files,
            capture_output=True, text=True, timeout=120,
        )

        if compile_result.returncode != 0:
            filtered = _filter_compilation_output(compile_result.stderr)
            result["compilation_errors"] = filtered
            analysis = classify_compilation_errors(compile_result.stderr)
            result.update(analysis)
            result["compile_error_type"] = analysis.get("primary_error", "unknown")
            first_error = ""
            for line in filtered.split("\n"):
                if "error:" in line:
                    first_error = line.strip()[:300]
                    break
            result["compile_error_message"] = first_error
            return result

        result["compilation_success"] = True
        result["compile_error_type"]    = ""
        result["compile_error_message"] = ""

        test_code = features[task]["unit_tests"]
        test_code = re.sub(r"(?m)^\s*package\s+[\w.]+\s*;\s*", "", test_code, count=1)
        test_code = autofix_imports(test_code, target_game)
        test_code = "\n".join(
            line for line in test_code.splitlines()
            if "import test." not in line
        )

        missing_junit = [imp for imp in (
            "import org.junit.Test;",
            "import org.junit.Before;",
            "import static org.junit.Assert.*;",
        ) if imp not in test_code]
        if missing_junit:
            test_code = "\n".join(missing_junit) + "\n" + test_code

        test_code = inject_missing_imports(test_code, target_game)

        test_code = f"package {target_package};\n\n{test_code}"
        test_dir = os.path.join(project_dir, target_dir)
        os.makedirs(test_dir, exist_ok=True)
        test_filepath = os.path.join(test_dir, f"{test_class}.java")
        with open(test_filepath, "w") as f:
            f.write(test_code)

        compile_test_result = subprocess.run(
            ["javac", "-cp", f"{classes_dir}{sep}{classpath}", "-d", classes_dir,
             "-sourcepath", project_dir, "-encoding", "UTF-8", "-nowarn", test_filepath],
            capture_output=True, text=True, timeout=120,
        )
        if compile_test_result.returncode != 0:
            filtered_test = _filter_compilation_output(compile_test_result.stderr)
            result["test_compilation_errors"] = filtered_test
            print(f"Test compilation failed (game compiled)")
            for line in filtered_test.split("\n")[:3]:
                print(f"    | {line}")
            return result

        full_test_class = f"{target_package}.{test_class}"
        run_cp = f"{classes_dir}{sep}{classpath}"
        test_command = config.get("test_command", "")
        if test_command:
            import shlex
            cmd = shlex.split(test_command.format(
                cp=run_cp, classes=classes_dir, test_class=full_test_class, sep=sep))
        else:
            cmd = ["java", "-cp", run_cp, "org.junit.runner.JUnitCore", full_test_class]
        test_proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = test_proc.stdout + test_proc.stderr
        result["test_output"] = output

        run_m  = re.search(r"Tests run:\s*(\d+)", output)
        fail_m = re.search(r"Failures:\s*(\d+)", output)
        err_m  = re.search(r"Errors:\s*(\d+)", output)
        ok_m   = re.search(r"OK\s*\((\d+)\s+test", output)

        if run_m:                                 
            result["tests_run"]    = int(run_m.group(1))
            result["tests_failed"] = int(fail_m.group(1)) if fail_m else 0
            if err_m:
                result["tests_failed"] += int(err_m.group(1))
        elif ok_m:                                
            result["tests_run"]    = int(ok_m.group(1))
            result["tests_failed"] = 0
        else:                                     
            ok5 = re.search(r"(\d+)\s+tests successful", output)
            f5  = re.search(r"(\d+)\s+tests failed", output)
            if ok5:
                passed = int(ok5.group(1)); failed = int(f5.group(1)) if f5 else 0
                result["tests_run"]    = passed + failed
                result["tests_failed"] = failed

        result["tests_passed"] = result["tests_run"] - result["tests_failed"]
        test_failure_messages: dict[str, str] = {}
        current_test = None
        for line in output.split("\n"):
            m = re.match(r"\d+\)\s+(\w+)\(", line)
            if m:
                current_test = m.group(1)
                result["test_results"][current_test] = "FAIL"
                test_failure_messages[current_test] = ""
                continue
            if current_test and test_failure_messages.get(current_test) == "":
                stripped = line.strip()
                if stripped and not stripped.startswith("at "):
                    test_failure_messages[current_test] = stripped[:300]
        result["test_failure_messages"] = test_failure_messages

       
        for method in re.findall(r"@Test\s+public\s+void\s+(\w+)", features[task]["unit_tests"]):
            if method not in result["test_results"]:
                result["test_results"][method] = "PASS"
            elif result["test_results"][method] == "FAIL":
                msg = test_failure_messages.get(method, "")
                result["test_results"][method] = f"FAIL: {msg}" if msg else "FAIL"

    except subprocess.TimeoutExpired:
        result["compilation_errors"] = "TIMEOUT"
    except Exception as e:
        result["compilation_errors"] = f"Pipeline error: {str(e)}"
    finally:
        import_index_per_game[target_game] = original_index   
        shutil.rmtree(work_dir, ignore_errors=True)

    return result


def run_experiment():
    from google import genai

    client = genai.Client(api_key=API_KEY)

    try:
        test_resp = client.models.generate_content(
            model=GEMINI_MODEL, contents="Say 'connected' and nothing else."
        )
        print(f"Gemini API connected")
    except Exception as e:
        print(f"Gemini API failed: {e}")
        sys.exit(1)

    load_data(client=client)
    build_import_index()

    results_file  = os.path.join(OUTPUT_DIR, "experiment_results.json")
    all_results   = []
    if os.path.exists(results_file):
        with open(results_file, "r") as f:
            all_results = json.load(f)
    completed_keys = {(r["prompt_id"], r["run"]) for r in all_results}

    total_calls = len(prompts) * NUM_RUNS
    print(f"\nTotal: {len(prompts)} prompts × {NUM_RUNS} runs = {total_calls} calls")
    print("=" * 60)

    for run in range(1, NUM_RUNS + 1):
        for prompt_row in prompts:
            pid = prompt_row["id"]
            if (pid, run) in completed_keys:
                continue

            label = (f"[Run {run}/{NUM_RUNS}] Prompt {pid}: "
                     f"{prompt_row['task']}/{prompt_row['method']}/{prompt_row['context_label']}")
            print(f"\n{'=' * 60}\n{label}")

            entry = {
                "prompt_id":     pid,
                "run":           run,
                "task":          prompt_row["task"],
                "method":        prompt_row["method"],
                "source_game":   prompt_row["source"],
                "target_game":   prompt_row["target"],
                "context_label": prompt_row["context_label"],
                "context_types": prompt_row["context_types"],
                "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            try:
                full_instructions, file_attachments = assemble_prompt_with_attachments(prompt_row)
                entry["prompt_length"] = len(full_instructions)
                contents_payload = [full_instructions] + file_attachments

                print(f"  Sending to Gemini ({len(full_instructions)} chars instructions + {len(file_attachments)} attachments)...")
                t0 = time.time()

                for attempt in range(5):
                    try:
                        response = client.models.generate_content(
                            model=GEMINI_MODEL,
                            contents=contents_payload,
                            config={"temperature": TEMPERATURE, "max_output_tokens": MAX_OUTPUT_TOKENS, 
                                    "thinking_config": {"thinking_level": "HIGH"}},
                        )
                        break
                    except Exception as api_err:
                        if "429" in str(api_err) and attempt < 4:
                            wait = 30 * (2 ** attempt)
                            print(f"Rate limited, waiting {wait}s (attempt {attempt+1}/5)...")
                            time.sleep(wait)
                        else:
                            raise

                response_text = response.text or ""
                if not response_text:
                    raise ValueError("Gemini returned empty response")
                elapsed       = time.time() - t0
                entry["response_time_sec"] = round(elapsed, 2)
                entry["response_length"]   = len(response_text)
                finish = ""
                try:
                    fr = response.candidates[0].finish_reason
                    finish = getattr(fr, "name", None) or str(fr)
                except Exception:
                    pass
                entry["finish_reason"]      = finish
                entry["response_truncated"] = ("MAX_TOKENS" in finish)
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    entry["prompt_tokens"]   = getattr(usage, "prompt_token_count", None)
                    entry["output_tokens"]   = getattr(usage, "candidates_token_count", None)
                    entry["thinking_tokens"] = getattr(usage, "thoughts_token_count", None)

                trunc_note = "  ⚠ TRUNCATED (hit max_output_tokens)" if entry["response_truncated"] else ""
                print(f"  Response: {len(response_text)} chars in {elapsed:.1f}s "
                      f"(finish={finish or '?'}){trunc_note}")

                generated_files = extract_java_files(response_text)
                entry["generated_files"] = list(generated_files.keys())
                print(f"  Extracted: {list(generated_files.keys())}")

                if not generated_files:
                    entry.update({
                        "compilation_success": False,
                        "compilation_errors":  "No Java files extracted from response",
                        "compile_error_type":  "no_files_extracted",
                        "compile_error_message": "No Java files extracted from response",
                        "tests_run": 0, "tests_passed": 0, "tests_failed": 0, "test_results": {},
                    })
                    print("No files extracted!")
                else:
                    print("Compiling and testing...")
                    test_result = integrate_compile_test(
                        prompt_row["task"], generated_files, run_id=f"p{pid}_r{run}",
                    )
                    entry["compilation_success"]      = test_result["compilation_success"]
                    entry["compilation_errors"]       = _filter_compilation_output(test_result["compilation_errors"])
                    entry["compile_error_type"]       = test_result.get("compile_error_type", "")
                    entry["compile_error_message"]    = test_result.get("compile_error_message", "")
                    entry["test_compilation_errors"]  = test_result.get("test_compilation_errors", "")
                    entry["truncated_files"]          = test_result.get("truncated_files", [])
                    entry["tests_run"]     = test_result["tests_run"]
                    entry["tests_passed"]  = test_result["tests_passed"]
                    entry["tests_failed"]  = test_result["tests_failed"]
                    entry["test_results"]  = test_result["test_results"]
                    entry["error_categories"] = test_result.get("error_categories", {})
                    entry["primary_error"]    = test_result.get("primary_error", "")
                    entry["total_errors"]     = test_result.get("total_errors", 0)

                    status = "✅" if test_result["compilation_success"] else "❌"
                    print(f"  {status} Game+Generated compile: {test_result['compilation_success']}")
                    if test_result.get("truncated_files"):
                        print(f"Truncated (skipped): {test_result['truncated_files']}")
                    if test_result["compilation_success"]:
                        if test_result.get("test_compilation_errors"):
                            print(f" Test compilation failed (game compiled):")
                            for line in test_result["test_compilation_errors"].strip().split("\n")[:3]:
                                print(f"    | {line}")
                        else:
                            print(f"  Tests: {test_result['tests_passed']}/{test_result['tests_run']} passed")
                            for tname, tresult in test_result["test_results"].items():
                                print(f"    {'✅' if tresult == 'PASS' else '❌'} {tname}: {tresult}")
                    else:
                        primary = test_result.get("primary_error", "unknown")
                        total   = test_result.get("total_errors", 0)
                        print(f"  Primary error: {primary} ({total} total errors)")
                        for cat, count in sorted(test_result.get("error_categories", {}).items(), key=lambda x: -x[1]):
                            print(f"    {cat}: {count}")
                        for line in test_result["compilation_errors"].strip().split("\n")[:3]:
                            print(f"    | {line}")

                raw_path = os.path.join(OUTPUT_DIR, "raw_responses", f"p{pid}_r{run}.txt")
                with open(raw_path, "w") as f:
                    f.write(response_text)

            except Exception as e:
                print(f"  ❌ ERROR: {e}")
                traceback.print_exc()
                entry.update({
                    "compilation_success": False,
                    "compilation_errors":  f"API/Pipeline error: {str(e)}",
                    "compile_error_type":  "pipeline_error",
                    "compile_error_message": str(e)[:300],
                    "tests_run": 0, "tests_passed": 0, "tests_failed": 0, "test_results": {},
                })

            all_results.append(entry)
            with open(results_file, "w") as f:
                json.dump(all_results, f, indent=2)

            time.sleep(DELAY_BETWEEN_CALLS)

    print(f"\n\n{'=' * 60}")
    print(f"EXPERIMENT COMPLETE: {len(all_results)} results")
    print(f"   Results: {results_file}")
    return all_results



if __name__ == "__main__":
    setup()
    run_experiment()  