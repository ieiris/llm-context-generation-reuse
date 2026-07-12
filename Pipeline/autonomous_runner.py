import importlib.util, os, json, re, shutil, subprocess, tempfile

BASE        = ""
RESULTS_DIR = ""  # experiment output to grade
TESTS_DIR   = ""  # holds the *AutonomousTest.java files
GEN = ""
LIB        = ""
RUN_TIMEOUT = 120
SEP = ":"

TASKS = {
    "Highscore": {
        "game_root": os.path.join(BASE, "ApoMario"), "game_name": "ApoMario",
        "driver": os.path.join(BASE, "integration", "IntegrationDriver.java"),
        "test": "ApoMarioHighscoreAutonomousTest", "pkg_dir": "apoMario/game/panels",
        "gen_pkg": "apoMario.game.panels", "test_pkg": "apoMario.game.panels",
        "subs": ("apoMario", "org", "test", "images", "levels", "META-INF"),
    },
    "Achievements": {
        "game_root": os.path.join(BASE, "ApoMario"), "game_name": "ApoMario",
        "driver": os.path.join(BASE, "integration", "IntegrationDriver.java"),
        "test": "ApoMarioAchievementsAutonomousTest", "pkg_dir": "apoMario/game/panels",
        "gen_pkg": "apoMario.game.panels", "test_pkg": "apoMario.game.panels",
        "subs": ("apoMario", "org", "test", "images", "levels", "META-INF"),
    },
    "Options": {
        "game_root": os.path.join(BASE, "ApoBot"), "game_name": "ApoBot",
        "driver": os.path.join(TESTS_DIR, "IntegrationDriver.java"),   
        "test": "ApoBotOptionsAutonomousTest", "pkg_dir": "apoBot/game",
        "gen_pkg": "apoBot.game", "test_pkg": "apoBot.game",
        "subs": ("apoBot", "org", "images", "levels"),
    },
}

_spec = importlib.util.spec_from_file_location("genrun", GEN)
gr = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(gr)


def _result(outcome, detail, test_results=None, fail_msgs=None):
    tr = test_results or {}
    return {"outcome": outcome, "detail": detail, "test_results": tr,
            "test_failure_messages": fail_msgs or {},
            "tests_passed": sum(1 for v in tr.values() if v == "PASS"),
            "tests_failed": sum(1 for v in tr.values() if v == "FAIL")}


def run_autonomous(new_files, task, rid):
    c = TASKS[task]
    gr.PROJECT_BASE = c["game_root"]
    gr.GAME_PROJECTS = {c["game_name"]: c["game_root"]}
    gr.build_import_index()
    work = tempfile.mkdtemp(prefix=f"auto_{rid}_"); proj = os.path.join(work, "project")
    try:
        os.makedirs(proj)
        for sub in c["subs"]:
            s = os.path.join(c["game_root"], sub)
            if os.path.isdir(s):
                shutil.copytree(s, os.path.join(proj, sub),
                                ignore=lambda d, n: {x for x in n if x.endswith(".class") and os.path.basename(d) != "test"})
        import glob
        for pfile in glob.glob(os.path.join(c["game_root"], "*.properties")):
            shutil.copy(pfile, proj)
        gr.convert_to_utf8(proj)

        for fn, code in new_files.items():
            cls = fn[:-5]
            dest, pkg, overwrote = gr.resolve_generated_placement(
                cls, code, proj, c["gen_pkg"], c["pkg_dir"])
            code = gr.autofix_imports(code, c["game_name"])
            code = gr.inject_missing_imports(code, c["game_name"])
            code = gr.fix_reserved_keyword_methods(code)
            code = gr.fix_generated_package(code, pkg)
            if not gr.code_braces_balanced(code):
                return _result("truncated-file", fn)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "w", encoding="utf-8").write(code)

        pkg_path = os.path.join(proj, *c["pkg_dir"].split("/")); os.makedirs(pkg_path, exist_ok=True)
        shutil.copy(c["driver"], pkg_path)
        shutil.copy(os.path.join(TESTS_DIR, f"{c['test']}.java"), pkg_path)

        cp = f"{os.path.join(LIB,'junit-4.13.2.jar')}{SEP}{os.path.join(LIB,'hamcrest-core-1.3.jar')}{SEP}{proj}"
        classes = os.path.join(work, "classes"); os.makedirs(classes)
        srcs = [os.path.join(r, f) for sub in c["subs"][:2]
                for r, _, fs in os.walk(os.path.join(proj, sub)) for f in fs if f.endswith(".java")]
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
                                 "org.junit.runner.JUnitCore", f"{c['test_pkg']}.{c['test']}"],
                                capture_output=True, text=True, cwd=rundir, timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            return _result("run-timeout", "")
        out = rt.stdout + rt.stderr
        names = re.findall(r"@Test\s+public\s+void\s+(\w+)",
                           open(os.path.join(TESTS_DIR, f"{c['test']}.java"), encoding="utf-8").read())
        ran = re.search(r"OK\s*\((\d+)\s+test", out) or re.search(r"Tests run:\s*(\d+)", out)
        if not ran:
            first = next((l for l in out.split("\n") if "Exception" in l or "Error" in l), "")
            return _result("boot-error", first.strip()[-160:], {n: "ERROR" for n in names})
        test_results = {n: "PASS" for n in names}; fail_msgs = {}; current = None
        for line in out.split("\n"):
            mm = re.match(r"\d+\)\s+(\w+)\(", line)
            if mm:
                current = mm.group(1); test_results[current] = "FAIL"; fail_msgs[current] = ""; continue
            if current and fail_msgs.get(current) == "":
                s = line.strip()
                if s and not s.startswith("at "):
                    fail_msgs[current] = s[:300]
        run_count = int(ran.group(1))
        if run_count == 0:                       
            first = next((l for l in out.split("\n") if "Exception" in l or "Error" in l), "")
            return _result("boot-error", first.strip()[-160:], {n: "ERROR" for n in names})
        if run_count != len(names):
            for n in names:
                if test_results[n] == "PASS": test_results[n] = "NOT_RUN"
            return _result("count-mismatch", f"ran {run_count} of {len(names)}", test_results, fail_msgs)
        failed = sum(1 for v in test_results.values() if v == "FAIL")
        return _result("PASS" if failed == 0 else "FAIL",
                       f"{failed}/{len(names)} failed" if failed else f"{len(names)} tests",
                       test_results, fail_msgs)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    results = json.load(open(os.path.join(RESULTS_DIR, "experiment_results.json")))
    out_rows = []
    for e in results:
        if not e.get("compilation_success") or e.get("task") not in TASKS:
            continue
        rawf = os.path.join(RESULTS_DIR, "raw_responses", f"p{e['prompt_id']}_r{e['run']}.txt")
        if not os.path.exists(rawf):
            continue
        files = gr.extract_java_files(open(rawf).read())
        res = run_autonomous(files, e["task"], f"p{e['prompt_id']}_r{e['run']}")
        print(f"  p{e['prompt_id']:<3} r{e['run']} {e['task'][:4]}/{e.get('context_label','?'):6s}: "
              f"{res['outcome']:12s} {res['detail']}")
        for t, st in res["test_results"].items():
            if st == "FAIL":
                print(f"        ✗ {t}: {res['test_failure_messages'].get(t, '')[:140]}")
        out_rows.append({"prompt_id": e["prompt_id"], "run": e["run"], "task": e["task"],
                         "context_label": e.get("context_label", "?"),
                         "autonomous_outcome": res["outcome"], "autonomous_pass": res["outcome"] == "PASS",
                         "detail": res["detail"],
                         "tests_passed": res["tests_passed"], "tests_failed": res["tests_failed"],
                         "test_results": res["test_results"],
                         "test_failure_messages": res["test_failure_messages"]})
    outfile = os.path.join(RESULTS_DIR, "autonomous_results.json")
    json.dump(out_rows, open(outfile, "w"), indent=2)
    print(f"\nwrote {outfile}  ({len(out_rows)} responses)")


if __name__ == "__main__":
    main()
