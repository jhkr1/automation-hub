"""나무위키 실시간 검색어 원본 스냅샷 저장 진입점."""

from datetime import timezone
from zoneinfo import ZoneInfo

from namuwiki_trend.collector import collect_trends
from namuwiki_trend.snapshot_pipeline import SnapshotCollectionPipeline

SEOUL_TZ = ZoneInfo("Asia/Seoul")


def build_snapshot_pipeline() -> SnapshotCollectionPipeline:
    """Create the production Collector and snapshot save service."""
    from database.snapshot_save_service import SnapshotSaveService

    return SnapshotCollectionPipeline(collect_trends, SnapshotSaveService())


def main() -> None:
    """Collect and persist one trend snapshot batch."""
    snapshots = build_snapshot_pipeline().run()
    if snapshots:
        collected_at_utc = snapshots[0].collected_at.replace(tzinfo=timezone.utc)
        collected_at_kst = collected_at_utc.astimezone(SEOUL_TZ)
        print(f"Snapshot collection completed: {len(snapshots)} rows saved.")
        print(f"Collected at: {collected_at_utc:%Y-%m-%d %H:%M:%S} UTC")
        print(f"Collected at: {collected_at_kst:%Y-%m-%d %H:%M:%S} KST")
    else:
        print("Snapshot collection completed: no trends collected.")


if __name__ == "__main__":
    main()
