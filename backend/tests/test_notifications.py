from tests.conftest import login


def test_new_tweet_notifies_tribe_members(client, seeded):
    login(client, seeded["sl_a"])  # tribe 1
    assert client.post("/api/feed", json={"content": "hello", "kind": "info"}).status_code == 201
    login(client, seeded["member"])  # tribe 1
    n = client.get("/api/notifications").json()
    assert n["unread_count"] >= 1
    assert any(i["kind"] == "tweet" for i in n["items"])
    client.post("/api/notifications/read-all")
    assert client.get("/api/notifications").json()["unread_count"] == 0


def test_reply_notifies_post_author(client, seeded):
    login(client, seeded["sl_a"])
    pid = client.post("/api/feed", json={"content": "x", "kind": "info"}).json()["id"]
    login(client, seeded["member"])
    assert client.post(f"/api/feed/{pid}/replies", json={"content": "reply"}).status_code == 201
    login(client, seeded["sl_a"])
    assert any(i["kind"] == "reply" for i in client.get("/api/notifications").json()["items"])


def test_tweet_does_not_leak_across_tribes(client, seeded):
    login(client, seeded["tribe2"])  # other tribe posts
    client.post("/api/feed", json={"content": "T2 tweet", "kind": "info"})
    login(client, seeded["member"])  # tribe 1
    items = client.get("/api/notifications").json()["items"]
    assert all("T2" not in (i.get("excerpt") or "") for i in items)


def test_preferences_mute_tweets(client, seeded):
    login(client, seeded["member"])
    assert client.put("/api/me/preferences", json={"notify_tweets": False}).json()["notify_tweets"] is False
    login(client, seeded["sl_a"])
    client.post("/api/feed", json={"content": "after mute", "kind": "info"})
    login(client, seeded["member"])
    assert client.get("/api/notifications").json()["unread_count"] == 0
