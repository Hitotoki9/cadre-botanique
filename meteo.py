"""Prévisions du jour en une phrase d'almanach, pour le pied de page du cadre.

Données : Open-Meteo (gratuit, sans clé), à partir de la latitude/longitude de config.json.
Exemples : « Belles éclaircies, fraîcheur matinale — 9° à 21° »
           « Grisaille le matin, soleil l'après-midi — 11° à 22° »
           « Ciel limpide, vent d'autan — 14° à 26° »
Pour un même état du ciel, plusieurs formulations existent : le choix change d'un jour à l'autre
mais reste le même toute la journée (les images sont régénérées toutes les 6 h).
"""
import datetime as dt
import json
import random
import urllib.request

# plusieurs formulations par état du ciel (codes météo WMO)
ETATS = {
    0: ["Grand soleil", "Ciel limpide", "Soleil radieux", "Pas un nuage"],
    1: ["Beau temps", "Soleil généreux", "Ciel presque dégagé"],
    2: ["Belles éclaircies", "Soleil et nuages", "Ciel changeant", "Temps mitigé"],
    3: ["Ciel gris", "Temps couvert", "Grisaille", "Ciel bas"],
    45: ["Brouillard", "Temps brumeux", "Brume tenace"], 48: ["Brouillard givrant"],
    51: ["Bruine", "Crachin"], 53: ["Bruine", "Crachin"], 55: ["Bruine soutenue"],
    56: ["Bruine verglaçante"], 57: ["Bruine verglaçante"],
    61: ["Pluie faible", "Petite pluie", "Quelques gouttes"], 63: ["Pluie", "Temps pluvieux"],
    65: ["Forte pluie", "Pluie battante"], 66: ["Pluie verglaçante"], 67: ["Pluie verglaçante"],
    71: ["Quelques flocons"], 73: ["Neige"], 75: ["Forte neige", "Neige abondante"], 77: ["Grésil"],
    80: ["Quelques averses", "Giboulées"], 81: ["Averses"], 82: ["Fortes averses"],
    85: ["Averses de neige"], 86: ["Averses de neige"],
    95: ["Orages", "Temps orageux"], 96: ["Orages et grêle"], 99: ["Orages et grêle"],
}
PRECIPITATIONS = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}
GRIS = {3, 45, 48}
CLAIR = {0, 1}
PERIODES = [("le matin", 6, 12), ("l'après-midi", 12, 18), ("en soirée", 18, 24)]

QUALIFICATIFS = {
    "fortes_gelees": ["fortes gelées", "froid mordant"],
    "gelee": ["gelée au petit matin", "gelée blanche à l'aube", "givre au réveil"],
    "canicule": ["canicule", "chaleur écrasante"],
    "chaleur": ["forte chaleur", "chaleur estivale", "journée brûlante"],
    "tempete": ["fortes rafales", "coups de vent"],
    "vent": ["vent soutenu", "journée venteuse"],
    "nuit_tropicale": ["nuit tropicale"],
    "nuit_douce": ["nuit douce", "douceur nocturne"],
    "frais": ["frais au matin", "fraîcheur matinale", "matin frisquet"],
    "brouillard_matin": ["brouillard matinal", "brumes au lever du jour"],
    "grand_ecart": ["matin frais, après-midi doux", "grand écart de températures"],
}


def telecharger(cfg, jours=3):
    """Renvoie la réponse brute d'Open-Meteo (dict) ou lève une exception."""
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={cfg['latitude']}&longitude={cfg['longitude']}"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,wind_gusts_10m_max,"
           "wind_direction_10m_dominant"
           "&hourly=precipitation,weather_code"
           f"&timezone={cfg.get('fuseau', 'Europe/Paris')}&forecast_days={jours}")
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def _dans_secteur(direction, secteur):
    a, b = secteur
    return a <= direction <= b if a <= b else (direction >= a or direction <= b)


def phrases(donnees, cfg=None):
    """{date: [phrase longue, …, phrase courte]} — le cadre prend la plus longue qui tient."""
    cfg = cfg or {}
    vent_local = cfg.get("vent_local")          # ex. {"nom": "vent d'autan", "secteur": [90, 170], "rafales_min": 40}
    d, h = donnees["daily"], donnees["hourly"]
    pluie = dict(zip(h["time"], h["precipitation"]))
    codes_h = dict(zip(h["time"], h.get("weather_code", [None] * len(h["time"]))))
    resultat = {}
    for i, jour in enumerate(d["time"]):
        hasard = random.Random(jour)            # même tirage toute la journée, différent chaque jour
        choisir = lambda options: hasard.choice(options)
        code = d["weather_code"][i]
        tmin, tmax = d["temperature_2m_min"][i], d["temperature_2m_max"][i]
        rafales = d["wind_gusts_10m_max"][i] or 0
        direction = (d.get("wind_direction_10m_dominant") or [None] * len(d["time"]))[i]

        def code_moyen(h0, h1):
            valeurs = [codes_h.get(f"{jour}T{x:02d}:00") for x in range(h0, h1)]
            valeurs = [v for v in valeurs if v is not None]
            return max(set(valeurs), key=valeurs.count) if valeurs else None
        matin, aprem = code_moyen(8, 12), code_moyen(13, 18)

        # 1. l'état du ciel, avec son évolution dans la journée si elle est nette
        etat = choisir(ETATS.get(code, ["Temps variable"]))
        if code in PRECIPITATIONS:
            mouillees = [nom for nom, h0, h1 in PERIODES
                         if sum(pluie.get(f"{jour}T{x:02d}:00", 0) or 0 for x in range(h0, h1)) >= 0.3]
            if len(mouillees) == 3:
                etat += " toute la journée"
            elif len(mouillees) == 1:
                etat += " " + mouillees[0]
                if mouillees[0] == "l'après-midi" and matin in CLAIR:
                    etat = f"Soleil le matin, {etat[0].lower() + etat[1:]}"
        elif matin in GRIS and aprem in CLAIR:
            etat = choisir(["Grisaille le matin, soleil l'après-midi", "Ciel gris puis éclaircies",
                            "Le soleil perce l'après-midi"])
        elif matin in CLAIR and aprem in GRIS:
            etat = choisir(["Soleil le matin, nuages l'après-midi", "Beau matin, ciel voilé ensuite"])

        # 2. un qualificatif, le plus marquant
        cle = None
        brouillard_matin = any(codes_h.get(f"{jour}T{x:02d}:00") in (45, 48) for x in range(6, 10))
        if tmin <= -4:
            cle = "fortes_gelees"
        elif tmin <= 0:
            cle = "gelee"
        elif tmax >= 35:
            cle = "canicule"
        elif rafales >= 70:
            cle = "tempete"
        elif (vent_local and direction is not None and rafales >= vent_local.get("rafales_min", 40)
              and _dans_secteur(direction, vent_local["secteur"])):
            cle = "local"
        elif tmax >= 30:
            cle = "chaleur"
        elif rafales >= 50:
            cle = "vent"
        elif tmin >= 20:
            cle = "nuit_tropicale"
        elif brouillard_matin and code not in (45, 48):
            cle = "brouillard_matin"
        elif tmax - tmin >= 15:
            cle = "grand_ecart"
        elif tmin < 8:
            cle = "frais"
        elif tmin >= 18:
            cle = "nuit_douce"
        nuance = vent_local["nom"] if cle == "local" else (choisir(QUALIFICATIFS[cle]) if cle else "")

        temp = f"{round(tmin)}° à {round(tmax)}°"
        variantes = []
        if nuance:
            variantes.append(f"{etat}, {nuance} — {temp}")
        variantes.append(f"{etat} — {temp}")
        base = choisir(ETATS.get(code, ["Temps variable"]))
        variantes.append(f"{base} — {temp}")
        resultat[dt.date.fromisoformat(jour)] = list(dict.fromkeys(variantes))
    return resultat


def previsions(cfg):
    """Comme phrases(), mais ne plante jamais : en cas de problème réseau, renvoie {} (date seule)."""
    try:
        return phrases(telecharger(cfg), cfg)
    except Exception as e:  # noqa: BLE001
        print(f"Météo indisponible ({e}) : date seule dans le pied de page.")
        return {}


if __name__ == "__main__":
    cfg = json.load(open("config.json", encoding="utf-8"))
    for jour, v in previsions(cfg).items():
        print(jour, "->", v[0])
