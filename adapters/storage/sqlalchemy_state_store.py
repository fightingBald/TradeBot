from __future__ import annotations

import logging
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from adapters.storage.models import Base, FillRecord, OrderRecord, PositionRecord, ProtectionLinkRecord
from core.domain.order import Fill, Order
from core.domain.position import Position

logger = logging.getLogger(__name__)


class SqlAlchemyStateStore:
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

    def upsert_order(self, profile_id: str, order: Order, *, source: str | None = None) -> None:
        with self._session_factory() as session:
            existing = session.execute(
                select(OrderRecord).where(OrderRecord.broker_order_id == order.order_id)
            ).scalar_one_or_none()
            if existing:
                self._apply_order_update(existing, order, source=source)
            else:
                session.add(self._order_to_record(profile_id, order, source=source))
            session.commit()
        logger.info("Stored order %s status=%s", order.order_id, order.status)

    def list_orders(self, profile_id: str, *, limit: int = 100) -> list[Order]:
        with self._session_factory() as session:
            records = session.execute(
                select(OrderRecord)
                .where(OrderRecord.profile_id == profile_id)
                .order_by(OrderRecord.updated_at.desc().nullslast(), OrderRecord.created_at.desc())
                .limit(limit)
            ).scalars()
            return [self._record_to_order(record) for record in records]

    def record_fill(self, profile_id: str, fill: Fill) -> None:
        with self._session_factory() as session:
            existing = session.execute(
                select(FillRecord).where(
                    FillRecord.broker_order_id == fill.order_id,
                    FillRecord.qty == fill.qty,
                    FillRecord.price == fill.price,
                    FillRecord.filled_at == fill.filled_at,
                )
            ).scalar_one_or_none()
            if existing:
                return
            session.add(self._fill_to_record(profile_id, fill))
            session.commit()
        logger.info("Stored fill order_id=%s qty=%s", fill.order_id, fill.qty)

    def list_fills(self, profile_id: str, *, limit: int = 100) -> list[Fill]:
        with self._session_factory() as session:
            records = session.execute(
                select(FillRecord)
                .where(FillRecord.profile_id == profile_id)
                .order_by(FillRecord.filled_at.desc().nullslast(), FillRecord.created_at.desc())
                .limit(limit)
            ).scalars()
            return [self._record_to_fill(record) for record in records]

    def has_protection_link(self, profile_id: str, entry_order_id: str) -> bool:
        with self._session_factory() as session:
            record = session.execute(
                select(ProtectionLinkRecord).where(
                    ProtectionLinkRecord.profile_id == profile_id,
                    ProtectionLinkRecord.entry_order_id == entry_order_id,
                )
            ).scalar_one_or_none()
            return record is not None

    def create_protection_link(self, profile_id: str, entry_order_id: str, protection_order_id: str) -> None:
        with self._session_factory() as session:
            exists = session.execute(
                select(ProtectionLinkRecord).where(
                    ProtectionLinkRecord.profile_id == profile_id,
                    ProtectionLinkRecord.entry_order_id == entry_order_id,
                )
            ).scalar_one_or_none()
            if exists:
                return
            session.add(
                ProtectionLinkRecord(
                    profile_id=profile_id,
                    entry_order_id=entry_order_id,
                    protection_order_id=protection_order_id,
                )
            )
            session.commit()
        logger.info("Linked protection order %s -> %s", entry_order_id, protection_order_id)

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

    @staticmethod
    def _order_to_record(profile_id: str, order: Order, *, source: str | None = None) -> OrderRecord:
        return OrderRecord(
            profile_id=profile_id,
            broker_order_id=order.order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            time_in_force=order.time_in_force,
            status=order.status,
            qty=order.qty,
            filled_qty=order.filled_qty,
            filled_avg_price=order.filled_avg_price,
            trail_percent=order.trail_percent,
            source=source,
            submitted_at=order.submitted_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    def _apply_order_update(record: OrderRecord, order: Order, *, source: str | None = None) -> None:
        record.client_order_id = order.client_order_id or record.client_order_id
        record.symbol = order.symbol
        record.side = order.side
        record.order_type = order.order_type
        record.time_in_force = order.time_in_force
        record.status = order.status
        record.qty = order.qty
        record.filled_qty = order.filled_qty
        record.filled_avg_price = order.filled_avg_price
        record.trail_percent = order.trail_percent
        record.submitted_at = order.submitted_at
        record.updated_at = order.updated_at
        if source:
            record.source = source

    @staticmethod
    def _record_to_order(record: OrderRecord) -> Order:
        return Order(
            order_id=record.broker_order_id,
            client_order_id=record.client_order_id,
            symbol=record.symbol,
            side=record.side,
            order_type=record.order_type,
            time_in_force=record.time_in_force,
            status=record.status,
            qty=Decimal(record.qty) if record.qty is not None else None,
            filled_qty=Decimal(record.filled_qty) if record.filled_qty is not None else None,
            filled_avg_price=Decimal(record.filled_avg_price) if record.filled_avg_price is not None else None,
            trail_percent=Decimal(record.trail_percent) if record.trail_percent is not None else None,
            submitted_at=record.submitted_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _fill_to_record(profile_id: str, fill: Fill) -> FillRecord:
        return FillRecord(
            profile_id=profile_id,
            broker_order_id=fill.order_id,
            symbol=fill.symbol,
            side=fill.side,
            qty=fill.qty,
            price=fill.price,
            filled_at=fill.filled_at,
        )

    @staticmethod
    def _record_to_fill(record: FillRecord) -> Fill:
        return Fill(
            order_id=record.broker_order_id,
            symbol=record.symbol,
            side=record.side,
            qty=Decimal(record.qty),
            price=Decimal(record.price) if record.price is not None else None,
            filled_at=record.filled_at,
        )
