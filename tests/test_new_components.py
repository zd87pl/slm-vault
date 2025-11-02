#!/usr/bin/env python3
"""
Test runner for new components.

Run all tests for:
- Adapter registry API
- Cloud sync service
- PDF processor
- RunPod handler user isolation
"""

import unittest
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))

def run_tests():
    """Run all test suites."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test modules
    try:
        # Adapter registry tests
        from advanced_vault.backend.tests.test_adapters import (
            TestAdapterRegistryHelpers,
            TestAdapterRegistryAPI
        )
        suite.addTests(loader.loadTestsFromTestCase(TestAdapterRegistryHelpers))
        suite.addTests(loader.loadTestsFromTestCase(TestAdapterRegistryAPI))
        print("✓ Loaded adapter registry tests")
    except ImportError as e:
        print(f"⚠ Could not load adapter registry tests: {e}")
    
    try:
        # Cloud sync tests
        from advanced_vault.gui.tests.test_cloud_sync import TestCloudSyncService
        suite.addTests(loader.loadTestsFromTestCase(TestCloudSyncService))
        print("✓ Loaded cloud sync tests")
    except ImportError as e:
        print(f"⚠ Could not load cloud sync tests: {e}")
    
    try:
        # PDF processor tests
        from advanced_vault.gui.tests.test_pdf_processor import TestPDFProcessor
        suite.addTests(loader.loadTestsFromTestCase(TestPDFProcessor))
        print("✓ Loaded PDF processor tests")
    except ImportError as e:
        print(f"⚠ Could not load PDF processor tests: {e}")
    
    try:
        # RunPod handler tests
        from tests.test_rp_handler_user_isolation import (
            TestRunPodHandlerUserIsolation,
            TestRunPodHandlerFunctionSignatures
        )
        suite.addTests(loader.loadTestsFromTestCase(TestRunPodHandlerUserIsolation))
        suite.addTests(loader.loadTestsFromTestCase(TestRunPodHandlerFunctionSignatures))
        print("✓ Loaded RunPod handler tests")
    except ImportError as e:
        print(f"⚠ Could not load RunPod handler tests: {e}")
    
    # Run tests
    print("\n" + "="*60)
    print("Running Tests")
    print("="*60 + "\n")
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f" Skipped: {len(result.skipped)}")
    
    if result.wasSuccessful():
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback.split(chr(10))[-1]}")
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback.split(chr(10))[-1]}")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())


