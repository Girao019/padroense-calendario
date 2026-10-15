#!/usr/bin/env python3
"""Gera um calendário iCalendar com os jogos de uma equipa numa prova da FPA.

Uso: python3 fpa_calendar.py [URL_DA_PROVA] [EQUIPA] > calendario.ics
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

URL = "https://portal.fpa.pt/prova/10018/"
TEAM = "PADROENSE"
DURATION = timedelta(minutes=90)
LISBON = ZoneInfo("Europe/Lisbon")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def games(html, team):
    decoder = json.JSONDecoder()
    seen = {}
    for m in re.finditer(r"var TABLE_CONTENT_\d+\s*=\s*", html):
        data, _ = decoder.raw_decode(html, m.end())
        for tab in data.get("tabs", []):
            if tab.get("id") != "results":
                continue
            for row in tab.get("rows", []):
                if team in row["EQUIPA_CASA"].upper() + row["EQUIPA_FORA"].upper():
                    seen[row["ID_PROVA_JOGO"]] = row
    return sorted(seen.values(), key=lambda r: (r["JOG_DATA"], r["JOG_HORA"] or ""))


def esc(text):
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line, limit=75):
    parts, current = [], b""
    for ch in line:
        encoded = ch.encode("utf-8")
        if len(current) + len(encoded) > limit:
            parts.append(current)
            current, limit = b" ", 75
        current += encoded
    parts.append(current)
    return "\r\n".join(p.decode("utf-8") for p in parts)


def utc(dt):
    return dt.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")


def ics(rows, competition):
    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//padroense-calendario//PT",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{esc(TEAM.title())} Andebol",
        "X-WR-TIMEZONE:Europe/Lisbon",
    ]
    for r in rows:
        home, away = " ".join(r["EQUIPA_CASA"].split()), " ".join(r["EQUIPA_FORA"].split())
        score = f" {r['JOG_GOLOS_CASA']}-{r['JOG_GOLOS_FORA']} " if r["JOG_GOLOS_CASA"] is not None else " vs "
        start = datetime.fromisoformat(f"{r['JOG_DATA']}T{r['JOG_HORA'] or '00:00'}").replace(tzinfo=LISBON)
        out += [
            "BEGIN:VEVENT",
            f"UID:{r['ID_PROVA_JOGO']}@portal.fpa.pt",
            f"DTSTAMP:{utc(start)}",
            f"DTSTART:{utc(start)}",
            f"DTEND:{utc(start + DURATION)}",
            f"SUMMARY:{esc(home + score + away)}",
            f"LOCATION:{esc(r['REC_NOME'])}",
            "DESCRIPTION:" + esc(f"{competition} - Jornada {r['PJO_NUM_JORNADA']} (jogo {r['JOG_NUM_JOGO']})"),
            f"URL:{URL}",
            "END:VEVENT",
        ]
    out.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in out) + "\r\n"


if __name__ == "__main__":
    URL = sys.argv[1] if len(sys.argv) > 1 else URL
    TEAM = sys.argv[2].upper() if len(sys.argv) > 2 else TEAM
    rows = games(fetch(URL), TEAM)
    if not rows:
        sys.exit(f"Nenhum jogo de {TEAM} encontrado em {URL}")
    sys.stdout.write(ics(rows, rows[0]["PRO_DESCRICAO"]))
