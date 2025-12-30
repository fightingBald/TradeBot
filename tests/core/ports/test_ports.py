from __future__ import annotations

from core.ports import BrokerPort, CommandBus, MarketDataPort, StateStore


def test_ports_expose_expected_methods() -> None:
    assert {"get_positions", "cancel_open_orders", "close_all_positions"} <= set(BrokerPort.__dict__)
    assert {"publish", "consume", "close"} <= set(CommandBus.__dict__)
    assert {"get_latest_quotes"} <= set(MarketDataPort.__dict__)
    assert {"upsert_positions", "list_positions"} <= set(StateStore.__dict__)


def test_ports_module_exports() -> None:
    assert BrokerPort.__name__ in {"BrokerPort"}
    assert CommandBus.__name__ in {"CommandBus"}
    assert MarketDataPort.__name__ in {"MarketDataPort"}
    assert StateStore.__name__ in {"StateStore"}
