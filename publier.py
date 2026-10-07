"""Génère les images d'aujourd'hui et de demain (heure de Paris) dans le dossier site/,
prêt à être publié sur GitHub Pages. Lancé automatiquement chaque nuit par GitHub Actions.

Pour chaque jour :
  site/AAAA-MM-JJ/HH.png   aperçu (pour le navigateur)
  site/AAAA-MM-JJ/HH.bin   image brute pour l'écran : 800 × 480, 1 bit par pixel (48 000 octets)
  site/AAAA-MM-JJ/index.json  liste des plantes de la journée
et site/index.html : la galerie du jour, pratique pour vérifier depuis un téléphone.

Usage local :  python3 publier.py
"""
import datetime as dt, html, json, shutil
from pathlib import Path
from zoneinfo import ZoneInfo

import generer_images as G
import meteo
import selection

SITE = Path("site")


def vers_bin(image, rotation, inverser):
    """Image portrait 480 × 800 -> tampon brut de l'écran (paysage 800 × 480, 1 bit/pixel, bit de poids fort
    à gauche). Par défaut 1 = blanc, comme la bibliothèque Waveshare."""
    img = image.convert("1").rotate(rotation, expand=True)
    assert img.size == (800, 480), img.size
    donnees = img.tobytes()                 # Pillow : 1 bit par pixel, 1 = blanc
    if inverser:
        donnees = bytes(b ^ 0xFF for b in donnees)
    return donnees


def generer_jour(date, plantes, choix, cfg, previsions=None):
    dossier = SITE / date.isoformat()
    dossier.mkdir(parents=True, exist_ok=True)
    avec_planche = {pid for pid, c in choix.items() if c and Path(c["fichier"]).exists()}
    du_jour = selection.plantes_du_jour(date, avec_planche)
    if len({p["id"] for p in du_jour}) < 4:      # presque aucune planche : on reprend toutes les plantes
        du_jour = selection.plantes_du_jour(date)
    ecran = cfg.get("ecran", {})
    liste = []
    for heure, p in enumerate(du_jour):
        img = G.image_plante(p, choix, date, heure, cfg, cfg.get("tramage", "atkinson"),
                             (previsions or {}).get(date))
        img.save(dossier / f"{heure:02d}.png", optimize=True)
        (dossier / f"{heure:02d}.bin").write_bytes(
            vers_bin(img, ecran.get("rotation", 90), ecran.get("inverser", False)))
        liste.append({"heure": heure, "id": p["id"], "nom": p["nom_fr"], "latin": p["nom_latin"]})
        print(f"{date} {heure:02d} h  {p['nom_fr']}")
    (dossier / "index.json").write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
    return liste


def galerie(date, liste):
    cases = "".join(
        f'<figure><img loading="lazy" src="{date}/{x["heure"]:02d}.png">'
        f'<figcaption>{x["heure"]:02d} h · {html.escape(x["nom"])}</figcaption></figure>' for x in liste)
    (SITE / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        "<title>Cadre botanique</title><style>body{font-family:Georgia,serif;margin:16px;background:#f4f1ea}"
        ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}"
        "img{width:100%;border:1px solid #ccc;background:#fff}figcaption{font-size:13px}</style>"
        f"<h1>Cadre botanique — {date:%d/%m/%Y}</h1><div class=g>{cases}</div>"
        "<p style='margin-top:32px;font-size:14px'><a href='credits.html'>Crédits des illustrations</a></p>",
        encoding="utf-8")


OUVRAGES = {
    "Sturm": "Deutschlands Flora in Abbildungen (Sturm)",
    "Köhler": "Köhler's Medizinal-Pflanzen",
    "Flora Batava": "Flora Batava",
    "Curtis": "Curtis's Botanical Magazine",
    "Thomé": "Flora von Deutschland, Österreich und der Schweiz (Thomé)",
    "Lindman": "Bilder ur Nordens Flora (Lindman)",
    "Sowerby": "English Botany (Sowerby)",
    "Fuchs": "De historia stirpium (Fuchs)",
    "Flora Danica": "Flora Danica",
    "Plantenschat": "Plantenschat",
}


def credits(plantes, choix):
    """Page credits.html : illustrateur, ouvrage et source de chaque planche, plus police et météo."""
    e = html.escape
    lignes = []
    for pid, p in sorted(plantes.items(), key=lambda x: x[1]["nom_fr"].lower()):
        c = choix.get(pid)
        if not c or not Path(c["fichier"]).exists():
            continue
        ouvrage = c.get("source") or ""
        ouvrage = OUVRAGES.get(ouvrage, "" if ouvrage in ("Illustration", "ajout manuel") else ouvrage)
        auteur = (c.get("auteur") or "").split("(")[0].strip() or "Auteur inconnu"
        lien = c.get("page") or ""
        source = f'<a href="{e(lien)}">Wikimedia Commons</a>' if lien else "—"
        lignes.append(f"<tr><td>{e(p['nom_fr'])}<br><i>{e(p['nom_latin'])}</i></td><td>{e(auteur)}</td>"
                      f"<td>{e(ouvrage)}</td><td>{e(c.get('licence') or '')}</td><td>{source}</td></tr>")
    (SITE / "credits.html").write_text(
        "<!doctype html><html lang=fr><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        "<title>Crédits — Cadre botanique</title><style>"
        "body{font-family:Georgia,serif;margin:0;background:#f4f1ea;color:#222}"
        "main{max-width:900px;margin:auto;padding:24px 16px}h1{font-weight:normal}"
        "table{border-collapse:collapse;width:100%;font-size:14px;background:#fff}"
        "th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}"
        "th{font-weight:normal;font-variant:small-caps;letter-spacing:1px;background:#ebe6da}"
        "a{color:#2d4a33}.wrap{overflow-x:auto}</style><main>"
        "<h1>Crédits</h1>"
        "<p>Les planches botaniques affichées par le cadre sont des illustrations anciennes du domaine public, "
        "issues de Wikimedia Commons. Elles sont recadrées et converties en noir et blanc pour l'écran. "
        "Merci aux illustrateurs, graveurs et éditeurs qui les ont créées, et aux institutions qui les ont "
        "numérisées.</p>"
        "<p>Police : <i>IM Fell English</i>, d'Igino Marini, sous licence SIL Open Font License. "
        "Prévisions météo : <a href='https://open-meteo.com/'>Open-Meteo.com</a> (CC BY 4.0).</p>"
        f"<h2 style='font-weight:normal'>Planches ({len(lignes)})</h2><div class=wrap><table>"
        "<tr><th>Plante</th><th>Illustrateur</th><th>Ouvrage</th><th>Licence</th><th>Source</th></tr>"
        + "".join(lignes) + "</table></div><p><a href='index.html'>← Planches du jour</a></p></main></html>",
        encoding="utf-8")


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    aujourdhui = dt.datetime.now(ZoneInfo(cfg.get("fuseau", "Europe/Paris"))).date()
    if SITE.exists():
        shutil.rmtree(SITE)
    plantes, choix = G.charger()
    avec = [pid for pid, c in choix.items() if c and Path(c["fichier"]).exists()]
    if not avec:
        raise SystemExit("Aucune planche trouvée : le dossier planches/ (avec candidats.csv et choix.csv) "
                         "manque dans le dépôt.")
    if not Path("polices").exists():
        print("Attention : dossier polices/ absent du dépôt, police de secours utilisée.")
    print(f"{len(avec)} plantes avec planche.")
    previsions = meteo.previsions(cfg)
    for jour, v in previsions.items():
        print(f"Météo {jour} : {v[0]}")
    listes = {}
    for d in (aujourdhui, aujourdhui + dt.timedelta(days=1)):    # demain aussi : couvre le passage de minuit
        listes[d] = generer_jour(d, plantes, choix, cfg, previsions)
    galerie(aujourdhui, listes[aujourdhui])
    credits(plantes, choix)
    (SITE / "derniere_publication.txt").write_text(dt.datetime.now().isoformat(), encoding="utf-8")
    print(f"\nSite prêt dans {SITE}/")


if __name__ == "__main__":
    main()
