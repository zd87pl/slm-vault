#!/usr/bin/env python3
"""
Test runner for DoRA WDVA test suite.

Runs all tests and generates a coverage report.
"""

import unittest
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_tests(verbosity=2, pattern='test_*.py', failfast=False):
    """
    Discover and run all tests.

    Args:
        verbosity: Test output verbosity (0, 1, or 2)
        pattern: Test file pattern
        failfast: Stop on first failure

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print("=" * 80)
    print("DoRA WDVA Test Suite")
    print("=" * 80)

    # Discover tests
    loader = unittest.TestLoader()
    start_dir = Path(__file__).parent
    suite = loader.discover(start_dir, pattern=pattern)

    # Count tests
    test_count = suite.countTestCases()
    print(f"\nDiscovered {test_count} tests\n")

    # Run tests
    start_time = time.time()
    runner = unittest.TextTestRunner(
        verbosity=verbosity,
        failfast=failfast
    )
    result = runner.run(suite)
    elapsed = time.time() - start_time

    # Print summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print(f"Time: {elapsed:.2f}s")

    if result.wasSuccessful():
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed")

    print("=" * 80)

    # Return exit code
    return 0 if result.wasSuccessful() else 1


def run_specific_suite(suite_name):
    """
    Run a specific test suite.

    Args:
        suite_name: Name of test suite (e.g., 'encryption', 'cache', 'integration')

    Returns:
        Exit code
    """
    pattern_map = {
        'encryption': 'test_encryption.py',
        'cache': 'test_adapter_cache.py',
        'dora': 'test_dora_weights.py',
        'inference': 'test_ephemeral_inference.py',
        'integration': 'test_integration.py',
        'errors': 'test_error_handling.py',
        'performance': 'test_performance.py',
    }

    pattern = pattern_map.get(suite_name, f'test_{suite_name}.py')
    print(f"\nRunning {suite_name} tests (pattern: {pattern})\n")

    return run_tests(verbosity=2, pattern=pattern)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run DoRA WDVA tests')
    parser.add_argument(
        '--suite',
        choices=['encryption', 'cache', 'dora', 'inference', 'integration',
                'errors', 'performance', 'all'],
        default='all',
        help='Test suite to run'
    )
    parser.add_argument(
        '--failfast',
        action='store_true',
        help='Stop on first failure'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    verbosity = 2 if args.verbose else 1

    if args.suite == 'all':
        exit_code = run_tests(verbosity=verbosity, failfast=args.failfast)
    else:
        exit_code = run_specific_suite(args.suite)

    sys.exit(exit_code)
