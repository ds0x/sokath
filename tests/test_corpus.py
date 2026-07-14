from sokath.corpus import Corpus


def test_ratify_revise_roundtrip(tmp_path):
    c = Corpus(tmp_path / "t.db")
    eid = c.ratify("enr-fb", "enrollment fell back to manual",
                   proposed_by="alpha", ratified_by=["bravo"])
    assert c.active_entries()[0].revision == 1
    rev = c.revise(eid, "device fell back to manual enrollment",
                   trigger="repair:1", ratified_by=["alpha", "bravo"])
    assert rev == 2
    assert "manual enrollment" in c.as_prompt_block()


def test_escrow_and_repair_log(tmp_path):
    c = Corpus(tmp_path / "t.db")
    c.escrow_put("m1", "alpha", "original text", "orig-txt")
    assert c.escrow_get("m1") == ("original text", "orig-txt")
    c.log_repair_event("m1", ["alpha", "bravo"],
                       {"alpha": "x", "bravo": "y"}, tokens_at_event=1234)
    assert c.repair_events()[0]["tokens_at_event"] == 1234
