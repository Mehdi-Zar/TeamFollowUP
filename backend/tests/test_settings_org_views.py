"""The org chart's views, in the order set by an administrator."""
from tests.conftest import login


def test_the_tree_opens_first_by_default(client, seeded):
    assert client.get("/api/config").json()["org_views"] == ["tree", "list"]


def test_an_admin_puts_the_list_first(client, seeded):
    login(client, seeded["admin"])
    out = client.put("/api/admin/settings", json={"org_views": ["list", "tree"]}).json()
    assert out["org_views"] == ["list", "tree"]
    assert client.get("/api/config").json()["org_views"] == ["list", "tree"]


def test_a_view_is_reordered_never_lost(client, seeded):
    login(client, seeded["admin"])
    assert client.put("/api/admin/settings", json={"org_views": ["list", "list", "bogus"]}).json()["org_views"] \
        == ["list", "tree"]
