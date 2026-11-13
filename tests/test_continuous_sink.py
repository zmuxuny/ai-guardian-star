"""Continuous sampler must keep encoded frame count in step with the wall clock."""

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from guardian_continuous import ContinuousCaptureSink, MAX_CATCH_UP_FRAMES


class FakeManager:
    def __init__(self, accept=True):
        self.calls = []
        self.accept = accept

    def submit_frame(self, frame, captured_at=None, monotonic_at=None):
        self.calls.append((captured_at, monotonic_at))
        return self.accept


class ContinuousSinkTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((48, 64, 3), dtype=np.uint8)

    def test_throttles_frames_that_arrive_too_soon(self):
        manager = FakeManager()
        sink = ContinuousCaptureSink(manager, fps=8)
        self.assertTrue(sink(self.frame, 0.0, 100.0))
        self.assertFalse(sink(self.frame, 0.01, 100.02))
        self.assertEqual(len(manager.calls), 1)

    def test_late_frames_are_duplicated_to_fill_the_gap(self):
        manager = FakeManager()
        sink = ContinuousCaptureSink(manager, fps=8)  # interval 125 ms
        self.assertTrue(sink(self.frame, 0.0, 100.0))
        # 三个间隔离散后才来了下一帧（真实采样 7.35fps 时的典型情况）
        for step in range(1, 16):
            sink(self.frame, step * 0.136, 100.0 + step * 0.136)
        frames = len(manager.calls)
        # 15 次到达跨越 2.04s，按 8fps 应为约 16 帧；多出来的是补帧
        self.assertGreaterEqual(frames, 16)
        self.assertGreater(sink.status()["duplicated_frames"], 0)
        # 关键回归：重复帧的时间戳必须严格递增，否则管理器判定时钟不连续，
        # 会把视频切成碎片段（板上实测被切成 0.25 秒一段）。
        stamps = [call[1] for call in manager.calls]
        self.assertEqual(stamps, sorted(set(stamps)))

    def test_catch_up_is_capped_after_a_long_stall(self):
        manager = FakeManager()
        sink = ContinuousCaptureSink(manager, fps=8)
        sink(self.frame, 0.0, 100.0)
        sink(self.frame, 5.0, 105.0)  # 停滞 5 秒
        self.assertEqual(len(manager.calls), 1 + MAX_CATCH_UP_FRAMES)

    def test_eight_fps_over_sixty_seconds_yields_sixty_second_file(self):
        """端到端折算：7.35fps 的真实采样经补帧后应达到 8 帧/秒的名义节奏。"""
        manager = FakeManager()
        sink = ContinuousCaptureSink(manager, fps=8)
        delivered = 0
        wall = 60.0
        # 模拟 7.35fps：每 136ms 一帧
        t = 0.0
        while t < wall:
            sink(self.frame, t, t)
            delivered += 1
            t += 1.0 / 7.35
        frames = len(manager.calls)
        self.assertAlmostEqual(frames / 8.0, wall, delta=2.0)
        self.assertGreater(frames, delivered)

    def test_over_width_frames_are_downscaled_when_cv2_is_available(self):
        try:
            import cv2  # noqa: F401
        except ImportError:
            self.skipTest("cv2 not installed")
        manager = FakeManager()
        sink = ContinuousCaptureSink(manager, fps=8, max_width=64)
        wide = np.zeros((48, 128, 3), dtype=np.uint8)
        sink(wide, 0.0, 100.0)
        self.assertEqual(len(manager.calls), 1)


if __name__ == "__main__":
    unittest.main()
