#!/usr/bin/env python3
"""Gera o calendário iCalendar e a classificação dos seniores de um clube nas provas nacionais da FPA.

Uso: python3 fpa_calendar.py  (escreve padroense.ics e classificacao.json)
"""
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://ws.fpa.pt/index.php/"
CLUB_ID = "878"
CALENDAR_NAME = "Padroense Andebol"
ESCALAO = "Seniores M"
DURATION = timedelta(minutes=90)
LISBON = ZoneInfo("Europe/Lisbon")
HERE = Path(__file__).parent
PAVILHOES = json.loads((HERE / "pavilhoes.json").read_text(encoding="utf-8"))


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


def is_ours(row):
    return CLUB_ID in (row["ID_OBJECTO_CASA"], row["ID_OBJECTO_FORA"])


def our_name(row):
    return row["EQUIPA_CASA"] if row["ID_OBJECTO_CASA"] == CLUB_ID else row["EQUIPA_FORA"]


def lost(row):
    if row["JOG_GOLOS_CASA"] is None:
        return False
    home, away = int(row["JOG_GOLOS_CASA"]), int(row["JOG_GOLOS_FORA"])
    return home < away if row["ID_OBJECTO_CASA"] == CLUB_ID else away < home


def next_round(rows, ours):
    """Jogos com "Vencedor jogo N" em que N é um jogo nosso ainda não perdido."""
    alive = {r["JOG_NUM_JOGO"]: r for r in ours if not lost(r)}
    found = []
    for row in rows:
        for side in ("EQUIPA_CASA", "EQUIPA_FORA"):
            m = re.fullmatch(r"Vencedor jogo (\d+)", row[side].strip())
            if m and m.group(1) in alive:
                prev = alive[m.group(1)]
                found.append(dict(row, **{side: our_name(prev), "TENTATIVE": prev["JOG_GOLOS_CASA"] is None}))
    return found


def collect():
    season = current_season()
    games, standings = {}, []
    for prova in api(f"getCompeticoes/{season}/8/{ESCALAO[-1]}/"):
        if prova["ESC_DESCRICAO"] != ESCALAO:
            continue
        rows = []
        for fase in api(f"getFases/{prova['ID_PROVA']}"):
            fase_rows = [dict(r, ID_PROVA=prova["ID_PROVA"], ID_FASE=fase["ID_FASE"], FASE=fase["DESCRICAO"])
                         for r in api(f"getResultadosCalendario/{prova['ID_PROVA']}/{fase['ID_FASE']}")]
            rows += fase_rows
            ours = [r for r in fase_rows if is_ours(r)]
            if ours and "TACA" not in prova["PRO_DESCRICAO"].upper():
                standings.append((max(r["JOG_DATA"] for r in ours), prova, fase, our_name(ours[0])))
        ours = [r for r in rows if is_ours(r)]
        for row in ours + next_round(rows, ours):
            games[row["ID_PROVA_JOGO"]] = row
    return sorted(games.values(), key=lambda r: (r["JOG_DATA"], r["JOG_HORA"] or "")), standings


def classificacao(standings):
    if not standings:
        return None
    _, prova, fase, team = max(standings, key=lambda s: s[0])
    rows = api(f"getClassificacoes/{prova['ID_PROVA']}/{fase['ID_FASE']}")
    keys = {"PEQ_CLASS_CLASSIFICACAO": "pos", "CLU_NOME": "equipa", "PEQ_CLASS_NUMERO_JOGOS": "j",
            "PEQ_CLASS_NUMERO_VITORIAS": "v", "PEQ_CLASS_NUMERO_EMPATES": "e", "PEQ_CLASS_NUMERO_DERROTAS": "d",
            "PEQ_CLASS_GOLOS_MARCADOS": "gm", "PEQ_CLASS_GOLOS_SOFRIDOS": "gs", "PEQ_CLASS_PONTOS": "pts"}
    return {
        "prova": " ".join(prova["PRO_DESCRICAO"].split()),
        "fase": fase["DESCRICAO"],
        "equipa": " ".join(team.split()),
        "tabela": [{v: (" ".join(r[k].split()) if k == "CLU_NOME" else r[k]) for k, v in keys.items()} for r in rows],
    }


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


def when(row):
    if row["JOG_HORA"] in (None, "", "00:00"):
        day = date.fromisoformat(row["JOG_DATA"])
        return [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    start = datetime.fromisoformat(f"{row['JOG_DATA']}T{row['JOG_HORA']}").replace(tzinfo=LISBON)
    return [f"DTSTART:{utc(start)}", f"DTEND:{utc(start + DURATION)}"]


def ics(rows, missing=None):
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
        prefix = ("Taça (se vencer): " if r.get("TENTATIVE") else "Taça: ") if "TACA" in competition.upper() else ""
        if r["REC_NOME"] not in PAVILHOES and missing is not None:
            missing.add(r["REC_NOME"])
        out += [
            "BEGIN:VEVENT",
            f"UID:{r['ID_PROVA_JOGO']}@portal.fpa.pt",
            f"DTSTAMP:{stamp}",
            *when(r),
            "SUMMARY:" + esc(prefix + home + score + away),
            "LOCATION:" + esc(PAVILHOES.get(r["REC_NOME"], r["REC_NOME"])),
            "DESCRIPTION:" + esc(f"{competition} - {r['FASE']} - Jornada {r['PJO_NUM_JORNADA']} (jogo {r['JOG_NUM_JOGO']})\nPavilhão: {r['REC_NOME']}\nhttps://portal.fpa.pt/prova/{r['ID_PROVA']}/"),
            "END:VEVENT",
        ]
    out.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in out) + "\r\n"


def main(out=HERE):
    rows, standings = collect()
    if not rows:
        # Between seasons the new season has no fixtures yet; keep the last published files.
        print(f"Sem jogos do clube {CLUB_ID} em {ESCALAO}; ficheiros mantidos.", file=sys.stderr)
        return
    missing = set()
    (out / "padroense.ics").write_bytes(ics(rows, missing).encode("utf-8"))
    table = classificacao(standings)
    if table:
        (out / "classificacao.json").write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for venue in sorted(missing):
        print(f"Pavilhão sem morada: {venue}", file=sys.stderr)


if __name__ == "__main__":
    main()
