from datetime import date, datetime
from zoneinfo import ZoneInfo

import toolkits.calendar_svc.calendars as calendars_mod
from toolkits.calendar_svc import build_ics
from toolkits.calendar_svc.domain import EarningsEvent

from .conftest import StubGoogleService


def test_build_ics_generates_expected_fields():
    ny = ZoneInfo("America/New_York")
    berlin = ZoneInfo("Europe/Berlin")
    event = EarningsEvent(
        symbol="AAPL",
        date=date(2024, 1, 25),
        session="AMC",
        source="FMP",
        url="https://example.com",
        start_at=datetime(2024, 1, 25, 17, 0, tzinfo=ny),
        end_at=datetime(2024, 1, 25, 18, 0, tzinfo=ny),
    )
    ics = build_ics([event], prodid="-//test//", target_timezone=berlin.key, default_duration_minutes=90)

    assert "PRODID:-//test//" in ics
    assert "SUMMARY:AAPL Earnings (AMC)" in ics
    assert "DESCRIPTION:Earnings date from FMP." in ics
    assert "URL:https://example.com" in ics
    assert "DTSTART;TZID=Europe/Berlin:20240125T230000" in ics
    assert "DTEND;TZID=Europe/Berlin:20240126T000000" in ics


def test_google_insert_creates_calendar_when_missing(monkeypatch):
    service = StubGoogleService()
    monkeypatch.setattr(calendars_mod, "_get_google_service", lambda *args, **kwargs: service)

    ny = ZoneInfo("America/New_York")
    event = EarningsEvent(
        symbol="AAPL",
        date=date(2024, 5, 1),
        session="AMC",
        source="FMP",
        start_at=datetime(2024, 5, 1, 17, 0, tzinfo=ny),
        end_at=datetime(2024, 5, 1, 18, 0, tzinfo=ny),
        timezone="America/New_York",
    )

    config = calendars_mod.GoogleCalendarConfig(
        calendar_id=None,
        creds_path="cred.json",
        token_path="token.json",
        calendar_name="Company Earnings",
        create_if_missing=True,
        target_timezone="Europe/Berlin",
        default_duration_minutes=75,
    )
    calendar_id = calendars_mod.google_insert([event], config=config)

    assert calendar_id in service.calendars_data
    assert service.calendars_data[calendar_id] == "Company Earnings"
    assert len(service.calendar_inserts) == 1
    assert len(service.events_data[calendar_id]) == 1
    stored_event = service.events_data[calendar_id][0]
    assert "dateTime" in stored_event["start"]
    assert stored_event["start"]["timeZone"] == "Europe/Berlin"


def test_google_insert_upserts_existing(monkeypatch):
    service = StubGoogleService({"primary": "Primary"})
    monkeypatch.setattr(calendars_mod, "_get_google_service", lambda *args, **kwargs: service)

    ny = ZoneInfo("America/New_York")
    base_event = EarningsEvent(
        symbol="MSFT",
        date=date(2024, 6, 10),
        session="BMO",
        source="FMP",
        start_at=datetime(2024, 6, 10, 8, 0, tzinfo=ny),
        end_at=datetime(2024, 6, 10, 9, 0, tzinfo=ny),
        timezone="America/New_York",
    )

    config = calendars_mod.GoogleCalendarConfig(
        calendar_id="primary",
        creds_path="cred.json",
        token_path="token.json",
        target_timezone="America/Chicago",
        default_duration_minutes=45,
    )
    calendars_mod.google_insert([base_event], config=config)

    assert len(service.events_data["primary"]) == 1
    first_event = service.events_data["primary"][0]
    event_id = first_event["id"]

    updated_event = EarningsEvent(
        symbol="MSFT",
        date=date(2024, 6, 10),
        session="BMO",
        source="FMP",
        notes="Updated desc",
        start_at=datetime(2024, 6, 10, 8, 0, tzinfo=ny),
        end_at=datetime(2024, 6, 10, 9, 0, tzinfo=ny),
        timezone="America/New_York",
    )

    calendars_mod.google_insert([updated_event], config=config)

    assert len(service.events_data["primary"]) == 1
    stored_event = service.events_data["primary"][0]
    assert stored_event["id"] == event_id
    assert "Updated desc" in stored_event["description"]
    assert stored_event["start"]["timeZone"] == "America/Chicago"
    assert len(service.insert_calls) == 1
    assert len(service.update_calls) == 1


def test_get_google_service_reauths_when_refresh_fails(tmp_path, monkeypatch):
    token_path = tmp_path / "nested" / "token.json"
    token_path.parent.mkdir(parents=True, exist_ok=False)
    token_path.write_text("stale-token", encoding="utf-8")
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text("client-creds", encoding="utf-8")

    calls: dict[str, int] = {"refresh": 0, "reauth": 0}

    class FakeCreds:
        def __init__(self, valid: bool = False, expired: bool = True, refresh_token: bool = True):
            self.valid = valid
            self.expired = expired
            self.refresh_token = refresh_token

        def refresh(self, request):
            from google.auth.exceptions import RefreshError

            calls["refresh"] += 1
            raise RefreshError("invalid_grant")

        def to_json(self) -> str:  # pragma: no cover - simple helper
            return '{"token": "new-token"}'

    def fake_from_user_file(path, scopes):
        return FakeCreds()

    class FakeFlow:
        @classmethod
        def from_client_secrets_file(cls, path, scopes):
            return cls()

        def run_local_server(self, port):
            calls["reauth"] += 1
            return FakeCreds(valid=True, expired=False, refresh_token=False)

    class DummyService:
        pass

    def fake_build(*args, **kwargs):
        return DummyService()

    import google.auth.transport.requests as requests_mod
    import google.oauth2.credentials as credentials_mod
    import google_auth_oauthlib.flow as flow_mod
    import googleapiclient.discovery as discovery_mod

    monkeypatch.setattr(credentials_mod.Credentials, "from_authorized_user_file", staticmethod(fake_from_user_file))
    monkeypatch.setattr(flow_mod, "InstalledAppFlow", FakeFlow)
    monkeypatch.setattr(requests_mod, "Request", lambda: "request")
    monkeypatch.setattr(discovery_mod, "build", fake_build)

    service = calendars_mod._get_google_service(str(creds_path), str(token_path))

    assert isinstance(service, DummyService)
    assert calls["refresh"] == 1
    assert calls["reauth"] == 1
    assert token_path.read_text(encoding="utf-8") == '{"token": "new-token"}'
    assert token_path.parent.exists()


def test_google_insert_recovers_after_refresh_error(tmp_path, monkeypatch):
    token_path = tmp_path / "deep" / "token.json"
    token_path.parent.mkdir(parents=True, exist_ok=False)
    token_path.write_text("stale-token", encoding="utf-8")
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text("client-creds", encoding="utf-8")

    calls: dict[str, int] = {"refresh": 0, "reauth": 0}

    class FakeCreds:
        def __init__(self, valid: bool = False, expired: bool = True, refresh_token: bool = True):
            self.valid = valid
            self.expired = expired
            self.refresh_token = refresh_token

        def refresh(self, request):
            from google.auth.exceptions import RefreshError

            calls["refresh"] += 1
            raise RefreshError("invalid_grant")

        def to_json(self):  # pragma: no cover - simple helper
            return '{"token": "new-token"}'

    def fake_from_user_file(path, scopes):
        return FakeCreds()

    class FakeFlow:
        @classmethod
        def from_client_secrets_file(cls, path, scopes):
            return cls()

        def run_local_server(self, port):
            calls["reauth"] += 1
            return FakeCreds(valid=True, expired=False, refresh_token=False)

    stub_service = StubGoogleService()

    def fake_build(*args, **kwargs):
        return stub_service

    import google.auth.transport.requests as requests_mod
    import google.oauth2.credentials as credentials_mod
    import google_auth_oauthlib.flow as flow_mod
    import googleapiclient.discovery as discovery_mod

    monkeypatch.setattr(credentials_mod.Credentials, "from_authorized_user_file", staticmethod(fake_from_user_file))
    monkeypatch.setattr(flow_mod, "InstalledAppFlow", FakeFlow)
    monkeypatch.setattr(requests_mod, "Request", lambda: "request")
    monkeypatch.setattr(discovery_mod, "build", fake_build)

    ny = ZoneInfo("America/New_York")
    event = EarningsEvent(
        symbol="AAPL",
        date=date(2024, 5, 1),
        session="AMC",
        source="FMP",
        start_at=datetime(2024, 5, 1, 17, 0, tzinfo=ny),
        timezone="America/New_York",
    )

    calendar_id = calendars_mod.google_insert(
        [event],
        config=calendars_mod.GoogleCalendarConfig(
            calendar_id=None,
            creds_path=str(creds_path),
            token_path=str(token_path),
            calendar_name="Company Earnings",
            create_if_missing=True,
            target_timezone="America/New_York",
            default_duration_minutes=60,
        ),
    )

    assert calls["refresh"] == 1
    assert calls["reauth"] == 1
    assert token_path.read_text(encoding="utf-8") == '{"token": "new-token"}'
    assert calendar_id in stub_service.calendars_data
    # 确认事件被写入新创建的日历
    assert stub_service.events_data[calendar_id]
