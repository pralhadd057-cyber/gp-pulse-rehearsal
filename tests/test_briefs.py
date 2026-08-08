import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gp_pulse.briefs import LLMBriefGenerator, TemplateBriefGenerator, get_generator
from gp_pulse.config import BriefConfig
from gp_pulse.models import DriftResult


def _sample_drift():
    return DriftResult(
        gp_id="abc123", gp_name="Dr. Test Person", clinic="Test Clinic", city="Sydney",
        monthly_series={"Jan": 40, "Feb": 39}, baseline_avg=40.0, recent_avg=18.0,
        drift_pct=55.0, flagged=True, severity="high",
    )


class TestTemplateBriefGenerator(unittest.TestCase):
    def test_generates_expected_fields(self):
        gen = TemplateBriefGenerator()
        brief = gen.generate(_sample_drift(), {"cause_code": "competitor_opened", "cause_detail": "X opened nearby."})
        self.assertEqual(brief.gp_name, "Dr. Test Person")
        self.assertEqual(brief.generated_by, "template")
        self.assertIn("55.0%", brief.brief_text)
        self.assertIn("X opened nearby.", brief.brief_text)
        self.assertEqual(len(brief.talking_points), 3)

    def test_unknown_cause_falls_back_gracefully(self):
        gen = TemplateBriefGenerator()
        brief = gen.generate(_sample_drift(), None)
        self.assertEqual(brief.cause_code, "unknown")
        self.assertIn("no confirmed external cause", brief.brief_text)


class TestLLMBriefGenerator(unittest.TestCase):
    def test_falls_back_to_template_when_no_api_key(self):
        cfg = BriefConfig(mode="llm", api_key="")
        gen = LLMBriefGenerator(cfg)
        brief = gen.generate(_sample_drift(), {"cause_code": "staff_turnover", "cause_detail": "Y left."})
        self.assertEqual(brief.generated_by, "template")  # fell back, didn't crash

    def test_falls_back_when_endpoint_unreachable(self):
        cfg = BriefConfig(mode="llm", api_key="fake-key", api_base="http://127.0.0.1:1", timeout_seconds=2)
        gen = LLMBriefGenerator(cfg)
        brief = gen.generate(_sample_drift(), {"cause_code": "unknown", "cause_detail": "n/a"})
        self.assertTrue(brief.brief_text)  # never raises, always returns something demo-able


class TestFactory(unittest.TestCase):
    def test_get_generator_template_mode(self):
        gen = get_generator(BriefConfig(mode="template"))
        self.assertIsInstance(gen, TemplateBriefGenerator)

    def test_get_generator_llm_mode(self):
        gen = get_generator(BriefConfig(mode="llm"))
        self.assertIsInstance(gen, LLMBriefGenerator)


if __name__ == "__main__":
    unittest.main()
