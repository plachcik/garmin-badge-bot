"""Tests for subscribers.py — all pure functions using a temp file."""
import json

import pytest

import subscribers as sub


@pytest.fixture(autouse=True)
def tmp_subscribers(tmp_path, monkeypatch):
    """Redirect SUBSCRIBERS_FILE to a temp path for every test."""
    tmp_file = str(tmp_path / "subscribers.json")
    monkeypatch.setattr(sub, "SUBSCRIBERS_FILE", tmp_file)
    return tmp_file


class TestLoadSubscribers:
    def test_returns_empty_list_when_no_file(self):
        assert sub.load_subscribers() == []

    def test_returns_saved_list(self, tmp_subscribers):
        with open(tmp_subscribers, "w") as f:
            json.dump([111, 222], f)
        assert sub.load_subscribers() == [111, 222]


class TestSaveSubscribers:
    def test_writes_valid_json(self, tmp_subscribers):
        sub.save_subscribers([1, 2, 3])
        with open(tmp_subscribers) as f:
            assert json.load(f) == [1, 2, 3]

    def test_overwrites_existing(self, tmp_subscribers):
        sub.save_subscribers([1])
        sub.save_subscribers([2, 3])
        assert sub.load_subscribers() == [2, 3]


class TestAddSubscriber:
    def test_new_subscriber_returns_true(self):
        assert sub.add_subscriber(123) is True

    def test_new_subscriber_is_persisted(self):
        sub.add_subscriber(123)
        assert 123 in sub.load_subscribers()

    def test_duplicate_returns_false(self):
        sub.add_subscriber(123)
        assert sub.add_subscriber(123) is False

    def test_duplicate_not_stored_twice(self):
        sub.add_subscriber(123)
        sub.add_subscriber(123)
        assert sub.load_subscribers().count(123) == 1

    def test_multiple_unique_subscribers(self):
        sub.add_subscriber(1)
        sub.add_subscriber(2)
        sub.add_subscriber(3)
        assert sub.load_subscribers() == [1, 2, 3]

    def test_start_multiple_times_safe(self):
        for _ in range(5):
            sub.add_subscriber(42)
        assert sub.load_subscribers() == [42]

    def test_different_chats_all_stored(self):
        chat_ids = [100, 200, 300]
        for cid in chat_ids:
            sub.add_subscriber(cid)
        stored = sub.load_subscribers()
        for cid in chat_ids:
            assert cid in stored
