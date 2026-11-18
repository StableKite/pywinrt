"""Exercise last-apartment shutdown without a test suite's permanent MTA."""

import subprocess
import sys
import unittest


_PROBE = """
from sys import argv

from winrt.runtime import ApartmentType, init_apartment, uninit_apartment
from winrt.system import box_int32, unbox_int32
from winrt.windows.foundation import Uri

apartment = ApartmentType[argv[1]]
for _ in range(3):
    init_apartment(apartment)
    try:
        base = Uri("https://localhost/example/")
        child = base.combine_uri("child")
        assert child.absolute_uri == "https://localhost/example/child"
        boxed = box_int32(42)
        assert unbox_int32(boxed) == 42
        # Drop the objects before uninitializing their last COM apartment.
        del base, child, boxed
    finally:
        uninit_apartment()

print("three WinRT apartment cycles completed")
"""


class ApartmentLifecycleTests(unittest.TestCase):
    def test_reactivate_after_uninitializing_the_last_apartment(self) -> None:
        for apartment in ("MULTI_THREADED", "SINGLE_THREADED"):
            with self.subTest(apartment=apartment):
                process = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        "-X",
                        "faulthandler",
                        "-c",
                        _PROBE,
                        apartment,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(
                    process.returncode, 0, (process.stdout, process.stderr)
                )
                self.assertEqual(
                    process.stdout.strip(), "three WinRT apartment cycles completed"
                )


if __name__ == "__main__":
    unittest.main()
