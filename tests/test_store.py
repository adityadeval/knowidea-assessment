from agent.store import MAX_ATTEMPTS, Store


def test_alert_once_survives_a_restart(tmp_path):
    db = tmp_path / "state.db"
    s1 = Store(db)
    assert not s1.is_handled("e1")
    s1.record_decision("e1", "alert", "why", "rule", "a@b.com", "subj", alerted=True)
    assert s1.is_handled("e1")
    s1.close()
    s2 = Store(db)                       # the "restart"
    assert s2.is_handled("e1")
    assert [a.email_id for a in s2.alerts_since(24)] == ["e1"]


def test_undecided_is_retried_then_given_up(tmp_path):
    s = Store(tmp_path / "state.db")
    for _ in range(MAX_ATTEMPTS - 1):
        s.record_decision("e2", "undecided", "no verdict", "none", "a@b.com", "s", alerted=False)
        assert not s.is_handled("e2")
    s.record_decision("e2", "undecided", "no verdict", "none", "a@b.com", "s", alerted=False)
    assert s.is_handled("e2")
    assert s.alerts_since(24) == []


def test_whats_new_lists_only_sent_alerts(tmp_path):
    s = Store(tmp_path / "state.db")
    s.record_decision("a", "alert", "r", "model", "x@y.com", "one", alerted=True)
    s.record_decision("b", "ignore", "r", "rule", "x@y.com", "two", alerted=False)
    s.record_decision("c", "alert", "muted", "rule", "x@y.com", "three", alerted=False)
    assert [a.email_id for a in s.alerts_since(24)] == ["a"]


def test_check_runs_and_meta(tmp_path):
    s = Store(tmp_path / "state.db")
    assert s.get_meta("last_check_at") is None
    s.record_check(new_count=2, alert_count=1)
    assert s.get_meta("last_check_at") is not None
    s.set_meta("mute_until", "2030-01-01T00:00:00+00:00")
    assert s.get_meta("mute_until") == "2030-01-01T00:00:00+00:00"
