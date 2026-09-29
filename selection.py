"""Plantes en fleur à une date donnée, pour le lieu défini dans config.json.
Usage : python3 selection.py [AAAA-MM-JJ]"""
import csv, json, random, sys, datetime as dt

cfg = json.load(open("config.json", encoding="utf-8"))
ref = cfg["reference"]
# Décalage des floraisons (loi bioclimatique de Hopkins, simplifiée) :
# plus au sud / plus bas = printemps plus précoce, automne plus tardif.
decalage = round(cfg["jours_par_degre_latitude"] * (cfg["latitude"] - ref["latitude"])
                 + cfg["jours_par_100m_altitude"] * (cfg["altitude_m"] - ref["altitude_m"]) / 100)

def jour(mmjj, annee):
    m, j = map(int, mmjj.split("-"))
    d = dt.date(annee, m, j).timetuple().tm_yday
    # printemps/été (janvier-juillet) : décalé ; automne/hiver : décalé en sens inverse
    return d + decalage if m <= 7 else d - decalage

def en_fleur(p, date):
    d = date.timetuple().tm_yday
    a, b = jour(p["debut"], date.year), jour(p["fin"], date.year)
    return a <= d <= b if a <= b else (d >= a or d <= b)   # floraison à cheval sur deux années

def plantes_du_jour(date, ids_autorises=None):
    """ids_autorises : si fourni, ne garde que ces plantes (par exemple celles qui ont une planche)."""
    plantes = [p for p in csv.DictReader(open("plantes.csv", encoding="utf-8"))
               if p["zone"] in cfg["zones"] and en_fleur(p, date)
               and (ids_autorises is None or p["id"] in ids_autorises)]
    random.Random(date.toordinal()).shuffle(plantes)      # ordre différent chaque jour, mais reproductible
    n = cfg["plantes_par_jour"]
    return [plantes[h % len(plantes)] for h in range(n)] if plantes else []

if __name__ == "__main__":
    date = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today()
    print(f"{cfg['lieu']} — {date:%d/%m/%Y} (décalage {decalage:+d} jours par rapport à la référence)\n")
    for h, p in enumerate(plantes_du_jour(date)):
        print(f"{h:02d} h  {p['nom_fr']} ({p['nom_latin']})")
