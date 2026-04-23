import os
from unittest.mock import patch

from django.test import SimpleTestCase

from app.trend_pipeline import latest_feed


class LatestFeedTests(SimpleTestCase):
    @patch.dict(os.environ, {"TREND_LATEST_REMOTE_ENABLED": "false"}, clear=False)
    def test_runpod_latest_can_be_disabled_for_local_chroma_mode(self):
        self.assertFalse(latest_feed._runpod_latest_enabled())

    def test_pick_display_title_prefers_article_title_for_section_headings(self):
        picked = latest_feed._pick_display_title(
            {
                "display_title": "9. Floral Curls",
                "article_title": "Tres Chic! Halle Berry's French Bob Is Perfect for Spring",
            }
        )

        self.assertEqual(picked, "Tres Chic! Halle Berry's French Bob Is Perfect for Spring")

    def test_pick_display_title_prefers_article_title_for_question_like_headings(self):
        picked = latest_feed._pick_display_title(
            {
                "display_title": "Why Legislation is the New Must Have",
                "article_title": "The Big Chop Is Back for Spring",
            }
        )

        self.assertEqual(picked, "The Big Chop Is Back for Spring")

    def test_normalize_item_drops_titles_without_hairstyle_signal(self):
        normalized = latest_feed._normalize_item(
            {
                "display_title": "Why Legislation is the New Must Have",
                "article_title": "Angel Reese Atlanta Dream: The Blockbuster Trade Shaking Up the WNBA",
                "summary": "A broad trend summary with no hairstyle headline signal.",
                "article_url": "https://example.com/big-chop",
                "source": "Example",
            }
        )

        self.assertIsNone(normalized)

    def test_normalize_item_uses_publication_name_from_article_url(self):
        normalized = latest_feed._normalize_item(
            {
                "display_title": "Brunette Layers for Spring",
                "summary": "A layered brunette trend for spring.",
                "article_url": "https://www.harpersbazaar.com/beauty/hair/a70857655/brunette-hair-trends-spring/",
                "source": "Glamour",
                "published_at": "2026-03-26T18:27:07+00:00",
            }
        )

        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["source"], "Glamour")
        self.assertEqual(normalized["source_name"], "Harper's Bazaar")

    @patch("app.trend_pipeline.latest_feed._load_translation_cache")
    def test_attach_korean_fields_skips_cache_when_items_are_already_localized(self, mock_load_translation_cache):
        items = [
            {
                "title": "Soft Bob",
                "summary": "A soft bob trend.",
                "title_ko": "소프트 보브",
                "summary_ko": "부드러운 보브 스타일입니다.",
            }
        ]

        localized = latest_feed._attach_korean_fields(items)

        self.assertEqual(localized, items)
        mock_load_translation_cache.assert_not_called()

    @patch("app.trend_pipeline.latest_feed._translate_missing_items", side_effect=lambda items, cache: cache)
    @patch("app.trend_pipeline.latest_feed._load_translation_cache")
    def test_attach_korean_fields_replaces_english_fallback_with_cached_translation(
        self,
        mock_load_translation_cache,
        _mock_translate_missing_items,
    ):
        article_url = "https://www.elle.com/beauty/hair/a70520530/japanese-bob-styling-tips/"
        mock_load_translation_cache.return_value = {
            article_url: {
                "title_ko": "프렌치 보브는 잊어라. 재패니즈 보브가 대세다",
                "summary_ko": "재패니즈 보브는 날렵하고 조형적인 턱선 길이 커트로, 깔끔한 라인과 얼굴을 감싸는 은은한 안쪽 컬이 특징이다.",
            }
        }
        items = [
            {
                "title": "Forget the French Bob. The Japanese Bob Is Taking Over",
                "summary": "The Japanese bob is a sharp, sculpted chin-skimming cut.",
                "article_url": article_url,
                "title_ko": "Forget the French Bob. The Japanese Bob Is Taking Over",
                "summary_ko": "The Japanese bob is a sharp, sculpted chin-skimming cut.",
            }
        ]

        localized = latest_feed._attach_korean_fields(items)

        self.assertEqual(localized[0]["title_ko"], "프렌치 보브는 잊어라. 재패니즈 보브가 대세다")
        self.assertEqual(
            localized[0]["summary_ko"],
            "재패니즈 보브는 날렵하고 조형적인 턱선 길이 커트로, 깔끔한 라인과 얼굴을 감싸는 은은한 안쪽 컬이 특징이다.",
        )
        mock_load_translation_cache.assert_called_once()

    @patch("app.trend_pipeline.latest_feed._translate_missing_items", side_effect=lambda items, cache: cache)
    @patch("app.trend_pipeline.latest_feed._load_translation_cache")
    def test_attach_korean_fields_replaces_question_mark_corruption_with_cached_translation(
        self,
        mock_load_translation_cache,
        _mock_translate_missing_items,
    ):
        article_url = "https://www.elle.com/beauty/hair/a70520530/japanese-bob-styling-tips/"
        mock_load_translation_cache.return_value = {
            article_url: {
                "title_ko": "프렌치 보브는 잊어라. 재패니즈 보브가 대세다",
                "summary_ko": "재패니즈 보브는 날렵하고 조형적인 턱선 길이 커트로, 깔끔한 라인과 얼굴을 감싸는 은은한 안쪽 컬이 특징이다.",
            }
        }
        items = [
            {
                "title": "Forget the French Bob. The Japanese Bob Is Taking Over",
                "summary": "The Japanese bob is a sharp, sculpted chin-skimming cut.",
                "article_url": article_url,
                "title_ko": "??? ??? ???. ???? ??? ???",
                "summary_ko": "???? ??? ???? ???? ?? ?? ???.",
            }
        ]

        localized = latest_feed._attach_korean_fields(items)

        self.assertEqual(localized[0]["title_ko"], "프렌치 보브는 잊어라. 재패니즈 보브가 대세다")
        self.assertEqual(
            localized[0]["summary_ko"],
            "재패니즈 보브는 날렵하고 조형적인 턱선 길이 커트로, 깔끔한 라인과 얼굴을 감싸는 은은한 안쪽 컬이 특징이다.",
        )
        mock_load_translation_cache.assert_called_once()

    @patch("app.trend_pipeline.latest_feed._load_translation_cache")
    def test_apply_translation_cache_overrides_replaces_stale_localized_fields(self, mock_load_translation_cache):
        mock_load_translation_cache.return_value = {
            "https://example.com/katseye": {
                "title_ko": "캣츠아이, 코첼라를 위한 파격 금발 변신!",
                "summary_ko": "캣츠아이는 코첼라 무대를 앞두고 블론드 변신을 선보였습니다.",
            }
        }
        items = [
            {
                "title": "Katseye on Going Blonde for Coachella",
                "summary": "Katseye went blonde for Coachella.",
                "article_url": "https://example.com/katseye",
                "title_ko": "오래된 제목",
                "summary_ko": "오래된 요약",
            }
        ]

        localized = latest_feed._apply_translation_cache_overrides(items)

        self.assertEqual(localized[0]["title_ko"], "캣츠아이, 코첼라를 위한 파격 금발 변신!")
        self.assertEqual(localized[0]["summary_ko"], "캣츠아이는 코첼라 무대를 앞두고 블론드 변신을 선보였습니다.")

    @patch("app.trend_pipeline.latest_feed._set_latest_trends_cached", side_effect=lambda limit, payload: payload)
    @patch("app.trend_pipeline.latest_feed._get_latest_trends_cached", return_value=None)
    @patch("app.trend_pipeline.latest_feed._load_refined_article_lookup", return_value={})
    @patch("app.trend_pipeline.latest_feed._iter_chroma_items")
    @patch("app.trend_pipeline.latest_feed._load_translation_cache")
    def test_latest_crawled_trends_uses_chroma_localized_metadata(
        self,
        mock_load_translation_cache,
        mock_iter_chroma_items,
        _mock_refined_lookup,
        _mock_get_cached,
        _mock_set_cached,
    ):
        mock_load_translation_cache.return_value = {}
        mock_iter_chroma_items.return_value = [
            {
                "display_title": "Soft Bob",
                "summary": "A soft bob trend with airy texture.",
                "article_url": "https://example.com/soft-bob",
                "image_url": "https://images.example.com/soft-bob.jpg",
                "source": "Example",
                "published_at": "2026-04-01T00:00:00+00:00",
                "category": "style_trend",
                "title_ko": "소프트 보브",
                "summary_ko": "가벼운 질감이 들어간 소프트 보브 스타일입니다.",
                "style_tags": "bob",
                "color_tags": "",
            }
        ]

        payload = latest_feed.get_latest_crawled_trends(limit=5)

        self.assertEqual(payload["source"], "chromadb_trends")
        self.assertEqual(payload["items"][0]["source_name"], "Example")
        self.assertEqual(payload["items"][0]["title_ko"], "소프트 보브")
        self.assertEqual(payload["items"][0]["summary_ko"], "가벼운 질감이 들어간 소프트 보브 스타일입니다.")
        mock_load_translation_cache.assert_called_once()

    @patch("app.trend_pipeline.latest_feed._set_latest_trends_cached", side_effect=lambda limit, payload: payload)
    @patch("app.trend_pipeline.latest_feed._get_latest_trends_cached", return_value=None)
    @patch("app.trend_pipeline.latest_feed._attach_korean_fields", side_effect=lambda items: items)
    @patch("app.trend_pipeline.latest_feed._load_refined_article_lookup")
    @patch("app.trend_pipeline.latest_feed._iter_chroma_items")
    def test_latest_crawled_trends_prefers_refined_article_metadata_for_deduped_chroma_items(
        self,
        mock_iter_chroma_items,
        mock_refined_lookup,
        _mock_attach_korean_fields,
        _mock_get_cached,
        _mock_set_cached,
    ):
        article_url = "https://www.marieclaire.com/beauty/hair/zendaya-hydro-bob-euphoria-season-three-premiere/"
        canonical_title = "Zendaya Brings the Sultry Wet and Wavy Look to the 'Euphoria' Red Carpet"
        mock_iter_chroma_items.return_value = [
            {
                "display_title": "Gabrielle Union Is Keeping the C*nty Little Bob Alive",
                "summary": "Gabrielle bob summary",
                "article_title": canonical_title,
                "article_url": article_url,
                "image_url": "https://images.example.com/zendaya-bob.jpg",
                "source": "Marieclaire",
                "published_at": "2026-04-08T18:30:56+00:00",
                "category": "celebrity_example",
                "style_tags": "bob",
                "color_tags": "",
            }
        ]
        mock_refined_lookup.return_value = {
            article_url: {
                "trend_name": canonical_title,
                "description": "Zendaya bob summary",
                "article_title": canonical_title,
                "article_url": article_url,
                "image_url": "https://images.example.com/zendaya-bob.jpg",
                "source": "Marieclaire",
                "published_at": "2026-04-08T18:30:56+00:00",
                "category": "celebrity_example",
                "hairstyle_text": "bob",
                "color_text": "",
            }
        }

        payload = latest_feed.get_latest_crawled_trends(limit=5)

        self.assertEqual(payload["items"][0]["title"], canonical_title)
        self.assertEqual(payload["items"][0]["summary"], "Zendaya bob summary")
        self.assertEqual(payload["items"][0]["source_name"], "Marie Claire")

    @patch("app.trend_pipeline.latest_feed._set_latest_trends_cached", side_effect=lambda limit, payload: payload)
    @patch("app.trend_pipeline.latest_feed._get_latest_trends_cached", return_value=None)
    @patch("app.trend_pipeline.latest_feed._attach_korean_fields", side_effect=lambda items: items)
    @patch("app.trend_pipeline.latest_feed._load_refined_article_lookup", return_value={})
    @patch("app.trend_pipeline.latest_feed._load_json_list")
    @patch("app.trend_pipeline.latest_feed._iter_chroma_items")
    def test_latest_crawled_trends_falls_back_to_refined_when_chroma_normalizes_to_empty(
        self,
        mock_iter_chroma_items,
        mock_load_json_list,
        _mock_refined_lookup,
        _mock_attach_korean_fields,
        _mock_get_cached,
        _mock_set_cached,
    ):
        mock_iter_chroma_items.return_value = [
            {
                "display_title": "Generic headline",
                "summary": "No hairstyle signal here.",
                "article_url": "https://example.com/not-hair",
                "source": "Example",
                "published_at": "2026-04-01T00:00:00+00:00",
                "category": "trend",
            }
        ]
        mock_load_json_list.return_value = [
            {
                "trend_name": "Soft Bob",
                "description": "A soft bob trend with airy layers.",
                "article_title": "Soft Bob",
                "article_url": "https://example.com/soft-bob",
                "image_url": "https://images.example.com/soft-bob.jpg",
                "source": "Example",
                "published_at": "2026-04-02T00:00:00+00:00",
                "crawled_at": "2026-04-02T01:00:00+00:00",
                "hairstyle_text": "bob",
                "color_text": "",
            }
        ]

        payload = latest_feed.get_latest_crawled_trends(limit=5)

        self.assertEqual(payload["source"], "refined_trends_json")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["title"], "Soft Bob")

    @patch("app.trend_pipeline.latest_feed._set_latest_trends_cached", side_effect=lambda limit, payload: payload)
    @patch("app.trend_pipeline.latest_feed._get_latest_trends_cached", return_value=None)
    @patch("app.trend_pipeline.latest_feed._attach_korean_fields", side_effect=lambda items: items)
    @patch("app.trend_pipeline.latest_feed._load_refined_article_lookup", return_value={})
    @patch("app.trend_pipeline.latest_feed._iter_chroma_items")
    def test_latest_crawled_trends_skips_items_without_image_url(
        self,
        mock_iter_chroma_items,
        _mock_refined_lookup,
        _mock_attach_korean_fields,
        _mock_get_cached,
        _mock_set_cached,
    ):
        mock_iter_chroma_items.return_value = [
            {
                "display_title": "Soft Bob",
                "summary": "A soft bob trend with airy layers.",
                "article_url": "https://example.com/soft-bob",
                "image_url": "",
                "source": "Example",
                "published_at": "2026-04-02T00:00:00+00:00",
                "category": "style_trend",
                "style_tags": "bob",
                "color_tags": "",
            },
            {
                "display_title": "Golden Hour Brunette",
                "summary": "A brunette gloss trend with soft movement.",
                "article_url": "https://example.com/golden-hour-brunette",
                "image_url": "https://images.example.com/golden-hour.jpg",
                "source": "Example",
                "published_at": "2026-04-03T00:00:00+00:00",
                "category": "style_trend",
                "style_tags": "brunette",
                "color_tags": "",
            },
        ]

        payload = latest_feed.get_latest_crawled_trends(limit=5)

        self.assertEqual(payload["source"], "chromadb_trends")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["title"], "Golden Hour Brunette")
        self.assertEqual(payload["items"][0]["image_url"], "https://images.example.com/golden-hour.jpg")

    @patch("app.trend_pipeline.latest_feed._set_latest_trends_cached", side_effect=lambda limit, payload: payload)
    @patch("app.trend_pipeline.latest_feed._get_latest_trends_cached", return_value=None)
    @patch("app.trend_pipeline.latest_feed._attach_korean_fields", side_effect=lambda items: items)
    @patch("app.trend_pipeline.latest_feed._load_refined_article_lookup", return_value={})
    @patch("app.trend_pipeline.latest_feed._load_json_list")
    @patch("app.trend_pipeline.latest_feed._iter_chroma_items")
    def test_latest_crawled_trends_falls_back_when_chroma_items_have_no_images(
        self,
        mock_iter_chroma_items,
        mock_load_json_list,
        _mock_refined_lookup,
        _mock_attach_korean_fields,
        _mock_get_cached,
        _mock_set_cached,
    ):
        mock_iter_chroma_items.return_value = [
            {
                "display_title": "Soft Bob",
                "summary": "A soft bob trend with airy layers.",
                "article_url": "https://example.com/soft-bob",
                "image_url": "",
                "source": "Example",
                "published_at": "2026-04-02T00:00:00+00:00",
                "category": "style_trend",
                "style_tags": "bob",
                "color_tags": "",
            }
        ]
        mock_load_json_list.return_value = [
            {
                "trend_name": "Golden Hour Brunette",
                "description": "A brunette gloss trend with soft movement.",
                "article_title": "Golden Hour Brunette",
                "article_url": "https://example.com/golden-hour-brunette",
                "image_url": "https://images.example.com/golden-hour.jpg",
                "source": "Example",
                "published_at": "2026-04-03T00:00:00+00:00",
                "crawled_at": "2026-04-03T01:00:00+00:00",
                "hairstyle_text": "brunette",
                "color_text": "",
            }
        ]

        payload = latest_feed.get_latest_crawled_trends(limit=5)

        self.assertEqual(payload["source"], "refined_trends_json")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["title"], "Golden Hour Brunette")
        self.assertEqual(payload["items"][0]["image_url"], "https://images.example.com/golden-hour.jpg")
