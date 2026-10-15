#!/usr/bin/env python3
"""Gera um calendário iCalendar com os jogos de uma equipa em provas da FPA.

Uso: python3 fpa_calendar.py [EQUIPA] [ID_PROVA ...] > calendario.ics
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

API = "https://ws.fpa.pt/index.php/"
TEAM = "PADROENSE"
PROVAS = ["10018", "10030"]
DURATION = timedelta(minutes=90)
LISBON = ZoneInfo("Europe/Lisbon")


def fetch(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r) or []


def games(team, provas):
    seen = {}
    for prova in provas:
        for fase in fetch(f"getFases/{prova}"):
            for row in fetch(f"getResultadosCalendario/{prova}/{fase['ID_FASE']}"):
                if team in row["EQUIPA_CASA"].upper() + row["EQUIPA_FORA"].upper():
                    seen[row["ID_PROVA_JOGO"]] = dict(row, ID_PROVA=prova, FASE=fase["DESCRICAO"])
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
        f"X-WR-CALNAME:{esc(TEAM.title())} Andebol",
        "X-WR-TIMEZONE:Europe/Lisbon",
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
            "LOCATION:" + esc(r["REC_NOME"]),
            "DESCRIPTION:" + esc(f"{competition} - {r['FASE']} - Jornada {r['PJO_NUM_JORNADA']} (jogo {r['JOG_NUM_JOGO']})"),
            f"URL:https://portal.fpa.pt/prova/{r['ID_PROVA']}/",
            "END:VEVENT",
        ]
    out.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in out) + "\r\n"


if __name__ == "__main__":
    TEAM = sys.argv[1].upper() if len(sys.argv) > 1 else TEAM
    provas = sys.argv[2:] or PROVAS
    rows = games(TEAM, provas)
    if not rows:
        sys.exit(f"Nenhum jogo de {TEAM} encontrado nas provas {provas}")
    sys.stdout.write(ics(rows))
