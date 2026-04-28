import unittest

from search_agent.models import WebPageContent
from search_agent.web_fetch import FetchQuality, WebFetchRouter


class StubProvider:
    def __init__(self, page):
        self.page = page
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return self.page


class WebFetchRouterTests(unittest.TestCase):
    def test_uses_jina_when_quality_is_good(self):
        jina = StubProvider(
            WebPageContent(
                title="一网通办",
                url="https://example.test",
                text="灵活就业人员社会保险费缴费。受理条件和办理流程。",
                provider="jina",
                status="ok",
            )
        )
        crawl = StubProvider(
            WebPageContent(title="fallback", url="https://example.test", text="fallback", provider="crawl4ai", status="ok")
        )
        router = WebFetchRouter(jina_provider=jina, crawl4ai_provider=crawl, quality=FetchQuality(min_chars=20))

        page = router.fetch("https://example.test", query_terms=["灵活就业", "缴费"])

        self.assertEqual(page.provider, "jina")
        self.assertEqual(crawl.calls, [])

    def test_falls_back_to_crawl4ai_when_jina_content_is_too_short(self):
        jina = StubProvider(
            WebPageContent(title="", url="https://example.test", text="", provider="jina", status="too_short")
        )
        crawl = StubProvider(
            WebPageContent(
                title="一网通办",
                url="https://example.test",
                text="灵活就业人员社会保险费缴费。受理条件和办理流程。",
                provider="crawl4ai",
                status="ok",
            )
        )
        router = WebFetchRouter(jina_provider=jina, crawl4ai_provider=crawl)

        page = router.fetch("https://example.test", query_terms=["灵活就业", "缴费"])

        self.assertEqual(page.provider, "crawl4ai")
        self.assertEqual(len(crawl.calls), 1)

    def test_pdf_is_marked_for_pdf_parser_without_browser_fetch(self):
        router = WebFetchRouter(jina_provider=StubProvider(None), crawl4ai_provider=StubProvider(None))

        page = router.fetch("https://example.test/file.pdf", query_terms=["缴费"])

        self.assertEqual(page.status, "pdf_unsupported")
        self.assertEqual(page.provider, "pdf")

    def test_quality_rejects_precondition_failed_text(self):
        quality = FetchQuality(min_chars=20)
        page = WebPageContent(
            title="",
            url="https://example.test",
            text="Warning: Target URL returned error 412: Precondition Failed",
            provider="jina",
            status="ok",
        )

        self.assertFalse(quality.is_good(page, ["灵活就业"]))


if __name__ == "__main__":
    unittest.main()
