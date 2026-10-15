from fpa_calendar import fold

short = "LOCATION:MUN. PADRÃO LÉGUA"
assert fold(short) == short

long = "DESCRIPTION:" + "Á" * 100
folded = fold(long).split("\r\n")
assert all(len(p.encode("utf-8")) <= 75 for p in folded)
assert all(p.startswith(" ") for p in folded[1:])
assert folded[0] + "".join(p[1:] for p in folded[1:]) == long
print("ok")
