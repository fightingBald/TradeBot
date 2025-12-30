from __future__ import annotations

import logging
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from adapters.storage.models import Base, PositionRecord
from core.domain.position import Position

logger = logging.getLogger(__name__)


class SqliteStateStore:
    def __init__(self, database_url: str, *, create_tables: bool = True) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self._engine: Engine = create_engine(database_url, connect_args=connect_args, future=True)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)
        if create_tables:
            Base.metadata.create_all(self._engine)

    def upsert_positions(self, profile_id: str, positions: Sequence[Position]) -> None:
        with self._session_factory() as session:
            self._replace_positions(session, profile_id, positions)
            session.commit()
        logger.info("Stored %d positions for profile %s", len(positions), profile_id)

    def list_positions(self, profile_id: str) -> list[Position]:
        with self._session_factory() as session:
            records = session.execute(
                select(PositionRecord)
                .where(PositionRecord.profile_id == profile_id)
                .order_by(PositionRecord.market_value.desc())
            ).scalars()
            return [self._record_to_position(record) for record in records]

    def close(self) -> None:
        self._engine.dispose()

    def _replace_positions(self, session: Session, profile_id: str, positions: Sequence[Position]) -> None:
        session.execute(delete(PositionRecord).where(PositionRecord.profile_id == profile_id))
        for position in positions:
            session.add(self._position_to_record(profile_id, position))

    @staticmethod
    def _position_to_record(profile_id: str, position: Position) -> PositionRecord:
        return PositionRecord(
            profile_id=profile_id,
            symbol=position.symbol,
            asset_id=position.asset_id,
            asset_class=position.asset_class,
            exchange=position.exchange,
            side=position.side,
            quantity=position.quantity,
            avg_entry_price=position.avg_entry_price,
            market_value=position.market_value,
            cost_basis=position.cost_basis,
            unrealized_pl=position.unrealized_pl,
            unrealized_plpc=position.unrealized_plpc,
            current_price=position.current_price,
            lastday_price=position.lastday_price,
            change_today=position.change_today,
        )

    @staticmethod
    def _record_to_position(record: PositionRecord) -> Position:
        return Position(
            symbol=record.symbol,
            asset_id=record.asset_id,
            asset_class=record.asset_class,
            exchange=record.exchange,
            side=record.side,
            quantity=Decimal(record.quantity),
            avg_entry_price=Decimal(record.avg_entry_price),
            market_value=Decimal(record.market_value),
            cost_basis=Decimal(record.cost_basis),
            unrealized_pl=Decimal(record.unrealized_pl) if record.unrealized_pl is not None else None,
            unrealized_plpc=Decimal(record.unrealized_plpc) if record.unrealized_plpc is not None else None,
            current_price=Decimal(record.current_price) if record.current_price is not None else None,
            lastday_price=Decimal(record.lastday_price) if record.lastday_price is not None else None,
            change_today=Decimal(record.change_today) if record.change_today is not None else None,
        )
