"""Application diagnostic logging stays bounded and has one file handler."""

import logging
import tempfile
import unittest
from pathlib import Path

from main import configure_application_logging


class DiagnosticsTests(unittest.TestCase):
    def test_logging_uses_bounded_rotation_and_reuses_its_handler(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = configure_application_logging(Path(folder))
            handlers = [
                handler for handler in logger.handlers
                if getattr(handler, "_attendance_handler", False)
            ]
            try:
                self.assertEqual(len(handlers), 1)
                self.assertEqual(handlers[0].maxBytes, 1_000_000)
                self.assertEqual(handlers[0].backupCount, 3)
                self.assertEqual(
                    configure_application_logging(Path(folder)), logger
                )
                self.assertEqual(
                    len([handler for handler in logger.handlers
                         if getattr(handler, "_attendance_handler", False)]),
                    1,
                )
                logger.info("synthetic storage diagnostic")
                handlers[0].flush()
                log_path = Path(folder) / "application.log"
                self.assertIn(
                    "synthetic storage diagnostic",
                    log_path.read_text(encoding="utf-8"),
                )
            finally:
                for handler in handlers:
                    logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
