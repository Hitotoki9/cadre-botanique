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


def generer_jour(date, plantes, choix, cfg):
    dossier = SITE / date.isoformat()
    dossier.mkdir(parents=True, exist_ok=True)
    avec_planche = {pid for pid, c in choix.items() if c and Path(c["fichier"]).exists()}
    du_jour = selection.plantes_du_jour(date, avec_planche)
    if len({p["id"] for p in du_jour}) < 4:      # presque aucune planche : on reprend toutes les plantes
        du_jour = selection.plantes_du_jour(date)
    ecran = cfg.get("ecran", {})
    liste = []
    for heure, p in enumerate(du_jour):
        img = G.image_plante(p, choix, date, heure, cfg, cfg.get("tramage", "atkinson"))
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
        f"<h1>Cadre botanique — {date:%d/%m/%Y}</h1><div class=g>{cases}</div>", encoding="utf-8")


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    aujourdhui = dt.datetime.now(ZoneInfo(cfg.get("fuseau", "Europe/Paris"))).date()
    if SITE.exists():
        shutil.rmtree(SITE)
    plantes, choix = G.charger()
    listes = {}
    for d in (aujourdhui, aujourdhui + dt.timedelta(days=1)):    # demain aussi : couvre le passage de minuit
        listes[d] = generer_jour(d, plantes, choix, cfg)
    galerie(aujourdhui, listes[aujourdhui])
    (SITE / "derniere_publication.txt").write_text(dt.datetime.now().isoformat(), encoding="utf-8")
    print(f"\nSite prêt dans {SITE}/")


if __name__ == "__main__":
    main()
