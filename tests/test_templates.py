from opencode_loop.templates import render_template, list_to_bullets, compose


def test_render_template_basic():
    result = render_template("Hello {{NAME}}", {"NAME": "world"})
    assert result == "Hello world"


def test_render_template_multiple():
    result = render_template("{{A}} and {{B}}", {"A": "foo", "B": "bar"})
    assert result == "foo and bar"


def test_list_to_bullets_empty():
    assert list_to_bullets([]) == "- None"


def test_list_to_bullets_items():
    result = list_to_bullets(["a", "b"])
    assert result == "- a\n- b"


def test_compose_with_prefix():
    assert compose("prefix", "body") == "prefix\n\nbody"


def test_compose_no_prefix():
    assert compose("", "body") == "body"
