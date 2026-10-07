"""Prépare le dossier depot/ à envoyer sur GitHub : uniquement ce qui sert à générer les images.

- copie les scripts, plantes.csv, config.json (sans ton e-mail) et les polices ;
- ne garde que la planche retenue pour chaque plante, réduite à 1200 px de haut (le dépôt reste léger) ;
- ajoute le workflow GitHub Actions qui publie les images chaque nuit.

Usage :  python3 preparer_depot.py
Relance-le quand tu changes de planche dans choix.csv, puis renvoie le dossier sur GitHub.
"""
import csv, json, shutil
from pathlib import Path
from PIL import Image

import generer_images as G

DEPOT = Path("depot")
FICHIERS = ["generer_images.py", "selection.py", "publier.py", "meteo.py", "plantes.csv"]


def importer_choix_telecharge():
    """Si un choix.csv plus récent a été enregistré depuis apercu.html dans le dossier Téléchargements,
    il remplace planches/choix.csv (l'ancien est gardé en choix_ancien.csv)."""
    cible = Path("planches/choix.csv")
    candidats = []
    for dossier in (Path.home() / "Downloads", Path.home() / "Téléchargements"):
        if dossier.exists():
            candidats += list(dossier.glob("choix*.csv"))
    if not candidats:
        return
    recent = max(candidats, key=lambda f: f.stat().st_mtime)
    if cible.exists() and recent.stat().st_mtime <= cible.stat().st_mtime:
        return
    if cible.exists():
        shutil.copy(cible, cible.with_name("choix_ancien.csv"))
    shutil.copy(recent, cible)
    print(f"Choix importés depuis {recent} (plus récent que planches/choix.csv).")


def main():
    importer_choix_telecharge()
    DEPOT.mkdir(exist_ok=True)
    for f in FICHIERS:
        shutil.copy(f, DEPOT / f)

    cfg = json.load(open("config.json", encoding="utf-8"))
    cfg["contact"] = ""                                   # ton e-mail ne part pas sur GitHub
    json.dump(cfg, open(DEPOT / "config.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if Path("polices").exists():
        shutil.copytree("polices", DEPOT / "polices", dirs_exist_ok=True)
    else:
        print("Attention : pas de dossier polices/ — les images utiliseraient une police de secours.")

    # planches retenues seulement
    dest = DEPOT / "planches"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir()
    _, choix = G.charger()
    lignes, n = [], 0
    for pid, c in choix.items():
        if not c or not Path(c["fichier"]).exists():
            continue
        cible = dest / pid / "1.jpg"
        cible.parent.mkdir(parents=True)
        img = Image.open(c["fichier"]).convert("RGB")
        img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        img.save(cible, quality=88)
        lignes.append({**c, "rang": "1", "fichier": cible.relative_to(DEPOT).as_posix()})
        n += 1
    champs = ["id", "rang", "fichier", "titre", "source", "auteur", "date", "licence", "page"]
    with open(dest / "candidats.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
        w.writeheader()
        w.writerows(lignes)
    with open(dest / "choix.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "nom_fr", "rang"])
        for l in lignes:
            w.writerow([l["id"], "", "1"])

    wf = DEPOT / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "publier.yml").write_text(WORKFLOW, encoding="utf-8")
    (DEPOT / ".gitignore").write_text("site/\n__pycache__/\n", encoding="utf-8")
    with open(DEPOT / "planches_retenues.txt", "w", encoding="utf-8") as f:
        for l in lignes:
            f.write(f"{l['id']:32} {l['titre']}\n")
    print(f"Dossier {DEPOT}/ prêt : {n} planches (liste dans {DEPOT}/planches_retenues.txt). "
          "Envoie son contenu sur GitHub.")


WORKFLOW = """name: Publier les images du jour

on:
  schedule:
    - cron: "5 22 * * *"      # chaque nuit vers minuit (heure de Paris) ; génère aujourd'hui + demain
  workflow_dispatch:           # bouton « Run workflow » pour lancer à la main
  push:
    branches: [main]

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  construire:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: pip install pillow numpy
      - run: python publier.py
      - uses: actions/upload-pages-artifact@v5
        with:
          path: site
      # GitHub désactive les tâches planifiées d'un dépôt public inactif depuis 60 jours :
      # une petite mise à jour le 1er de chaque mois garde le dépôt actif.
      - name: Garder le dépôt actif
        if: github.event_name == 'schedule'
        run: |
          if [ "$(date +%d)" = "01" ]; then
            date -u > .actif
            git config user.name "github-actions[bot]"
            git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
            git add .actif && git commit -m "Maintien du dépôt actif" && git push
          fi

  publier:
    needs: construire
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deploiement.outputs.page_url }}
    steps:
      - id: deploiement
        uses: actions/deploy-pages@v5
"""

if __name__ == "__main__":
    main()
