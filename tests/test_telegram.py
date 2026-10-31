from agent.telegram import Incoming, Telegram, parse_command


def test_only_the_allowed_chat_passes():
    tg = Telegram(token="x", allowed_chat_id=111)
    assert tg.is_allowed(Incoming(update_id=1, chat_id=111, text="hello"))
    assert not tg.is_allowed(Incoming(update_id=2, chat_id=222, text="hello"))


def test_commands():
    assert parse_command("hello") == ("hello", None)
    assert parse_command("Hello!") == ("hello", None)
    assert parse_command("/start") == ("hello", None)
    assert parse_command("What is new?") == ("whats_new", None)
    assert parse_command("what's new") == ("whats_new", None)
    assert parse_command("mute 2h") == ("mute", 120)
    assert parse_command("Mute 30m") == ("mute", 30)
    assert parse_command("/mute") == ("mute", 60)
    assert parse_command("unmute") == ("unmute", None)


def test_write_requests_are_recognised_and_refused_by_the_caller():
    assert parse_command("Please delete the email from Bob")[0] == "write_request"
    assert parse_command("send a reply to Alice")[0] == "write_request"
    assert parse_command("archive everything")[0] == "write_request"


def test_unknown_text_falls_to_help():
    assert parse_command("how is the weather")[0] == "unknown"
