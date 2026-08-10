from pathlib import Path

from scripts.ops.sync_wechat_articles import Source, _article_path, _load_sources, _safe_name, _source_for_article


def test_safe_name_removes_path_characters():
    assert _safe_name('AMD/Intel: "Q2"?') == "AMD Intel Q2"


def test_source_matching_prefers_fakeid():
    sources = [Source("半导体观察", "fake-1", "AMD.US", "AMD")]
    article = {"fakeid": "fake-1", "nickname": "renamed"}
    assert _source_for_article(sources, article) == sources[0]


def test_article_path_contains_real_publish_date():
    source = Source("半导体观察", "fake-1", "AMD.US", "AMD")
    article = {"id": 7, "title": "MI450/Helios", "publish_time": 1785254400}
    path = _article_path(source, article)
    assert path.name.startswith("20260729-MI450 Helios-7")
    assert str(path.parent).endswith("data/inputs/news/AMD/wechat")


def test_disabled_template_source_is_ignored(tmp_path):
    config = tmp_path / "wechat.json"
    config.write_text(
        '[{"nickname":"示例","fakeid":"","ticker":"AMD.US","folder":"AMD","enabled":false}]',
        encoding="utf-8",
    )
    assert _load_sources(config) == []
