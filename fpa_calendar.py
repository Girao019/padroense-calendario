#!/usr/bin/env python3
"""Gera um calendário iCalendar com todos os jogos de seniores de um clube nas provas nacionais da FPA.

Uso: python3 fpa_calendar.py > padroense.ics
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://ws.fpa.pt/index.php/"
CLUB_ID = "878"
CALENDAR_NAME = "Padroense Andebol"
ESCALAO = "Seniores M"
DURATION = timedelta(minutes=90)
LISBON = ZoneInfo("Europe/Lisbon")
PAVILHOES = json.loads((Path(__file__).parent / "pavilhoes.json").read_text(encoding="utf-8"))


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def api(path):
    return json.loads(get(API + path)) or []


def current_season():
    html = get(f"https://portal.fpa.pt/clube/id/{CLUB_ID}")
    m = re.search(r"var TABLE_CONTENT_1\s*=\s*", html)
    data, _ = json.JSONDecoder().raw_decode(html, m.end())
    return next(d["value"] for d in data["dropdowns"] if d["id"] == "season")


def games():
    season = current_season()
    seen = {}
    for prova in api(f"getCompeticoes/{season}/8/{ESCALAO[-1]}/"):
        if prova["ESC_DESCRICAO"] != ESCALAO:
            continue
        for fase in api(f"getFases/{prova['ID_PROVA']}"):
            for row in api(f"getResultadosCalendario/{prova['ID_PROVA']}/{fase['ID_FASE']}"):
                if CLUB_ID in (row["ID_OBJECTO_CASA"], row["ID_OBJECTO_FORA"]):
                    seen[row["ID_PROVA_JOGO"]] = dict(row, ID_PROVA=prova["ID_PROVA"], FASE=fase["DESCRICAO"])
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


def ics(rows):
    # Truncated to the day so the scheduled run commits at most once a day.
    stamp = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT000000Z")
    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//padroense-calendario//PT",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{CALENDAR_NAME}",
        "X-WR-TIMEZONE:Europe/Lisbon",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for r in rows:
        home, away = " ".join(r["EQUIPA_CASA"].split()), " ".join(r["EQUIPA_FORA"].split())
        score = f" {r['JOG_GOLOS_CASA']}-{r['JOG_GOLOS_FORA']} " if r["JOG_GOLOS_CASA"] is not None else " vs "
        competition = " ".join(r["PRO_DESCRICAO"].split())
        prefix = "Taça: " if "TACA" in competition.upper() else ""
        start = datetime.fromisoformat(f"{r['JOG_DATA']}T{r['JOG_HORA'] or '00:00'}").replace(tzinfo=LISBON)
        out += [
            "BEGIN:VEVENT",
            f"UID:{r['ID_PROVA_JOGO']}@portal.fpa.pt",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{utc(start)}",
            f"DTEND:{utc(start + DURATION)}",
            "SUMMARY:" + esc(prefix + home + score + away),
            "LOCATION:" + esc(PAVILHOES.get(r["REC_NOME"], r["REC_NOME"])),
            "DESCRIPTION:" + esc(f"{competition} - {r['FASE']} - Jornada {r['PJO_NUM_JORNADA']} (jogo {r['JOG_NUM_JOGO']})\nPavilhão: {r['REC_NOME']}\nhttps://portal.fpa.pt/prova/{r['ID_PROVA']}/"),
            "END:VEVENT",
        ]
    out.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in out) + "\r\n"


if __name__ == "__main__":
    rows = games()
    if not rows:
        sys.exit(f"Nenhum jogo do clube {CLUB_ID} encontrado em {ESCALAO}")
    sys.stdout.write(ics(rows))
