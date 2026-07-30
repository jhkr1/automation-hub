"""DATABASE_URL로 MySQL 연결을 확인하는 수동 검증 스크립트."""

from sqlalchemy import text

from database.engine import engine


def main() -> int:
    """데이터베이스에 연결하고 SELECT 1을 실행한다."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - manual process boundary reports failure
        print(f"[database] 연결 실패: {type(exc).__name__}: {exc}")
        return 1

    print("[database] MySQL 연결 성공")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
