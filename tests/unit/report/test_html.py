import pytest

from agentgauge.report.html import Markup, esc, join, tag, text

HOSTILE = "<script>alert(\"x\")</script> & 'quote'"


def test_esc_neutralises_markup_ampersands_and_quotes() -> None:
    out = esc(HOSTILE)
    assert "<" not in out and ">" not in out and '"' not in out and "'" not in out
    assert out == "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#x27;quote&#x27;"


def test_text_escapes_plain_strings_and_non_strings() -> None:
    assert text("a < b") == "a &lt; b"
    assert text(3.5) == "3.5"
    assert isinstance(text("x"), Markup)


def test_markup_is_not_escaped_twice() -> None:
    inner = tag("b", "<i>")
    assert text(inner) is inner
    assert tag("p", inner) == "<p><b>&lt;i&gt;</b></p>"


def test_children_are_escaped() -> None:
    assert tag("p", HOSTILE) == f"<p>{esc(HOSTILE)}</p>"
    assert tag("td", "a", Markup("<br>"), "b") == "<td>a<br>b</td>"


def test_attribute_values_cannot_break_out_of_their_quotes() -> None:
    out = tag("a", "link", title='x" onmouseover="alert(1)')
    assert out == '<a title="x&quot; onmouseover=&quot;alert(1)">link</a>'
    assert 'onmouseover="' not in out


def test_attribute_spelling_booleans_and_omissions() -> None:
    out = tag("details", "x", class_="case", open=True, hidden=False, lang=None, aria_label="L")
    assert out == '<details class="case" open aria-label="L">x</details>'
    assert tag("label", "x", for_="id") == '<label for="id">x</label>'


@pytest.mark.parametrize("name", ["", "Script", "a b", "p><script", "1p"])
def test_element_names_are_validated(name: str) -> None:
    with pytest.raises(ValueError, match="element name"):
        tag(name)


@pytest.mark.parametrize("key", ["on click", 'x"y', "a=b", "1a", "_"])
def test_attribute_names_are_validated(key: str) -> None:
    with pytest.raises(ValueError, match="attribute name"):
        tag("p", **{key: "v"})


def test_join_escapes_loose_strings_and_keeps_markup() -> None:
    assert join(["<a>", tag("i", "x")], ", ") == "&lt;a&gt;, <i>x</i>"
    assert join([]) == ""
