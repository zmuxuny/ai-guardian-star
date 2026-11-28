"""Include the three pinned upstream suites in root unittest discovery."""
import importlib.util
from pathlib import Path
import sys
import unittest


def load_tests(loader, tests, pattern):
    for filename in ('test_late_wakeup_demo.py', 'test_routine_alert_demo.py', 'test_personalization_http.py'):
        name = 'adopted_personalization_' + filename[:-3]
        spec = importlib.util.spec_from_file_location(name, Path(__file__).parent/'tests'/filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        tests.addTests(loader.loadTestsFromModule(module))
    return tests
