"""Prévisions du jour en une phrase d'almanach, pour le pied de page du cadre.

Données : Open-Meteo (gratuit, sans clé), à partir de la latitude/longitude de config.json.
Exemple de résultat : « Belles éclaircies, frais au matin — 9° à 21° »
"""
import datetime as dt
import json
import urllib.request

ETATS = {
    0: "Grand soleil", 1: "Beau temps", 2: "Belles éclaircies", 3: "Ciel gris",
    45: "Brouillard", 48: "Brouillard givrant",
    51: "Bruine", 53: "Bruine", 55: "Bruine", 56: "Bruine verglaçante", 57: "Bruine verglaçante",
    61: "Pluie faible", 63: "Pluie", 65: "Forte pluie", 66: "Pluie verglaçante", 67: "Pluie verglaçante",
    71: "Quelques flocons", 73: "Neige", 75: "Forte neige", 77: "Grésil",
    80: "Quelques averses", 81: "Averses", 82: "Fortes averses", 85: "Averses de neige", 86: "Averses de neige",
    95: "Orages", 96: "Orages et grêle", 99: "Orages et grêle",
}
PRECIPITATIONS = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}
PERIODES = [("le matin", 6, 12), ("l'après-midi", 12, 18), ("en soirée", 18, 24)]


def telecharger(cfg, jours=3):
    """Renvoie la réponse brute d'Open-Meteo (dict) ou lève une exception."""
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={cfg['latitude']}&longitude={cfg['longitude']}"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,wind_gusts_10m_max"
           "&hourly=precipitation"
           f"&timezone={cfg.get('fuseau', 'Europe/Paris')}&forecast_days={jours}")
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def phrases(donnees):
    """{date: [phrase longue, phrase moyenne, phrase courte]} — le cadre prend la plus longue qui tient."""
    d, h = donnees["daily"], donnees["hourly"]
    pluie_par_heure = dict(zip(h["time"], h["precipitation"]))
    resultat = {}
    for i, jour in enumerate(d["time"]):
        code = d["weather_code"][i]
        tmin, tmax = d["temperature_2m_min"][i], d["temperature_2m_max"][i]
        rafales = d["wind_gusts_10m_max"][i] or 0
        etat = ETATS.get(code, "Temps variable")

        # à quel moment tombe la pluie (ou la neige) ?
        moment = ""
        if code in PRECIPITATIONS:
            mouillees = [nom for nom, h0, h1 in PERIODES
                         if sum(pluie_par_heure.get(f"{jour}T{x:02d}:00", 0) or 0 for x in range(h0, h1)) >= 0.3]
            if len(mouillees) == 3:
                moment = " toute la journée"
            elif len(mouillees) == 1:
                moment = " " + mouillees[0]

        # un seul qualificatif, le plus utile
        if tmin <= 0:
            nuance = "gelée au petit matin"
        elif rafales >= 60:
            nuance = "vent fort"
        elif tmax >= 32:
            nuance = "forte chaleur"
        elif tmin < 8:
            nuance = "frais au matin"
        elif tmin >= 18:
            nuance = "nuit douce"
        else:
            nuance = ""

        temp = f"{round(tmin)}° à {round(tmax)}°"
        variantes = []
        if nuance:
            variantes.append(f"{etat}{moment}, {nuance} — {temp}")
        variantes += [f"{etat}{moment} — {temp}", f"{etat} — {temp}"]
        resultat[dt.date.fromisoformat(jour)] = list(dict.fromkeys(variantes))
    return resultat


def previsions(cfg):
    """Comme phrases(), mais ne plante jamais : en cas de problème réseau, renvoie {} (le cadre affiche la date seule)."""
    try:
        return phrases(telecharger(cfg))
    except Exception as e:  # noqa: BLE001
        print(f"Météo indisponible ({e}) : date seule dans le pied de page.")
        return {}


if __name__ == "__main__":
    cfg = json.load(open("config.json", encoding="utf-8"))
    for jour, v in previsions(cfg).items():
        print(jour, "->", v[0])
