from halo_news_bot.classifier import classify
from halo_news_bot.generator import generate_posts
from halo_news_bot.models import NewsItem


def test_template_generation_contains_source_and_hashtags():
    item = NewsItem(
        title="Halo Infinite Operation update is live",
        url="https://example.com/source",
        source_key="steam",
        source_name="Steam News: Halo Infinite",
        summary="The latest operation adds playlists and balance changes.",
        official=True,
    )
    c = classify(item, auto_post_official=True, auto_post_min_score=82)
    posts = generate_posts(item, c, provider="template")
    assert "Source:" in posts.en_post
    assert "#Halo" in posts.en_post
    assert "RU admin version" in posts.ru_admin_post
