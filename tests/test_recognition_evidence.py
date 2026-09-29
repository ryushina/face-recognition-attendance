import unittest

from recognition_evidence import RecognitionEvidenceTracker
from recognition_service import MatchResult


def recognized(student_id="007", name="Lin Tan"):
    return MatchResult("recognized", student_id, name, 0.92, 0.2)


class RecognitionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tracker = RecognitionEvidenceTracker(3, 2.0, 1.0)

    def observe(self, result, frame_id, captured, now=None, **kwargs):
        return self.tracker.observe(
            result, frame_id=frame_id, captured_monotonic=captured,
            now_monotonic=captured if now is None else now, **kwargs
        )

    def test_requires_three_distinct_fresh_frames_and_returns_last_evidence(self):
        for frame_id in (1, 2):
            self.assertIsNone(self.observe(recognized(), frame_id, frame_id * 0.1))
        stable = self.observe(recognized(), 3, 0.3)
        self.assertEqual(stable.student_id, "007")
        self.assertEqual(stable.frame_id, 3)
        self.assertEqual(stable.consecutive_frames, 3)

    def test_duplicate_or_out_of_order_frame_does_not_count(self):
        self.observe(recognized(), 5, 0.1)
        self.assertIsNone(self.observe(recognized(), 5, 0.2))
        self.assertIsNone(self.observe(recognized(), 4, 0.3))
        self.assertIsNone(self.observe(recognized(), 6, 0.4))
        self.assertIsNotNone(self.observe(recognized(), 7, 0.5))

    def test_unknown_identity_change_camera_loss_pause_and_stale_reset(self):
        self.observe(recognized(), 1, 0.1)
        self.observe(recognized(), 2, 0.2)
        self.assertIsNone(self.observe(MatchResult("unknown"), 3, 0.3))
        self.observe(recognized(), 4, 0.4)
        self.observe(recognized(), 5, 0.5)
        self.assertIsNone(self.observe(recognized("008"), 6, 0.6))
        self.assertIsNone(self.observe(recognized(), 7, 0.7, camera_available=False))
        self.observe(recognized(), 8, 0.8)
        self.assertIsNone(self.observe(recognized(), 9, 0.9, enabled=False))
        self.observe(recognized(), 10, 1.0)
        self.assertIsNone(self.observe(recognized(), 11, 0.0, now=2.0))
        self.assertIsNone(self.observe(recognized(), 12, 2.1))

    def test_capture_window_and_slow_results_restart_evidence(self):
        self.observe(recognized(), 1, 0.1)
        self.assertIsNone(self.observe(recognized(), 2, 2.2))
        self.assertIsNone(self.observe(recognized(), 3, 2.3, now=3.5))


if __name__ == "__main__":
    unittest.main()
