"""Tests for the --parser flag of Context_gen (step A6).

generate_context(..., parser="regex" | "ast") picks the per-file parser; the rest of the pipeline
(flatten_inheritance, split_contexts, writing the JSONs) is the same. The default is "regex", so the
existing behaviour does not change. tree-sitter is imported only for parser="ast".
"""
import json
import os
import subprocess
import sys
import zipfile

import pytest

import Context_gen
import java_ast

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(PIPELINE_DIR, "tests", "java_samples")
CONTEXT_GEN = os.path.join(PIPELINE_DIR, "Context_gen.py")
GAME = "Sample"
KINDS = ("Context", "Structural", "Functional", "Behavioral")

# CallInComment is a known A4 deviation (regex takes calls from comments), so regex != AST on it.
SAMPLE_FILES = [
    "a4/CallInComment.java",
    "a4/ConstructorCalls.java",
    "a4/ReceiverForms.java",
    "a3/OverrideMethods.java",
]


@pytest.fixture
def sample_zip(tmp_path):
    path = tmp_path / "Sample.zip"
    with zipfile.ZipFile(path, "w") as z:
        for rel in SAMPLE_FILES:
            z.write(os.path.join(SAMPLES, *rel.split("/")), rel)
    return str(path)


def _read_outputs(out_dir):
    result = {}
    for kind in KINDS:
        with open(os.path.join(out_dir, f"{GAME}_{kind}.json"), "rb") as f:
            result[kind] = f.read()
    return result


def _expected(analyze):
    """The pipeline of generate_context by hand, with the given per-file parser."""
    full = {}
    for rel in SAMPLE_FILES:
        with open(os.path.join(SAMPLES, *rel.split("/")), encoding="utf-8", errors="ignore") as f:
            data = analyze(f.read(), os.path.basename(rel))
        if data:
            full[data["module"]] = data
    full = Context_gen.flatten_inheritance(full)
    s, f_, b = Context_gen.split_contexts(full)
    return dict(zip(KINDS, (full, s, f_, b)))


def _loads(outputs):
    return {k: json.loads(v) for k, v in outputs.items()}


def _run_cli(*args):
    return subprocess.run([sys.executable, "-B", CONTEXT_GEN, *args],
                          capture_output=True, text=True, cwd=PIPELINE_DIR)


def test_default_parser_is_regex(sample_zip, tmp_path):
    Context_gen.generate_context(sample_zip, GAME, str(tmp_path / "default"))
    Context_gen.generate_context(sample_zip, GAME, str(tmp_path / "regex"), parser="regex")
    default = _read_outputs(tmp_path / "default")
    assert default == _read_outputs(tmp_path / "regex")
    assert _loads(default) == _expected(Context_gen.analyze_java_file)


def test_ast_parser_uses_java_ast(sample_zip, tmp_path):
    Context_gen.generate_context(sample_zip, GAME, str(tmp_path / "ast"), parser="ast")
    Context_gen.generate_context(sample_zip, GAME, str(tmp_path / "regex"), parser="regex")
    ast_out = _loads(_read_outputs(tmp_path / "ast"))
    assert ast_out == _expected(java_ast.analyze_java_file_ast)
    # The flag really switches the parser: the known A4 deviation shows up in the output.
    regex_out = _loads(_read_outputs(tmp_path / "regex"))
    assert regex_out["Behavioral"] != ast_out["Behavioral"]
    assert list(ast_out["Context"]) == list(regex_out["Context"])  # same modules, same order


def test_unknown_parser_raises_before_writing(sample_zip, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="Unknown parser"):
        Context_gen.generate_context(sample_zip, GAME, str(out), parser="javaparser")
    assert not out.exists()


@pytest.mark.parametrize("flags", [
    ["--parser", "ast"],
    ["--subtypes", "S_fields", "B_calls", "--parser", "ast"],
    ["--parser", "ast", "--subtypes", "S_fields", "B_calls"],
])
def test_cli_parser_ast(sample_zip, tmp_path, flags):
    out = tmp_path / "cli"
    r = _run_cli("generate", GAME, sample_zip, str(out), *flags)
    assert r.returncode == 0, r.stderr
    assert _loads(_read_outputs(out)) == _expected(java_ast.analyze_java_file_ast)
    if "--subtypes" in flags:
        expected_subtypes = {"S_fields", "B_calls"}
    else:
        expected_subtypes = set(Context_gen.VALID_SUBTYPES)
    written = {n[len(GAME) + 1:-len(".json")] for n in os.listdir(out)} - set(KINDS)
    assert written == expected_subtypes


def test_cli_without_flag_is_regex(sample_zip, tmp_path):
    r = _run_cli("generate", GAME, sample_zip, str(tmp_path / "cli"))
    assert r.returncode == 0, r.stderr
    assert _loads(_read_outputs(tmp_path / "cli")) == _expected(Context_gen.analyze_java_file)


def test_cli_unknown_parser_fails_without_output(sample_zip, tmp_path):
    out = tmp_path / "cli"
    r = _run_cli("generate", GAME, sample_zip, str(out), "--parser", "bogus")
    assert r.returncode != 0
    assert "Unknown parser" in r.stderr
    assert not out.exists()


def test_regex_path_does_not_load_tree_sitter(sample_zip, tmp_path):
    code = (
        "import sys, Context_gen\n"
        f"Context_gen.generate_context({sample_zip!r}, {GAME!r}, {str(tmp_path / 'o')!r})\n"
        "print('tree_sitter' in sys.modules, 'java_ast' in sys.modules)\n"
    )
    r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True,
                       cwd=PIPELINE_DIR)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "False False"
