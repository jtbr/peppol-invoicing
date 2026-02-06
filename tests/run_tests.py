#!/usr/bin/env python3
"""
Test runner for peppol_invoicing test suite.

Usage:
    python tests/run_tests.py              # Run all tests
    python tests/run_tests.py -v           # Verbose output
    python tests/run_tests.py --xml        # Output JUnit XML (for CI)
    python tests/run_tests.py TestClass    # Run specific test class
    python tests/run_tests.py TestClass.test_method  # Run specific test
"""

import unittest
import sys
import os
import argparse
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def discover_tests():
    """Discover all tests in the tests directory."""
    test_dir = os.path.dirname(os.path.abspath(__file__))
    loader = unittest.TestLoader()
    suite = loader.discover(test_dir, pattern='test_*.py')
    return suite


def run_specific_tests(test_names):
    """Run specific test classes or methods."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Import test modules
    from tests import test_utils, test_en16931_invoice

    modules = {
        'test_utils': test_utils,
        'test_en16931_invoice': test_en16931_invoice,
    }

    for name in test_names:
        if '.' in name:
            # Specific test method: TestClass.test_method
            parts = name.split('.')
            class_name = parts[0]
            method_name = parts[1] if len(parts) > 1 else None

            # Find the class
            for module in modules.values():
                if hasattr(module, class_name):
                    cls = getattr(module, class_name)
                    if method_name:
                        suite.addTest(cls(method_name))
                    else:
                        suite.addTests(loader.loadTestsFromTestCase(cls))
                    break
        else:
            # Full test class
            for module in modules.values():
                if hasattr(module, name):
                    cls = getattr(module, name)
                    suite.addTests(loader.loadTestsFromTestCase(cls))
                    break

    return suite


class SummaryResult(unittest.TextTestResult):
    """Custom test result that provides a clear summary."""

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.successes = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.append(test)


def print_summary(result, duration):
    """Print a human-readable summary."""
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    total = result.testsRun
    passed = len(result.successes)
    failed = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)

    print(f"  Total:   {total}")
    print(f"  Passed:  {passed} ✓")
    if failed > 0:
        print(f"  Failed:  {failed} ✗")
    if errors > 0:
        print(f"  Errors:  {errors} !")
    if skipped > 0:
        print(f"  Skipped: {skipped} -")
    print(f"  Time:    {duration:.2f}s")
    print("-" * 70)

    if failed == 0 and errors == 0:
        print("  RESULT:  ALL TESTS PASSED ✓")
    else:
        print("  RESULT:  SOME TESTS FAILED ✗")
        if result.failures:
            print("\n  Failed tests:")
            for test, _ in result.failures:
                print(f"    - {test}")
        if result.errors:
            print("\n  Errors:")
            for test, _ in result.errors:
                print(f"    - {test}")

    print("=" * 70)

    return failed == 0 and errors == 0


def main():
    parser = argparse.ArgumentParser(description='Run peppol_invoicing tests')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')
    parser.add_argument('--xml', metavar='FILE',
                        help='Output JUnit XML to file')
    parser.add_argument('tests', nargs='*',
                        help='Specific tests to run (TestClass or TestClass.test_method)')
    args = parser.parse_args()

    # Determine verbosity
    verbosity = 2 if args.verbose else 1

    # Get test suite
    if args.tests:
        suite = run_specific_tests(args.tests)
    else:
        suite = discover_tests()

    # Run tests
    start_time = datetime.now()

    if args.xml:
        # XML output for CI systems
        try:
            import xmlrunner
            with open(args.xml, 'wb') as output:
                runner = xmlrunner.XMLTestRunner(output=output, verbosity=verbosity)
                result = runner.run(suite)
        except ImportError:
            print("Warning: xmlrunner not installed, using text output")
            print("Install with: pip install unittest-xml-reporting")
            runner = unittest.TextTestRunner(verbosity=verbosity, resultclass=SummaryResult)
            result = runner.run(suite)
    else:
        runner = unittest.TextTestRunner(verbosity=verbosity, resultclass=SummaryResult)
        result = runner.run(suite)

    duration = (datetime.now() - start_time).total_seconds()

    # Print summary
    success = print_summary(result, duration)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
