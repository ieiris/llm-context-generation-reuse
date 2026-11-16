"""Tests for values_hint and assets in the regex parser (Pipeline/Context_gen.py), step 3.

Rule (decision 11): no duplicates, order of first appearance in the code, values_hint cut to the
first six distinct numbers. The output must not depend on PYTHONHASHSEED (list(set(...)) did).
"""
import json
import os
import subprocess
import sys

import Context_gen

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SOURCE = """\
package org.example.game;

public class Game {

    private int score;

    public Game() {
        this.score = 70;
        int a = 90 + 80 + 70 + 60;
    }

    public void tick() {
        int a = 50 + 10;
        int b = 50 * 300 + 10;
        int c = 4000 - 25;
    }

    public void render() {
        int a = 11 + 22 + 33 + 11 + 44 + 55 + 66 + 77 + 88 + 22;
    }

    public void load() {
        String s = "images/a.png";
        String t = "sounds/b.wav";
        String u = "images/a.png";
        String v = "images/c.gif";
        String w = "sounds/b.wav";
        String x = "fonts/d.ttf";
    }
}
"""


def _analyze():
    return Context_gen.analyze_java_file(SOURCE, "Game.java")


def test_values_hint_dedup_in_order_of_appearance():
    m = _analyze()["methods"]["tick"]
    assert m["values_hint"] == ["50", "10", "300", "4000", "25"]


def test_values_hint_takes_first_six_distinct():
    # 8 distinct numbers (11 and 22 repeated); [:6] must take the first six by appearance.
    m = _analyze()["methods"]["render"]
    assert m["values_hint"] == ["11", "22", "33", "44", "55", "66"]


def test_values_hint_constructor():
    m = _analyze()["methods"]["Game_constructor_0"]
    assert m["values_hint"] == ["70", "90", "80", "60"]


def test_assets_dedup_in_order_of_appearance():
    assert _analyze()["assets"] == ["images/a.png", "sounds/b.wav", "images/c.gif", "fonts/d.ttf"]


_CHILD = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import Context_gen\n"
    "src = sys.stdin.read()\n"
    "r = Context_gen.analyze_java_file(src, 'Game.java')\n"
    "out = {'assets': r['assets'],\n"
    "       'values_hint': {k: v['values_hint'] for k, v in r['methods'].items()}}\n"
    "print(json.dumps(out))\n"
)


def _analyze_with_seed(seed):
    env = dict(os.environ, PYTHONHASHSEED=str(seed), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, PIPELINE_DIR],
        input=SOURCE, capture_output=True, text=True, env=env, check=True,
    )
    return json.loads(proc.stdout)


def test_output_does_not_depend_on_hash_seed():
    results = {seed: _analyze_with_seed(seed) for seed in (0, 1, 2, 3)}
    assert all(r == results[0] for r in results.values()), results
    # And the in-process result is the same as in the child processes.
    r = _analyze()
    assert results[0]["assets"] == r["assets"]
    assert results[0]["values_hint"] == {k: v["values_hint"] for k, v in r["methods"].items()}
