from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from database.models import TrendSnapshot
from database.snapshot_save_service import SnapshotSaveService
from namuwiki_trend.models import TrendItem


class FakeSession:
    def __init__(self, *, fail: bool = False) -> None:
        self.added: list[TrendSnapshot] = []
        self.fail = fail
        self.committed = False
        self.rolled_back = False

    def add_all(self, snapshots: list[TrendSnapshot]) -> None:
        if self.fail:
            raise IntegrityError("insert failed", {}, ValueError("duplicate"))
        self.added.extend(snapshots)


class FakeTransaction:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __enter__(self) -> FakeSession:
        return self.session

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if exc_type is None:
            self.session.committed = True
        else:
            self.session.rolled_back = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.session)


def trends() -> list[TrendItem]:
    return [
        TrendItem(rank=1, keyword="first", href="/first"),
        TrendItem(rank=2, keyword="second", href="/second"),
    ]


def test_save_converts_and_commits_trends_with_one_collected_at() -> None:
    session = FakeSession()
    collected_at = datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc)
    service = SnapshotSaveService(FakeSessionFactory(session), clock=lambda: collected_at)

    saved = service.save(trends())

    assert saved == session.added
    assert [snapshot.rank_position for snapshot in saved] == [1, 2]
    assert [snapshot.keyword for snapshot in saved] == ["first", "second"]
    assert {snapshot.collected_at for snapshot in saved} == {
        datetime(2026, 7, 30, 8, 0)
    }
    assert session.committed is True
    assert session.rolled_back is False


def test_save_rolls_back_and_reraises_integrity_error() -> None:
    session = FakeSession(fail=True)
    service = SnapshotSaveService(FakeSessionFactory(session))

    with pytest.raises(IntegrityError):
        service.save(trends())

    assert session.committed is False
    assert session.rolled_back is True
