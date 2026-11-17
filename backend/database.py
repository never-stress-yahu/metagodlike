"""SQLite storage for exactly one active player and one bounded snapshot."""
import json
import os

from sqlalchemy import Column, Float, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dota_helper.db")
if not SQLALCHEMY_DATABASE_URL.startswith("sqlite:"):
    raise ValueError("This single-player backend requires a SQLite DATABASE_URL")
engine = create_engine(SQLALCHEMY_DATABASE_URL,
                       connect_args={"check_same_thread": False, "timeout": 15})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    account_id = Column(Integer, primary_key=True)
    persona_name = Column(String)
    rank_tier = Column(Integer)
    total_wins = Column(Integer, default=0)
    total_losses = Column(Integer, default=0)
    favorite_hero_id = Column(Integer, nullable=True)
    best_hero_id = Column(Integer, nullable=True)
    best_hero_games = Column(Integer, default=0)
    best_hero_winrate = Column(Float, default=0.0)
    best_hero_score = Column(Float, default=0.0)


class ActiveSnapshot(Base):
    __tablename__ = "active_snapshot"
    id = Column(Integer, primary_key=True)
    payload = Column(Text, nullable=False)


def init_db() -> None:
    """Apply the legacy additive migration under a SQLite write lock at startup."""
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            Base.metadata.create_all(bind=connection)
            existing = {c["name"] for c in inspect(connection).get_columns("users")}
            additions = {
                "favorite_hero_id": "INTEGER", "best_hero_id": "INTEGER",
                "best_hero_games": "INTEGER DEFAULT 0",
                "best_hero_winrate": "FLOAT DEFAULT 0.0",
                "best_hero_score": "FLOAT DEFAULT 0.0",
            }
            for name, definition in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {definition}"))
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def save_active_player(cache: dict) -> None:
    if len(cache["history"]) > 1000 or len(cache["recent"]) > 20:
        raise ValueError("Snapshot exceeds the agreed match limits")
    payload = json.dumps({"version": 1, "cache": cache}, allow_nan=False)
    if len(payload.encode("utf-8")) > 4_000_000:
        raise ValueError("Active-player snapshot exceeds 4 MB")
    with SessionLocal.begin() as db:
        db.query(User).delete(synchronize_session=False)
        favorite, best = cache["favorite_hero"], cache["best_hero"]
        db.add(User(
            account_id=cache["account_id"], persona_name=cache["player_name"],
            rank_tier=cache["rank"], total_wins=cache["total_wins"],
            total_losses=cache["total_losses"],
            favorite_hero_id=favorite["hero_id"] if favorite else None,
            best_hero_id=best["hero_id"] if best else None,
            best_hero_games=best["games"] if best else 0,
            best_hero_winrate=best["winrate"] if best else 0.0,
            best_hero_score=best["performance_score"] if best else 0.0,
        ))
        db.merge(ActiveSnapshot(id=1, payload=payload))


def load_active_player() -> dict | None:
    with SessionLocal() as db:
        snapshot = db.get(ActiveSnapshot, 1)
        if snapshot is None:
            return None
        envelope = json.loads(snapshot.payload)
    if envelope.get("version") != 1:
        raise ValueError("Unsupported snapshot version")
    cache = envelope["cache"]
    required = {"account_id", "source", "synced_at", "player_name", "rank", "total_wins",
                "total_losses", "history", "recent", "heroes", "favorite_hero", "best_hero", "meta"}
    if not isinstance(cache, dict) or not required.issubset(cache):
        raise ValueError("Incomplete active-player snapshot")
    if len(cache["history"]) > 1000 or len(cache["recent"]) > 20:
        raise ValueError("Oversized snapshot")
    cache["meta"]["heroes"] = {
        int(hero_id): {**row, "positions": {int(p): stats for p, stats in row["positions"].items()}}
        for hero_id, row in cache["meta"].get("heroes", {}).items()
    }
    return cache
