"""검사 이름이 곧 지켜야 할 규칙이다. 모델 호출 없이 응답 분류만으로 확인한다."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fallback as f  # noqa: E402


class OriginalFirst(unittest.TestCase):
    def test_original_frame_is_on_the_wall_right_after_upload(self):
        art = f.upload("animated")
        self.assertEqual(art.on_wall, "frame")
        self.assertIsNone(art.result)

    def test_original_frame_stays_on_the_wall_while_retrying(self):
        art = f.upload("animated")
        f.apply(art, "timeout")
        f.apply(art, "engine_down")
        self.assertEqual(art.on_wall, "frame")

    def test_new_result_replaces_frame_only_after_guardian_confirms(self):
        art = f.upload("animated")
        f.apply(art, "ok")
        self.assertEqual(art.on_wall, "frame")
        f.confirm(art, "animated")
        self.assertEqual(art.on_wall, "animated")


class QualityBelowDowngrades(unittest.TestCase):
    def test_quality_below_goes_one_step_down_without_retry(self):
        art = f.upload("animated")
        f.apply(art, "quality_below")
        self.assertEqual(art.target, "relief")
        self.assertEqual(art.attempts, 0)
        self.assertEqual(art.causes, ["model_downgrade"])

    def test_chain_ends_at_model_free_frame(self):
        art = f.upload("animated")
        f.apply(art, "quality_below")
        f.apply(art, "quality_below")
        self.assertEqual(art.result, "frame")
        self.assertEqual(art.causes.count("model_downgrade"), 2)

    def test_sculpture_falls_back_to_relief_then_frame(self):
        self.assertEqual(f.CHAIN["sculpture"], "relief")
        self.assertEqual(f.CHAIN["relief"], "frame")


class InfraErrorsRetry(unittest.TestCase):
    def test_infra_error_is_not_a_downgrade(self):
        art = f.upload("animated")
        f.apply(art, "engine_down")
        self.assertEqual(art.target, "animated")
        self.assertNotIn("model_downgrade", art.causes)

    def test_same_stage_is_tried_at_most_three_times_including_first(self):
        art = f.upload("relief")
        for r in ["timeout", "storage", "db"]:
            f.apply(art, r)
        self.assertIn("not_delivered", art.causes)
        self.assertEqual(art.attempts, 3)
        with self.assertRaises(ValueError):
            f.apply(art, "ok")

    def test_success_on_third_try_delivers_the_wanted_result(self):
        art = f.upload("animated")
        for r in ["timeout", "model_not_ready", "ok"]:
            f.apply(art, r)
        self.assertEqual(art.result, "animated")
        self.assertNotIn("not_delivered", art.causes)

    def test_unknown_response_is_rejected(self):
        with self.assertRaises(ValueError):
            f.apply(f.upload("animated"), "looks_fine")


class CausesAreNotMixed(unittest.TestCase):
    def test_guardian_choice_is_recorded_when_frame_or_relief_is_picked_first(self):
        self.assertEqual(f.upload("frame").causes, ["guardian_choice"])
        self.assertEqual(f.upload("relief").causes, ["guardian_choice"])
        self.assertEqual(f.upload("animated").causes, [])

    def test_picking_a_lower_result_at_confirm_is_a_guardian_switch(self):
        art = f.upload("animated")
        f.apply(art, "ok")
        f.confirm(art, "frame")
        self.assertIn("guardian_switch", art.causes)
        self.assertNotIn("model_downgrade", art.causes)

    def test_frame_after_exhausted_retries_stays_infra_not_switch(self):
        art = f.upload("animated")
        for r in ["timeout"] * 3:
            f.apply(art, r)
        f.confirm(art, "frame")
        self.assertEqual(art.on_wall, "frame")
        self.assertIn("infra_failure", art.causes)
        self.assertNotIn("guardian_switch", art.causes)

    def test_not_delivered_work_is_excluded_from_first_approval_rate(self):
        art = f.upload("animated")
        for r in ["timeout"] * 3:
            f.apply(art, r)
        self.assertFalse(f.counts_in_first_approval(art))
        ok = f.upload("animated")
        f.apply(ok, "ok")
        self.assertTrue(f.counts_in_first_approval(ok))


if __name__ == "__main__":
    unittest.main()


class InvalidResponseIsInfra(unittest.TestCase):
    """계약을 어긴 응답은 낮춤이 아니라 같은 단계 재시도다(결정 004)."""

    def test_invalid_then_ok_keeps_stage(self):
        art = f.upload("animated")
        f.apply(art, "invalid_response")
        self.assertEqual(art.target, "animated")
        self.assertNotIn(f.MODEL_DOWNGRADE, art.causes)
        f.apply(art, f.OK)
        self.assertEqual(art.result, "animated")
        self.assertIn(f.INFRA_FAILURE, art.causes)

    def test_three_invalid_is_not_delivered(self):
        art = f.upload("animated")
        for _ in range(f.MAX_ATTEMPTS):
            f.apply(art, "invalid_response")
        self.assertIn(f.NOT_DELIVERED, art.causes)
