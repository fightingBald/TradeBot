from __future__ import annotations

from dataclasses import dataclass


class StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class StubExecute:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


@dataclass
class _EventCall:
    calendar_id: str
    body: dict


@dataclass
class _UpdateCall:
    calendar_id: str
    event_id: str
    body: dict


class StubGoogleService:
    def __init__(self, calendars: dict[str, str] | None = None):
        self.calendars_data: dict[str, str] = calendars or {}
        self.events_data: dict[str, list[dict]] = {}
        self.calendar_inserts: list[dict] = []
        self.insert_calls: list[_EventCall] = []
        self.update_calls: list[_UpdateCall] = []

    # Calendar list API
    def calendarList(self):  # noqa: N802 (Google API style)
        outer = self

        class CalendarList:
            def list(self, **kwargs):  # noqa: ANN001
                items = [
                    {"id": cid, "summary": summary}
                    for cid, summary in outer.calendars_data.items()
                ]
                return StubExecute({"items": items})

        return CalendarList()

    # Calendar management API
    def calendars(self):  # noqa: N802
        outer = self

        class Calendars:
            def insert(self, body):  # noqa: ANN001
                new_id = f"cal_{len(outer.calendars_data) + 1}"
                summary = body.get("summary", new_id)
                outer.calendars_data[new_id] = summary
                outer.calendar_inserts.append(body)
                return StubExecute({"id": new_id, "summary": summary})

        return Calendars()

    # Events API
    def events(self):  # noqa: N802
        outer = self

        class Events:
            def list(
                self, calendarId, privateExtendedProperty, **kwargs
            ):  # noqa: ANN001,N803
                key = privateExtendedProperty.split("=", 1)[1]
                matches = [
                    evt
                    for evt in outer.events_data.get(calendarId, [])
                    if evt.get("extendedProperties", {})
                    .get("private", {})
                    .get("earnings_key")
                    == key
                ]
                return StubExecute({"items": matches})

            def insert(self, calendarId, body):  # noqa: ANN001,N803
                body = body.copy()
                events = outer.events_data.setdefault(calendarId, [])
                body.setdefault("id", f"evt_{len(events) + 1}")
                events.append(body)
                outer.insert_calls.append(_EventCall(calendarId, body))
                return StubExecute(body)

            def update(self, calendarId, eventId, body):  # noqa: ANN001,N803
                body = body.copy()
                body["id"] = eventId
                events = outer.events_data.setdefault(calendarId, [])
                for idx, existing in enumerate(events):
                    if existing.get("id") == eventId:
                        events[idx] = body
                        break
                else:
                    events.append(body)
                outer.update_calls.append(_UpdateCall(calendarId, eventId, body))
                return StubExecute(body)

        return Events()
