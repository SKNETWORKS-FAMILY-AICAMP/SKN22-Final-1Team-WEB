from django.test import SimpleTestCase
from unittest.mock import patch

from app.trend_pipeline import vectorize_chromadb


class VectorizeChromaMetadataTests(SimpleTestCase):
    @patch("app.trend_pipeline.vectorize_chromadb._load_article_metadata_candidates", return_value=[])
    @patch("app.trend_pipeline.vectorize_chromadb._load_refined_metadata_lookup")
    def test_merge_refined_metadata_prefers_direct_lookup(self, mock_lookup, _mock_article_candidates):
        mock_lookup.return_value = {
            "soft-bob": {
                "article_title": "Soft Bob Guide",
                "article_url": "https://example.com/soft-bob",
                "image_url": "https://example.com/soft-bob.jpg",
                "published_at": "2026-03-01T00:00:00+00:00",
                "crawled_at": "2026-03-02T00:00:00+00:00",
                "source": "Example",
                "year": "2026",
            }
        }

        merged = vectorize_chromadb._merge_refined_metadata(
            [
                {
                    "display_title": "Soft Bob",
                    "canonical_name": "soft bob",
                    "summary": "A soft bob trend.",
                    "search_text": "soft bob trend",
                    "style_tags": ["bob"],
                    "color_tags": [],
                    "source": "Example",
                    "year": "2026",
                    "article_title": "",
                    "article_url": "",
                    "image_url": "",
                    "published_at": "",
                    "crawled_at": "",
                }
            ]
        )

        self.assertEqual(merged[0]["article_url"], "https://example.com/soft-bob")
        self.assertEqual(merged[0]["article_title"], "Soft Bob Guide")
        self.assertEqual(merged[0]["published_at"], "2026-03-01T00:00:00+00:00")

    @patch("app.trend_pipeline.vectorize_chromadb._load_refined_metadata_lookup", return_value={})
    @patch("app.trend_pipeline.vectorize_chromadb._load_article_metadata_candidates")
    def test_merge_refined_metadata_uses_same_source_article_candidate(self, mock_article_candidates, _mock_lookup):
        mock_article_candidates.return_value = [
            {
                "article_title": "Forget the French Bob. The Japanese Bob Is Taking Over",
                "article_url": "https://example.com/japanese-bob",
                "image_url": "https://example.com/japanese-bob.jpg",
                "published_at": "2026-02-26T22:49:51+00:00",
                "crawled_at": "2026-04-07T00:46:17+00:00",
                "source": "Elle",
                "source_key": vectorize_chromadb._source_key("Elle"),
                "year": "2026",
                "row_count": 2,
                "row_token_sets": [{"french", "bob", "japanese", "fringe"}, {"french", "bob", "style"}],
                "article_tokens": {"french", "bob", "japanese", "fringe", "style"},
            },
            {
                "article_title": "Unrelated Allure Story",
                "article_url": "https://example.com/allure-story",
                "image_url": "https://example.com/allure-story.jpg",
                "published_at": "2026-03-10T00:00:00+00:00",
                "crawled_at": "2026-04-07T00:46:17+00:00",
                "source": "Allure",
                "source_key": vectorize_chromadb._source_key("Allure"),
                "year": "2026",
                "row_count": 1,
                "row_token_sets": [{"pixie", "ombre"}],
                "article_tokens": {"pixie", "ombre"},
            },
        ]

        merged = vectorize_chromadb._merge_refined_metadata(
            [
                {
                    "display_title": "French Bob",
                    "canonical_name": "french bob",
                    "summary": "French bob with soft fringe.",
                    "search_text": "french bob soft fringe style",
                    "style_tags": ["bob", "fringe"],
                    "color_tags": [],
                    "source": "Elle",
                    "year": "2026",
                    "article_title": "",
                    "article_url": "",
                    "image_url": "",
                    "published_at": "",
                    "crawled_at": "",
                }
            ]
        )

        self.assertEqual(merged[0]["article_url"], "https://example.com/japanese-bob")
        self.assertEqual(merged[0]["source"], "Elle")

    @patch("app.trend_pipeline.vectorize_chromadb._load_refined_metadata_lookup", return_value={})
    @patch("app.trend_pipeline.vectorize_chromadb._load_article_metadata_candidates")
    def test_merge_refined_metadata_does_not_cross_source_match_when_source_exists(self, mock_article_candidates, _mock_lookup):
        mock_article_candidates.return_value = [
            {
                "article_title": "Only Elle Candidate",
                "article_url": "https://example.com/elle-story",
                "image_url": "https://example.com/elle-story.jpg",
                "published_at": "2026-02-26T22:49:51+00:00",
                "crawled_at": "2026-04-07T00:46:17+00:00",
                "source": "Elle",
                "source_key": vectorize_chromadb._source_key("Elle"),
                "year": "2026",
                "row_count": 1,
                "row_token_sets": [{"pixie", "cut", "celebrity"}],
                "article_tokens": {"pixie", "cut", "celebrity"},
            }
        ]

        merged = vectorize_chromadb._merge_refined_metadata(
            [
                {
                    "display_title": "Pixie Cut",
                    "canonical_name": "pixie cut",
                    "summary": "Celebrity pixie cut.",
                    "search_text": "pixie cut celebrity style",
                    "style_tags": ["pixie"],
                    "color_tags": [],
                    "source": "Allure",
                    "year": "2026",
                    "article_title": "",
                    "article_url": "",
                    "image_url": "",
                    "published_at": "",
                    "crawled_at": "",
                }
            ]
        )

        self.assertEqual(merged[0]["article_url"], "")
