from django.test import TestCase


class ExtractionQualityTests(TestCase):
    """023/3.3: seniority unknown→infer from experience; mapping mirrors prompt."""

    def test_years_to_seniority_mapping(self):
        from apps.jobs.services.llm_jd_extractor import _years_to_seniority
        self.assertEqual([_years_to_seniority(y) for y in (0, 1, 3, 6, 10, 15)],
                         [0, 1, 2, 3, 4, 5])
