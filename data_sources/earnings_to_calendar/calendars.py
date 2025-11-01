"""Calendar export utilities (ICS, Google Calendar, iCloud CalDAV)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

from .domain import EarningsEvent


def _ics_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics(events: Sequence[EarningsEvent], prodid: str = "-//earnings-to-calendar//") -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{prodid}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for event in events:
        dtstart = event.date.strftime("%Y%m%d")
        uid = f"{uuid.uuid4()}@earnings"
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


def google_insert(
    events: Sequence[EarningsEvent],
    calendar_id: str = "primary",
    creds_path: str = "credentials.json",
    token_path: str = "token.json",
) -> None:
    """
    需要先在 https://developers.google.com/workspace/calendar/api/quickstart/python 按 Quickstart 下载 OAuth credentials.json
    首次运行会打开浏览器授权，令牌保存在 token.json
    """
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    scopes = ["https://www.googleapis.com/auth/calendar.events"]
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

    service = build("calendar", "v3", credentials=creds)
    for event in events:
        end_date = event.date + timedelta(days=1)
        body = {
            "summary": event.summary(),
            "description": event.description(),
            "start": {"date": event.iso_date},
            "end": {"date": end_date.strftime("%Y-%m-%d")},
            "transparency": "transparent",
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 24 * 60},
                    {"method": "popup", "minutes": 120},
                ],
            },
        }
        if event.url:
            body["source"] = {"title": event.source or "source", "url": event.url}
        service.events().insert(calendarId=calendar_id, body=body).execute()


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

    client = DAVClient(url="https://caldav.icloud.com/", username=apple_id, password=app_password)
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
