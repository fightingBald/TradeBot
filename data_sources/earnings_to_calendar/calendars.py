"""Calendar export utilities (ICS, Google Calendar, iCloud CalDAV)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Sequence
from zoneinfo import ZoneInfo

from .defaults import DEFAULT_EVENT_DURATION_MINUTES, DEFAULT_TARGET_TIMEZONE
from .domain import EarningsEvent, earnings_key
from .logging_utils import get_logger

logger = get_logger()


def _ics_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics(
    events: Sequence[EarningsEvent],
    prodid: str = "-//earnings-to-calendar//",
    *,
    target_timezone: str = DEFAULT_TARGET_TIMEZONE,
    default_duration_minutes: int = DEFAULT_EVENT_DURATION_MINUTES,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tz = ZoneInfo(target_timezone)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{prodid}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for event in events:
        uid = f"{uuid.uuid4()}@earnings"
        if event.start_at:
            start_local = event.start_at.astimezone(tz)
            end_source = event.end_at or (
                event.start_at + timedelta(minutes=default_duration_minutes)
            )
            end_local = end_source.astimezone(tz)
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{now}",
                    f"SUMMARY:{_ics_escape(event.summary())}",
                    f"DTSTART;TZID={tz.key}:{start_local.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND;TZID={tz.key}:{end_local.strftime('%Y%m%dT%H%M%S')}",
                    f"DESCRIPTION:{_ics_escape(event.description())}",
                    "TRANSP:OPAQUE",
                    "STATUS:CONFIRMED",
                ]
            )
        else:
            dtstart = event.date.strftime("%Y%m%d")
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{now}",
                    f"SUMMARY:{_ics_escape(event.summary())}",
                    f"DTSTART;VALUE=DATE:{dtstart}",
                    f"DESCRIPTION:{_ics_escape(event.description())}",
                    "TRANSP:TRANSPARENT",
                    "STATUS:CONFIRMED",
                ]
            )
        if event.url:
            lines.append(f"URL:{_ics_escape(event.url)}")
        lines.extend(
            [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                "DESCRIPTION:Earnings reminder",
                "TRIGGER:-P1D",
                "END:VALARM",
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                "DESCRIPTION:Earnings reminder",
                "TRIGGER:-PT2H",
                "END:VALARM",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def _get_google_service(creds_path: str, token_path: str):
    """
    需要先在 https://developers.google.com/workspace/calendar/api/quickstart/python 按 Quickstart 下载 OAuth credentials.json
    首次运行会打开浏览器授权，令牌保存在 token.json
    """
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    scopes = ["https://www.googleapis.com/auth/calendar"]
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def _ensure_calendar(
    service,
    calendar_id: str | None,
    calendar_name: str | None,
    create_if_missing: bool,
) -> str:
    if calendar_id:
        return calendar_id

    if not calendar_name:
        return "primary"

    calendar_name_lower = calendar_name.lower()
    page_token: Optional[str] = None
    while True:
        response = (
            service.calendarList()
            .list(pageToken=page_token, showDeleted=False, maxResults=250)
            .execute()
        )
        for item in response.get("items", []):
            summary = item.get("summary") or ""
            if summary.lower() == calendar_name_lower:
                logger.info("发现现有 Google 日历：%s -> %s", summary, item.get("id"))
                return item.get("id")
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    if not create_if_missing:
        raise RuntimeError(
            f"未找到名为 {calendar_name} 的 Google 日历，且未开启自动创建"
        )

    logger.info("创建新的 Google 日历：%s", calendar_name)
    created = service.calendars().insert(body={"summary": calendar_name}).execute()
    return created.get("id")


def _earnings_key(event: EarningsEvent) -> str:
    return earnings_key(event)


def _build_google_event_body(
    event: EarningsEvent,
    *,
    start_local: Optional[datetime],
    end_local: Optional[datetime],
    target_tz: ZoneInfo,
    default_duration_minutes: int,
) -> Dict[str, object]:
    end_date = event.date + timedelta(days=1)
    key = _earnings_key(event)
    body: Dict[str, object] = {
        "summary": event.summary(),
        "description": event.description(),
        "transparency": "transparent",
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 24 * 60},
                {"method": "popup", "minutes": 120},
            ],
        },
        "extendedProperties": {
            "private": {
                "earnings_key": key,
                "earnings_symbol": event.symbol.upper(),
                "earnings_session": (event.session or "").upper(),
            }
        },
    }
    if start_local:
        end_local = end_local or (
            start_local + timedelta(minutes=default_duration_minutes)
        )
        body["start"] = {"dateTime": start_local.isoformat(), "timeZone": target_tz.key}
        body["end"] = {"dateTime": end_local.isoformat(), "timeZone": target_tz.key}
    else:
        body["start"] = {"date": event.iso_date}
        body["end"] = {"date": end_date.strftime("%Y-%m-%d")}
    if event.url:
        body["source"] = {"title": event.source or "source", "url": event.url}
    return body


def google_insert(
    events: Sequence[EarningsEvent],
    calendar_id: str | None = "primary",
    creds_path: str = "credentials.json",
    token_path: str = "token.json",
    *,
    calendar_name: str | None = None,
    create_if_missing: bool = False,
    target_timezone: str = DEFAULT_TARGET_TIMEZONE,
    default_duration_minutes: int = DEFAULT_EVENT_DURATION_MINUTES,
) -> str:
    """Insert or update earnings events into Google Calendar."""

    service = _get_google_service(creds_path, token_path)
    target_calendar_id = _ensure_calendar(
        service, calendar_id, calendar_name, create_if_missing
    )
    target_tz = ZoneInfo(target_timezone)

    for event in events:
        key = _earnings_key(event)
        if event.start_at:
            end_source = event.end_at or (
                event.start_at + timedelta(minutes=default_duration_minutes)
            )
            start_local = event.start_at.astimezone(target_tz)
            end_local = end_source.astimezone(target_tz)
        else:
            start_local = None
            end_local = None

        event_body = _build_google_event_body(
            event,
            start_local=start_local,
            end_local=end_local,
            target_tz=target_tz,
            default_duration_minutes=default_duration_minutes,
        )

        existing = (
            service.events()
            .list(
                calendarId=target_calendar_id,
                privateExtendedProperty=f"earnings_key={key}",
                singleEvents=True,
                maxResults=1,
            )
            .execute()
        )
        items = existing.get("items", [])
        if items:
            event_id = items[0]["id"]
            service.events().update(
                calendarId=target_calendar_id,
                eventId=event_id,
                body=event_body,
            ).execute()
            logger.debug(
                "更新 Google Calendar 事件：calendarId=%s eventId=%s key=%s",
                target_calendar_id,
                event_id,
                key,
            )
        else:
            service.events().insert(
                calendarId=target_calendar_id, body=event_body
            ).execute()
            logger.debug(
                "创建 Google Calendar 事件：calendarId=%s key=%s",
                target_calendar_id,
                key,
            )

    return target_calendar_id


def icloud_caldav_insert(
    events: Sequence[EarningsEvent],
    apple_id: str,
    app_password: str,
    calendar_name: str = "Earnings",
) -> None:
    """
    需要 Apple app-specific password（非你的登录密码）。iCloud CalDAV 主机 caldav.icloud.com。
    会创建一个名为 Earnings 的日历并写入事件。
    """
    import caldav
    from caldav import DAVClient

    client = DAVClient(
        url="https://caldav.icloud.com/", username=apple_id, password=app_password
    )
    principal = client.principal()
    calendars = principal.calendars()
    target = None
    for calendar in calendars:
        if calendar.name == calendar_name:
            target = calendar
            break
    if target is None:
        target = principal.make_calendar(name=calendar_name)
    ics_payload = build_ics(events)
    target.add_event(ics_payload)
