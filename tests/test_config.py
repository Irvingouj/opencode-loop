from opencode_loop.config import dedupe_keep_order


def test_dedupe_keep_order():
    assert dedupe_keep_order(["a", "b", "a", "c"]) == ["a", "b", "c"]


def test_dedupe_empty():
    assert dedupe_keep_order([]) == []
