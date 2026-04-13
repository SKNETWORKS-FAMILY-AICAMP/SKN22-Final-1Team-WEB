from django.test import SimpleTestCase

from app.trend_pipeline.rag_safety import sanitize_rag_items


class RagSafetyTests(SimpleTestCase):
    def test_newsletter_title_is_rewritten_when_trend_payload_is_valid(self):
        items, report = sanitize_rag_items(
            [
                {
                    "canonical_name": "margot robbie's bob",
                    "display_title": "Get the Daily Beauty Blast Newsletter",
                    "category": "celebrity_example",
                    "style_tags": ["bob", "lob"],
                    "summary": "A textured bob with a side part and a soft celebrity silhouette.",
                    "search_text": "margot robbie bob, textured bob, side part",
                    "source": "Allure",
                }
            ]
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["display_title"], "Margot Robbie's Bob")
        self.assertEqual(report["retitled_count"], 1)
        self.assertEqual(report["dropped_count"], 0)

    def test_ad_only_item_is_dropped(self):
        items, report = sanitize_rag_items(
            [
                {
                    "display_title": "Shop Now",
                    "summary": "Sponsored content. Sign up for our newsletter and shop now.",
                    "search_text": "advertisement shop now newsletter",
                    "source": "Unknown",
                }
            ]
        )

        self.assertEqual(items, [])
        self.assertEqual(report["retitled_count"], 0)
        self.assertEqual(report["dropped_count"], 1)

    def test_single_cta_in_summary_does_not_drop_real_trend_item(self):
        items, report = sanitize_rag_items(
            [
                {
                    "canonical_name": "layered bob",
                    "display_title": "Layered Bob Trend",
                    "category": "style_trend",
                    "style_tags": ["bob"],
                    "summary": "A soft layered bob is trending this season. Subscribe for more looks.",
                    "search_text": "layered bob trend, soft movement, jaw-length shape",
                    "source": "Instyle",
                }
            ]
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["display_title"], "Layered Bob Trend")
        self.assertEqual(report["dropped_count"], 0)
