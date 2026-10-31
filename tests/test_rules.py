from agent.rules import Email, Rules, address_of, decide_by_rules, keyword_in, sender_matches

RULES = Rules(
    important_senders=["boss@acme.com", "@client.com"],
    alert_keywords=["deadline", "urgent"],
    ignore_senders=["@newsletter.io", "noreply@"],
    ignore_keywords=["unsubscribe", "weekly digest"],
)


def mail(sender="someone@else.com", subject="Hi", body="", **kw) -> Email:
    return Email(id="m1", sender=sender, subject=subject, body=body, **kw)


def test_address_of_strips_display_name():
    assert address_of("Jane Doe <Jane@Acme.com>") == "jane@acme.com"
    assert address_of("jane@acme.com") == "jane@acme.com"


def test_sender_matches_full_domain_and_prefix():
    assert sender_matches(RULES.important_senders, "Boss <boss@acme.com>") == "boss@acme.com"
    assert sender_matches(RULES.important_senders, "Someone <x@client.com>") == "@client.com"
    assert sender_matches(RULES.ignore_senders, "noreply@github.com") == "noreply@"
    assert sender_matches(RULES.important_senders, "x@notclient.com") is None


def test_keyword_search_is_case_insensitive_over_subject_and_body():
    assert keyword_in(["deadline"], "Re: DEADLINE tomorrow", "") == "deadline"
    assert keyword_in(["deadline"], "Hello", "the deadline moved") == "deadline"
    assert keyword_in(["deadline"], "Hello", "nothing here") is None


def test_important_sender_with_keyword_is_an_alert_by_rule():
    d = decide_by_rules(mail(sender="boss@acme.com", subject="Project deadline"), RULES)
    assert d is not None and d.decision == "alert" and d.by == "rule"
    assert "deadline" in d.reason


def test_important_sender_without_keyword_goes_to_the_model():
    assert decide_by_rules(mail(sender="boss@acme.com", subject="Lunch?"), RULES) is None


def test_newsletter_headers_are_ignored_without_a_model_call():
    d = decide_by_rules(mail(subject="Big sale", list_unsubscribe=True), RULES)
    assert d is not None and d.decision == "ignore" and d.by == "rule"
    d = decide_by_rules(mail(subject="Big sale", precedence_bulk=True), RULES)
    assert d is not None and d.decision == "ignore"


def test_ignore_sender_wins_even_with_alert_keyword():
    d = decide_by_rules(mail(sender="news@newsletter.io", subject="deadline: 50% off"), RULES)
    assert d is not None and d.decision == "ignore"


def test_ignore_keyword_in_subject():
    d = decide_by_rules(mail(subject="Your Weekly Digest"), RULES)
    assert d is not None and d.decision == "ignore"


def test_unknown_sender_plain_subject_is_undecided_by_rules():
    assert decide_by_rules(mail(sender="new@person.com", subject="Question about the invoice"), RULES) is None
