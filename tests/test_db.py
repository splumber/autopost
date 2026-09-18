from autopost.db.repo import Database


def test_topic_dedupe_and_lifecycle(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    assert db.topic_exists("hash1") is False
    topic_id = db.insert_topic("finance_education", "Why saving early matters", "hash1")
    assert db.topic_exists("hash1") is True

    topic = db.next_proposed_topic()
    assert topic["id"] == topic_id

    db.set_topic_status(topic_id, "used")
    assert db.next_proposed_topic() is None


def test_content_item_lifecycle(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    topic_id = db.insert_topic("finance_education", "Topic", "h1")
    script_id = db.insert_script(topic_id, "hook", "body", "cta", [{"text": "a", "keyword": "b"}], 60.0)
    item_id = db.insert_content_item(script_id, status="approved")

    assert db.list_content_items(status="approved")[0]["id"] == item_id

    db.update_content_item(item_id, status="ready_to_post", video_path="/tmp/v.mp4", duration_sec=61.0)
    item = db.get_content_item(item_id)
    assert item["status"] == "ready_to_post"
    assert item["duration_sec"] == 61.0


def test_rate_limit_and_posting_history(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.record_rate_limit_event("post/publish/video/init")
    assert db.count_calls_since("2000-01-01T00:00:00+00:00") == 1

    topic_id = db.insert_topic("finance_education", "T", "h2")
    script_id = db.insert_script(topic_id, "hook", "body", "cta", [], 60.0)
    item_id = db.insert_content_item(script_id)
    db.insert_posting_history(item_id, "vid123", "pub123", "SELF_ONLY", {"ok": True})
    assert db.count_posts_since("2000-01-01T00:00:00+00:00") == 1
