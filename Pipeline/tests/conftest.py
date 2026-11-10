import os
import sys

# Make modules in Pipeline/ (compare_contexts, later java_ast) importable from the tests.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
