from agent.decide import MAX_BODY_CHARS, build_prompt, parse_verdict
from agent.rules import Email, Rules


def test_parse_accepts_the_contract():
    d = parse_verdict('{"needs_attention": true, "reason": "Your client asks for a reply by Friday."}')
    assert d is not None and d.decision == "alert" and d.by == "model"
    d = parse_verdict('{"needs_attention": false, "reason": "A promotion."}')
    assert d is not None and d.decision == "ignore"


def test_parse_tolerates_text_around_the_object():
    d = parse_verdict('Sure: {"needs_attention": false, "reason": "Marketing."} done')
    assert d is not None and d.decision == "ignore"


def test_parse_fails_closed_on_anything_else():
    assert parse_verdict("") is None
    assert parse_verdict("ALERT") is None
    assert parse_verdict('{"needs_attention": "yes", "reason": "x"}') is None       # wrong type
    assert parse_verdict('{"needs_attention": true}') is None                       # missing reason
    assert parse_verdict('{"needs_attention": true, "reason": ""}') is None         # empty reason
    assert parse_verdict('[true, "x"]') is None                                     # not an object
    assert parse_verdict('{"needs_attention": true, "reason": "x"') is None         # broken JSON


def test_reason_is_one_line_and_bounded():
    d = parse_verdict('{"needs_attention": true, "reason": "line one\\nline two   spaced"}')
    assert d is not None and "\n" not in d.reason and "  " not in d.reason
    long = "{\"needs_attention\": true, \"reason\": \"" + "w" * 500 + "\"}"
    d = parse_verdict(long)
    assert d is not None and len(d.reason) <= 200


def test_prompt_bounds_the_body_and_wraps_it_as_data():
    email = Email(id="1", sender="a@b.com", subject="s", body="x" * (MAX_BODY_CHARS + 500))
    p = build_prompt(email, Rules())
    assert "[truncated]" in p and "<email>" in p and "</email>" in p
    assert "Bulk-mail headers present: no" in p
    hinted = build_prompt(Email(id="2", sender="a@b.com", subject="s", body="", list_unsubscribe=True), Rules())
    assert "Bulk-mail headers present: yes" in hinted
    assert len(p) < MAX_BODY_CHARS + 1000
