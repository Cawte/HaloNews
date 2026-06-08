from halo_news_bot.classifier import classify
from halo_news_bot.models import NewsItem


def test_trailer_high_score_official():
    item = NewsItem(
        title="Halo Studios reveals new Halo Combat Evolved trailer",
        url="https://example.com/halo",
        source_key="test",
        source_name="Official",
        summary="A new gameplay trailer for Halo Combat Evolved has been revealed.",
        official=True,
    )
    c = classify(item, auto_post_official=True, auto_post_min_score=80)
    assert c.news_type == "trailer"
    assert c.importance_score >= 80
    assert c.autopost_allowed is True


def test_rumor_no_autopost():
    item = NewsItem(
        title="Rumor: Halo leak reportedly mentions a remake",
        url="https://example.com/rumor",
        source_key="test",
        source_name="Blog",
        summary="Unconfirmed insider claim.",
        official=False,
    )
    c = classify(item, auto_post_official=True, auto_post_min_score=70)
    assert c.news_type == "rumor"
    assert c.autopost_allowed is False
