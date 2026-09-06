import unittest

from noteseek.schema import extract_tags, from_raw, normalize_tag, parse_datetime


class TestSchema(unittest.TestCase):
    def test_snake_and_camel_case_are_equivalent(self):
        snake = from_raw(
            {
                "key": "nabc",
                "name": "タイトル",
                "like_count": 12,
                "publish_at": "2026-09-01T10:00:00+09:00",
                "user": {"urlname": "u1", "follower_count": 300},
            }
        )
        camel = from_raw(
            {
                "key": "nabc",
                "name": "タイトル",
                "likeCount": 12,
                "publishAt": "2026-09-01T10:00:00+09:00",
                "user": {"urlname": "u1", "followerCount": 300},
            }
        )
        self.assertEqual(snake.like_count, camel.like_count)
        self.assertEqual(snake.creator_followers, camel.creator_followers)

    def test_missing_key_is_rejected(self):
        self.assertIsNone(from_raw({"name": "no key"}))
        self.assertIsNone(from_raw("not a dict"))

    def test_body_html_is_stripped_before_counting(self):
        article = from_raw(
            {"key": "n1", "name": "t", "body": "<p>あいう</p><br/>えお"}
        )
        self.assertNotIn("<p>", article.body_excerpt)
        self.assertIn("あいう", article.body_excerpt)

    def test_tag_normalization_handles_nesting_and_prefixes(self):
        self.assertEqual(normalize_tag("#AI"), "AI")
        self.assertEqual(normalize_tag("＃生成AI"), "生成AI")
        self.assertEqual(normalize_tag({"name": "#note"}), "note")
        tags = extract_tags(
            {"hashtags": [{"hashtag": {"name": "#AI"}}, {"name": "#AI"}, "#Python"]}
        )
        self.assertEqual(tags, ["AI", "Python"])

    def test_naive_datetime_is_treated_as_jst(self):
        parsed = parse_datetime("2026-09-01 10:00:00")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.utcoffset().total_seconds(), 9 * 3600)

    def test_paid_flag_follows_price(self):
        self.assertTrue(from_raw({"key": "n1", "name": "t", "price": 500}).is_paid)
        self.assertFalse(from_raw({"key": "n1", "name": "t", "price": 0}).is_paid)


if __name__ == "__main__":
    unittest.main()
