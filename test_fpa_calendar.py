from fpa_calendar import fold, ics, next_round

short = "LOCATION:MUN. PADRÃO LÉGUA"
assert fold(short) == short

long = "DESCRIPTION:" + "Á" * 100
folded = fold(long).split("\r\n")
assert all(len(p.encode("utf-8")) <= 75 for p in folded)
assert all(p.startswith(" ") for p in folded[1:])
assert folded[0] + "".join(p[1:] for p in folded[1:]) == long


def game(num, home, away, gh=None, ga=None, hora="19:00", casa="878", fora="1"):
    return {"JOG_NUM_JOGO": num, "EQUIPA_CASA": home, "EQUIPA_FORA": away, "JOG_GOLOS_CASA": gh, "JOG_GOLOS_FORA": ga,
            "ID_OBJECTO_CASA": casa, "ID_OBJECTO_FORA": fora, "JOG_DATA": "2026-11-07", "JOG_HORA": hora,
            "ID_PROVA_JOGO": num, "PRO_DESCRICAO": "PO20 - Taca", "FASE": "F", "PJO_NUM_JORNADA": "1",
            "REC_NOME": "X", "ID_PROVA": "1"}


ours = game("1043", "PADROENSE FC", "BALTAR")
nxt = game("1619", "S. PAIO", "Vencedor jogo 1043", casa="70", fora="59")
other = game("1620", "LUSITANOS", "Vencedor jogo 1045", casa="853", fora="59")
found = next_round([ours, nxt, other], [ours])
assert [(g["JOG_NUM_JOGO"], g["EQUIPA_FORA"], g["TENTATIVE"]) for g in found] == [("1619", "PADROENSE FC", True)]
assert next_round([nxt], [dict(ours, JOG_GOLOS_CASA="20", JOG_GOLOS_FORA="25")]) == []
assert next_round([nxt], [dict(ours, JOG_GOLOS_CASA="25", JOG_GOLOS_FORA="20")])[0]["TENTATIVE"] is False

cal = ics(found + [game("1", "PADROENSE FC", "Y", hora=None)])
assert "SUMMARY:Taça (se vencer): S. PAIO vs PADROENSE FC" in cal
assert "DTSTART;VALUE=DATE:20261107\r\nDTEND;VALUE=DATE:20261108" in cal
print("ok")
