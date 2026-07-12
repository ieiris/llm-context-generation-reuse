import importlib.util, os, json, glob, re, shutil, subprocess, tempfile, time


GAME_ROOT   = ""  # game compiled against
GEN_ROOT    = ""  # run.py lives here
RESULTS_DIR = ""  # run output_dir (has experiment_results.json + raw_responses/)
INTEG       = ""
DRIVER      = ""  # path to IntegrationDriver.java
INVOKED_DIR = ""
LIB         = ""  # path to library jars
GEN         = ""
INVOKED = {"Highscore": "ApoMarioHighscoreInvokedTest", "Achievements": "ApoMarioAchievementsInvokedTest"}
RUN_TIMEOUT = 90
ONLY_COMPILED = True         
SEP = ":"

_spec = importlib.util.spec_from_file_location("genrun", GEN)
gr = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(gr)
gr.PROJECT_BASE = GAME_ROOT; gr.GAME_PROJECTS = {"ApoMario": GAME_ROOT}; gr.build_import_index()


def _result(outcome, detail, test_results=None, fail_msgs=None):
    tr = test_results or {}
    failed = sum(1 for v in tr.values() if v == "FAIL")
    return {"outcome": outcome, "detail": detail, "test_results": tr,
            "test_failure_messages": fail_msgs or {},
            "tests_passed": sum(1 for v in tr.values() if v == "PASS"), "tests_failed": failed}


def run_invoked(new_files, task, rid):
    test_cls = INVOKED.get(task)
    if not test_cls:
        return _result("no-invoked-test", "")
    work = tempfile.mkdtemp(prefix=f"invoked_{rid}_"); proj = os.path.join(work, "project")
    try:
        os.makedirs(proj)
        for sub in ("apoMario", "org", "test", "images", "levels", "META-INF"):
            s = os.path.join(GAME_ROOT, sub)
            if os.path.isdir(s):
                shutil.copytree(s, os.path.join(proj, sub),
                                ignore=lambda d, n: {x for x in n if x.endswith(".class") and os.path.basename(d) != "test"})
        for p in glob.glob(os.path.join(GAME_ROOT, "*.properties")):
            shutil.copy(p, proj)
        gr.convert_to_utf8(proj)
        panels = os.path.join(proj, "apoMario", "game", "panels"); os.makedirs(panels, exist_ok=True)
        test_src = open(os.path.join(INVOKED_DIR, f"{test_cls}.java"), encoding="utf-8").read()
        aux_paths = set()
        for fn, code in new_files.items():
            cls = fn[:-5]
            if gr.find_java_file(proj, cls):                       
                continue
            code = gr.autofix_imports(code, "ApoMario")
            code = gr.inject_missing_imports(code, "ApoMario")
            code = gr.fix_reserved_keyword_methods(code)
            code = gr.fix_generated_package(code, "apoMario.game.panels")
            dest = os.path.join(panels, fn)
            open(dest, "w", encoding="utf-8").write(code)
            if not re.search(rf"\b{re.escape(cls)}\b", test_src):
                aux_paths.add(dest)
        shutil.copy(DRIVER, panels)
        shutil.copy(os.path.join(INVOKED_DIR, f"{test_cls}.java"), panels)

        cp = f"{os.path.join(LIB,'junit-4.13.2.jar')}{SEP}{os.path.join(LIB,'hamcrest-core-1.3.jar')}{SEP}{proj}"
        classes = os.path.join(work, "classes"); os.makedirs(classes)
        srcs = [os.path.join(r, f) for sub in ("apoMario", "org")
                for r, _, fs in os.walk(os.path.join(proj, sub)) for f in fs if f.endswith(".java")]
        srcs = [p for p in srcs if p not in aux_paths]
        rc = subprocess.run(["javac", "-encoding", "UTF-8", "-nowarn", "-sourcepath", proj,
                             "-cp", cp, "-d", classes] + srcs, capture_output=True, text=True, timeout=300)
        if rc.returncode != 0:
            lines = gr._filter_compilation_output(rc.stderr).split("\n")
            i = next((k for k, l in enumerate(lines) if "error:" in l), None)
            detail = "" if i is None else " | ".join(             
                l.strip() for l in lines[i:i + 3] if l.strip()).replace(proj + os.sep, "")
            return _result("compile-fail", detail[:300])

        rundir = os.path.join(work, "run"); os.makedirs(rundir)
        try:
            rt = subprocess.run(["java", "-Djava.awt.headless=false", "-cp", f"{classes}{SEP}{cp}",
                                 "org.junit.runner.JUnitCore", f"apoMario.game.panels.{test_cls}"],
                                capture_output=True, text=True, cwd=rundir, timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            return _result("run-timeout", "")
        out = rt.stdout + rt.stderr
        names = re.findall(r"@Test\s+public\s+void\s+(\w+)",
                           open(os.path.join(INVOKED_DIR, f"{test_cls}.java"), encoding="utf-8").read())
        ran = re.search(r"OK\s*\((\d+)\s+test", out) or re.search(r"Tests run:\s*(\d+)", out)
        if not ran:                                       
            first = next((l for l in out.split("\n") if "Exception" in l or "Error" in l), "")
            return _result("boot-error", first.strip()[-160:], {n: "ERROR" for n in names})
        run_count = int(ran.group(1))
        if run_count == 0:                       
            first = next((l for l in out.split("\n") if "Exception" in l or "Error" in l), "")
            return _result("boot-error", first.strip()[-160:], {n: "ERROR" for n in names})
        test_results = {n: "PASS" for n in names}
        fail_msgs = {}
        current = None
        for line in out.split("\n"):
            mm = re.match(r"\d+\)\s+(\w+)\(", line)        
            if mm:
                current = mm.group(1); test_results[current] = "FAIL"; fail_msgs[current] = ""; continue
            if current and fail_msgs.get(current) == "":
                s = line.strip()
                if s and not s.startswith("at "):
                    fail_msgs[current] = s[:300]
        failed = sum(1 for v in test_results.values() if v == "FAIL")
        if run_count != len(names):                        
            for n in names:                               
                if test_results[n] == "PASS":
                    test_results[n] = "NOT_RUN"
            return _result("count-mismatch", f"ran {run_count} of {len(names)} @Tests", test_results, fail_msgs)
        detail = f"{failed}/{len(names)} failed" if failed else f"{len(names)} tests"
        return _result("PASS" if failed == 0 else "FAIL", detail, test_results, fail_msgs)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    results = json.load(open(os.path.join(RESULTS_DIR, "experiment_results.json")))
    raw = os.path.join(RESULTS_DIR, "raw_responses")
    out_rows = []
    for e in results:
        if ONLY_COMPILED and not e.get("compilation_success"):
            continue
        task = e["task"]; pid = e["prompt_id"]; run = e["run"]; ctx = e.get("context_label", "?")
        rawf = os.path.join(raw, f"p{pid}_r{run}.txt")
        if not os.path.exists(rawf):
            continue
        files = gr.extract_java_files(open(rawf).read())
        res = run_invoked(files, task, f"p{pid}_r{run}") if files else _result("no-class", "")
        print(f"  p{pid:<3} r{run} {task[:4]}/{ctx:6s}: {res['outcome']:12s} {res['detail']}")
        for tname, st in res["test_results"].items():                     
            if st == "FAIL":
                print(f"        ✗ {tname}: {res['test_failure_messages'].get(tname, '')[:140]}")
        out_rows.append({"prompt_id": pid, "run": run, "task": task, "context_label": ctx,
                         "invoked_outcome": res["outcome"], "invoked_pass": res["outcome"] == "PASS",
                         "detail": res["detail"],
                         "compile_error": res["detail"] if res["outcome"] in ("compile-fail", "boot-error") else "",
                         "tests_passed": res["tests_passed"], "tests_failed": res["tests_failed"],
                         "test_results": res["test_results"], "test_failure_messages": res["test_failure_messages"]})
    outfile = os.path.join(RESULTS_DIR, "invoked_results.json")
    json.dump(out_rows, open(outfile, "w"), indent=2)

    import collections
    print("\n=== all-invoked-tests-pass rate by task x context (of compiled responses) ===")
    by = collections.defaultdict(lambda: [0, 0])
    for r in out_rows:
        by[(r["task"], r["context_label"])][0] += 1 if r["invoked_pass"] else 0
        by[(r["task"], r["context_label"])][1] += 1
    for k in sorted(by):
        print(f"  {k[0]:13s} {k[1]:7s}: {by[k][0]}/{by[k][1]}")

    print("\n=== per-test PASS rate by task x context x test (full detail in invoked_results.json) ===")
    pt = collections.defaultdict(lambda: [0, 0])
    for r in out_rows:
        for tname, st in r["test_results"].items():
            pt[(r["task"], r["context_label"], tname)][0] += 1 if st == "PASS" else 0
            pt[(r["task"], r["context_label"], tname)][1] += 1
    for k in sorted(pt):
        print(f"  {k[0][:4]} {k[1]:6s} {k[2]:34s}: {pt[k][0]}/{pt[k][1]}")
    print(f"\nwrote {outfile}  ({len(out_rows)} responses)")


if __name__ == "__main__":
    main()
