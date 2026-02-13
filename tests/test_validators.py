import unittest

from codex_search_stack.validators import (
    DEFAULT_ANTI_BOT_DOMAINS,
    coerce_int,
    extract_anti_bot_domains,
    is_high_risk_host,
    split_domain_boost,
    validate_explore_protocol,
    validate_extract_protocol,
    validate_search_protocol,
)


class ValidatorTests(unittest.TestCase):
    def test_coerce_int(self) -> None:
        self.assertEqual(coerce_int("7", 1), 7)
        self.assertEqual(coerce_int("bad", 9), 9)

    def test_split_domain_boost(self) -> None:
        self.assertEqual(split_domain_boost("OpenAI.com, github.com ,,"), ["openai.com", "github.com"])
        self.assertEqual(split_domain_boost(""), [])

    def test_validate_search_protocol_invalid_domain(self) -> None:
        err, detail = validate_search_protocol(
            queries=["q"],
            intent="exploratory",
            freshness="",
            num=5,
            domains=["openai.com", "not a domain"],
            comparison_queries=1,
            comparison_error_message="comparison intent requires --queries with at least 2 items",
            time_signal_error_message="time-sensitive query requires --freshness",
        )
        self.assertEqual(err, "invalid domain_boost values")
        self.assertEqual(detail, {"invalid_domains": ["not a domain"]})

    def test_validate_search_protocol_time_signal(self) -> None:
        err, _ = validate_search_protocol(
            queries=["latest codex release"],
            intent="exploratory",
            freshness="",
            num=5,
            domains=["openai.com"],
            comparison_queries=1,
            comparison_error_message="comparison intent requires --queries with at least 2 items",
            time_signal_error_message="time-sensitive query requires --freshness",
        )
        self.assertEqual(err, "time-sensitive query requires --freshness")

    def test_validate_search_protocol_valid(self) -> None:
        err, detail = validate_search_protocol(
            queries=["codex cli guide"],
            intent="resource",
            freshness="",
            num=5,
            domains=["openai.com"],
            comparison_queries=1,
            comparison_error_message="comparison intent requires --queries with at least 2 items",
            time_signal_error_message="time-sensitive query requires --freshness",
        )
        self.assertIsNone(err)
        self.assertIsNone(detail)

    def test_validate_extract_protocol_invalid_url(self) -> None:
        err, detail = validate_extract_protocol(url="not-a-url", max_chars=3000, strategy="auto")
        self.assertEqual(err, "url must be a valid http(s) URL")
        self.assertIsNone(detail)

    def test_validate_extract_protocol_invalid_range_and_strategy(self) -> None:
        err, _ = validate_extract_protocol(url="https://example.com", max_chars=100, strategy="auto")
        self.assertEqual(err, "max_chars must be between 500 and 200000")

        err, _ = validate_extract_protocol(url="https://example.com", max_chars=3000, strategy="unknown")
        self.assertEqual(err, "strategy must be one of auto/tavily_first/mineru_first/tavily_only/mineru_only")

    def test_validate_extract_protocol_valid_and_normalized(self) -> None:
        err, detail = validate_extract_protocol(
            url="https://Sub.Example.com/path",
            max_chars="4000",
            strategy="TAVILY_FIRST",
        )
        self.assertIsNone(err)
        self.assertEqual(detail["host"], "sub.example.com")
        self.assertEqual(detail["max_chars"], 4000)
        self.assertEqual(detail["strategy"], "tavily_first")

    def test_extract_anti_bot_domains(self) -> None:
        self.assertEqual(extract_anti_bot_domains(None), DEFAULT_ANTI_BOT_DOMAINS)

        policy = {"extract": {"anti_bot_domains": ["Zhihu.com", "", " mp.weixin.qq.com "]}}
        self.assertEqual(extract_anti_bot_domains(policy), {"zhihu.com", "mp.weixin.qq.com"})

    def test_is_high_risk_host(self) -> None:
        domains = {"zhihu.com", "mp.weixin.qq.com"}
        self.assertTrue(is_high_risk_host("zhihu.com", domains))
        self.assertTrue(is_high_risk_host("zhuanlan.zhihu.com", domains))
        self.assertFalse(is_high_risk_host("example.com", domains))

    def test_validate_explore_protocol(self) -> None:
        err, _ = validate_explore_protocol(
            issues=2,
            commits=5,
            external_num=8,
            extract_top=2,
            output_format="json",
        )
        self.assertEqual(err, "issues must be between 3 and 20")

        err, detail = validate_explore_protocol(
            issues="6",
            commits="7",
            external_num="9",
            extract_top="3",
            output_format="MARKDOWN",
        )
        self.assertIsNone(err)
        self.assertEqual(
            detail,
            {
                "issues": 6,
                "commits": 7,
                "external_num": 9,
                "extract_top": 3,
                "output_format": "markdown",
            },
        )


if __name__ == "__main__":
    unittest.main()
