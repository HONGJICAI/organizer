"""Tests for tag classification (/api/tags)."""
from model import TagInfo


def tags(client):
    return {t["name"]: (t["kind"], t["canonical"]) for t in client.get("/api/tags").json()}


class TestGetAll:
    def test_empty(self, client):
        r = client.get("/api/tags")
        assert r.status_code == 200
        assert r.json() == []

    def test_sorted_by_name(self, client, session):
        session.add(TagInfo(name="b", kind="author"))
        session.add(TagInfo(name="a", kind="ignored"))
        session.commit()
        assert [t["name"] for t in client.get("/api/tags").json()] == ["a", "b"]


class TestSetKind:
    def test_set_and_change(self, client):
        r = client.post("/api/tags/kind", json={"names": [" Alice ", "Bob", "Bob"], "kind": "author"})
        assert r.status_code == 200
        assert {t["name"] for t in r.json()["tags"]} == {"Alice", "Bob"}
        client.post("/api/tags/kind", json={"names": ["Bob"], "kind": "language"})
        assert tags(client) == {"Alice": ("author", None), "Bob": ("language", None)}

    def test_alias_becomes_standalone(self, client):
        client.post("/api/tags/merge", json={"primary": "アリス", "aliases": ["Alice"]})
        client.post("/api/tags/kind", json={"names": ["Alice"], "kind": "ignored"})
        assert tags(client)["Alice"] == ("ignored", None)

    def test_unclassify_forgets_tag_and_its_aliases(self, client):
        client.post("/api/tags/kind", json={"names": ["アリス", "Bob"], "kind": "author"})
        client.post("/api/tags/merge", json={"primary": "アリス", "aliases": ["Alice"]})
        r = client.post("/api/tags/kind", json={"names": ["アリス", "Never seen"], "kind": None})
        assert r.status_code == 200
        assert tags(client) == {"Bob": ("author", None)}

    def test_empty_name(self, client):
        r = client.post("/api/tags/kind", json={"names": [" "], "kind": "author"})
        assert r.status_code == 400

    def test_no_names(self, client):
        assert client.post("/api/tags/kind", json={"names": [], "kind": "author"}).status_code == 400

    def test_bad_kind(self, client):
        r = client.post("/api/tags/kind", json={"names": ["a"], "kind": "circle"})
        assert r.status_code == 400


class TestMerge:
    def test_primary_takes_kind_of_alias(self, client):
        client.post("/api/tags/kind", json={"names": ["Alice"], "kind": "author"})
        r = client.post("/api/tags/merge", json={"primary": "アリス", "aliases": ["Alice", "アリス"]})
        assert r.status_code == 200
        assert tags(client) == {"アリス": ("author", None), "Alice": (None, "アリス")}

    def test_primary_keeps_its_kind(self, client):
        client.post("/api/tags/kind", json={"names": ["アリス"], "kind": "ignored"})
        client.post("/api/tags/kind", json={"names": ["Alice"], "kind": "author"})
        client.post("/api/tags/merge", json={"primary": "アリス", "aliases": ["Alice"]})
        assert tags(client)["アリス"] == ("ignored", None)

    def test_unclassified_merge(self, client):
        client.post("/api/tags/merge", json={"primary": "A", "aliases": ["B"]})
        assert tags(client) == {"A": (None, None), "B": (None, "A")}

    def test_aliases_are_flattened(self, client):
        client.post("/api/tags/kind", json={"names": ["X"], "kind": "author"})
        client.post("/api/tags/merge", json={"primary": "X", "aliases": ["x1", "x2"]})
        # Merging X into Y moves X's aliases to Y.
        client.post("/api/tags/merge", json={"primary": "Y", "aliases": ["X"]})
        assert tags(client) == {
            "Y": ("author", None), "X": (None, "Y"), "x1": (None, "Y"), "x2": (None, "Y"),
        }

    def test_alias_promoted_to_primary(self, client):
        client.post("/api/tags/kind", json={"names": ["X"], "kind": "author"})
        client.post("/api/tags/merge", json={"primary": "X", "aliases": ["x1"]})
        # x1 breaks away from X as a primary of its own, keeping X's kind.
        client.post("/api/tags/merge", json={"primary": "x1", "aliases": ["x2"]})
        assert tags(client) == {"X": ("author", None), "x1": ("author", None), "x2": (None, "x1")}

    def test_only_primary(self, client):
        r = client.post("/api/tags/merge", json={"primary": "A", "aliases": ["A", " A "]})
        assert r.status_code == 400

    def test_empty_primary(self, client):
        r = client.post("/api/tags/merge", json={"primary": "", "aliases": ["A"]})
        assert r.status_code == 400
