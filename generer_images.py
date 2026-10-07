"""Transforme les planches téléchargées en images 480 × 800 noir et blanc pour l'écran e-ink.

Pour chaque plante, le script :
  1. prend la planche retenue dans planches/choix.csv ;
  2. retire les marges de papier vide autour du dessin ;
  3. blanchit le papier jauni et renforce le contraste ;
  4. la redimensionne pour la zone d'illustration ;
  5. la convertit en noir et blanc par tramage (Atkinson par défaut, idéal pour l'e-ink) ;
  6. ajoute le nom, le nom latin, la famille, la période de floraison, la note, le crédit et la date.

Usage :
    pip install pillow numpy
    python3 generer_images.py                         # les 24 images d'aujourd'hui -> sortie/AAAA-MM-JJ/00.png … 23.png
    python3 generer_images.py --date 2026-10-02       # les 24 images d'un autre jour
    python3 generer_images.py --plante colchicum-autumnale   # une seule plante, pour tester -> sortie/test/
    python3 generer_images.py --essais colchicum-autumnale   # compare 9 réglages de relief/papier
    python3 generer_images.py --toutes                # une image par plante ayant une planche -> sortie/toutes/
Options :
    --tramage atkinson|floyd|seuil    (défaut : atkinson)
"""
import csv, datetime as dt, json, sys, textwrap
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import selection   # même dossier : gère le lieu, le décalage des floraisons et le choix des 24 plantes

L, H = 480, 800                        # écran 7,5" utilisé en portrait
ZONE = (30, 30, 450, 522)              # zone de l'illustration (x0, y0, x1, y1), à l'intérieur du cadre
CADRE = (22, 22, 458, 530)
DOSSIER_PLANCHES = Path("planches")
SORTIE = Path("sortie")

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
JOURS = ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE"]

# Polices : la première trouvée est utilisée (Windows, macOS, Linux). Modifiable dans config.json -> "polices".
POLICES = {
    "normal": ["polices/IMFellEnglish-Regular.ttf",
               "C:/Windows/Fonts/georgia.ttf", "/System/Library/Fonts/Supplemental/Georgia.ttf",
               "/usr/share/fonts/truetype/crosextra/Caladea-Regular.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"],
    "italique": ["polices/IMFellEnglish-Italic.ttf",
                 "C:/Windows/Fonts/georgiai.ttf", "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
                 "/usr/share/fonts/truetype/crosextra/Caladea-Italic.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"],
}
POLICES["titre"] = POLICES["normal"]      # le nom de la plante : peut avoir sa propre police (config.json)


# ---------- polices ----------

def police(style, taille, cfg):
    chemins = [cfg.get("polices", {}).get(style)] + POLICES[style]
    for c in chemins:
        if c and Path(c).exists():
            return ImageFont.truetype(c, taille)
    print("Attention : aucune police trouvée, police par défaut utilisée (indique un .ttf dans config.json).")
    return ImageFont.load_default()


# ---------- traitement de la planche ----------

def cadre_imprime(encre):
    """Cherche le filet imprimé autour de la planche (lignes presque continues près des bords).
    Renvoie (x0, y0, x1, y1) de l'intérieur du cadre, ou None s'il n'y en a pas."""
    h, w = encre.shape
    lignes = encre.mean(axis=1)
    colonnes = encre.mean(axis=0)
    def filet(profil, debut, fin, pas):
        for i in range(debut, fin, pas):
            if profil[i] > 0.5:
                return i
        return None
    haut = filet(lignes, 0, int(h * 0.2), 1)
    bas = filet(lignes, h - 1, int(h * 0.8), -1)
    gauche = filet(colonnes, 0, int(w * 0.2), 1)
    droite = filet(colonnes, w - 1, int(w * 0.8), -1)
    if None in (haut, bas, gauche, droite):
        return None
    m = int(0.012 * max(h, w))                  # on se place juste à l'intérieur du filet
    return gauche + m, haut + m, droite - m, bas - m


def recadrer(gris):
    """Retire les marges de papier vide et, s'il y en a un, le cadre imprimé avec son titre et sa légende
    (le cadre de l'écran et le nom de la plante les remplacent)."""
    a = np.asarray(gris, dtype=np.int16)
    papier = np.percentile(a, 90)
    encre = a < papier - 45
    cadre = cadre_imprime(encre)
    if cadre:
        x0, y0, x1, y1 = cadre
        gris = gris.crop(cadre)
        a, encre = a[y0:y1, x0:x1], encre[y0:y1, x0:x1]
    lignes = np.where(encre.mean(axis=1) > 0.004)[0]
    colonnes = np.where(encre.mean(axis=0) > 0.004)[0]
    if len(lignes) < 10 or len(colonnes) < 10:
        return gris
    marge = int(0.015 * max(a.shape))
    y0, y1 = max(lignes[0] - marge, 0), min(lignes[-1] + marge, a.shape[0])
    x0, x1 = max(colonnes[0] - marge, 0), min(colonnes[-1] + marge, a.shape[1])
    return gris.crop((x0, y0, x1, y1))


def niveaux(gris, contraste=1.0, papier=0.85):
    """Papier jauni -> blanc pur, encre -> noir, avec un léger renforcement des demi-teintes.
    papier : tout ce qui est plus clair que ce seuil (0-1) devient blanc pur. Ça supprime le
    pointillé que le tramage ferait apparaître sur les taches, ombres de reliure et bords de scan."""
    a = np.asarray(gris, dtype=np.float32)
    blanc = np.percentile(a, 88) - 6          # le papier (majoritaire) devient blanc
    noir = np.percentile(a, 1.5)
    a = np.clip((a - noir) / max(blanc - noir, 1), 0, 1)
    a = a ** (1.15 * contraste)                 # contraste > 1 : plus sombre ; < 1 : plus clair
    a = np.clip(a / papier, 0, 1)               # papier légèrement teinté -> blanc
    return Image.fromarray((a * 255).astype(np.uint8))


def atkinson(gris):
    """Tramage d'Atkinson : garde les blancs propres et les traits nets, très adapté à l'e-ink."""
    a = np.asarray(gris, dtype=np.float32).copy()
    h, w = a.shape
    for y in range(h):
        for x in range(w):
            ancien = a[y, x]
            nouveau = 255.0 if ancien >= 128 else 0.0
            a[y, x] = nouveau
            e = (ancien - nouveau) / 8
            if x + 1 < w: a[y, x + 1] += e
            if x + 2 < w: a[y, x + 2] += e
            if y + 1 < h:
                if x > 0: a[y + 1, x - 1] += e
                a[y + 1, x] += e
                if x + 1 < w: a[y + 1, x + 1] += e
            if y + 2 < h: a[y + 2, x] += e
    return Image.fromarray(a.astype(np.uint8)).convert("1", dither=Image.Dither.NONE)


def preparer_planche(chemin, largeur, hauteur, tramage, contraste=0.7, papier=0.94, relief=80):
    img = Image.open(chemin)
    img = ImageOps.exif_transpose(img).convert("RGB")
    # le canal vert rend mieux les fleurs roses/rouges que la simple conversion en gris
    r, v, b = img.split()
    gris = Image.merge("RGB", (r, v, b)).convert("L")
    gris = Image.blend(gris, v, 0.35)
    gris = recadrer(gris)
    gris = niveaux(gris, contraste, papier)
    gris.thumbnail((largeur, hauteur), Image.Resampling.LANCZOS)
    if relief:
        # contraste local : fait réapparaître les hachures dans les zones sombres (bulbes, feuillages denses)
        gris = gris.filter(ImageFilter.UnsharpMask(radius=10, percent=int(relief), threshold=0))
    gris = gris.filter(ImageFilter.UnsharpMask(radius=1.2, percent=90, threshold=2))
    if tramage == "seuil":
        return gris.point(lambda p: 255 if p > 140 else 0).convert("1")
    if tramage == "floyd":
        return gris.convert("1")               # Floyd-Steinberg (Pillow)
    return atkinson(gris)


# ---------- texte ----------

def mois_floraison(p):
    """Période de floraison ajustée au lieu (via selection.py)."""
    if p["debut"] == "01-01" and p["fin"] == "12-31":
        return "En fleur toute l'année"
    annee = 2025
    def mois(mmjj):
        j = min(max(selection.jour(mmjj, annee), 1), 365)
        return (dt.date(annee, 1, 1) + dt.timedelta(days=j - 1)).month
    m1, m2 = MOIS[mois(p["debut"]) - 1], MOIS[mois(p["fin"]) - 1]
    de = "d'" if m1[0] in "aeiouo" else "de "
    if m1 == m2:
        return f"En fleur en {m1}"
    return f"En fleur {de}{m1} à {m2}"


def centre(d, y, texte, f, espacement=0):
    if espacement:
        largeur = sum(d.textlength(c, font=f) for c in texte) + espacement * (len(texte) - 1)
        x = (L - largeur) / 2
        for c in texte:
            d.text((x, y), c, font=f, fill=0)
            x += d.textlength(c, font=f) + espacement
    else:
        d.text(((L - d.textlength(texte, font=f)) / 2, y), texte, font=f, fill=0)


def couper(d, texte, f, largeur_max):
    """Coupe un texte en lignes qui tiennent dans largeur_max pixels."""
    lignes, ligne = [], ""
    for mot in texte.split():
        essai = f"{ligne} {mot}".strip()
        if d.textlength(essai, font=f) <= largeur_max:
            ligne = essai
        else:
            lignes.append(ligne)
            ligne = mot
    return lignes + [ligne] if ligne else lignes


def taille_ajustee(d, texte, style, taille, largeur_max, cfg):
    while taille > 18:
        f = police(style, taille, cfg)
        if d.textlength(texte, font=f) <= largeur_max:
            return f
        taille -= 2
    return police(style, taille, cfg)


def composer(plante, planche_1bit, credit, date, heure, cfg, meteo=None):
    page = Image.new("L", (L, H), 255)
    d = ImageDraw.Draw(page)
    d.fontmode = "1"                      # texte sans anticrénelage : plus net sur un écran noir et blanc

    # double filet autour de l'illustration (seulement s'il y a une planche)
    if planche_1bit is not None:
        d.rectangle(CADRE, outline=0, width=1)
        d.rectangle((CADRE[0] + 4, CADRE[1] + 4, CADRE[2] - 4, CADRE[3] - 4), outline=0, width=1)

    # textes
    titre = taille_ajustee(d, plante["nom_fr"], "titre", 36, L - 40, cfg)
    centre(d, 560, plante["nom_fr"], titre)
    centre(d, 604, plante["nom_latin"], taille_ajustee(d, plante["nom_latin"], "italique", 23, L - 60, cfg))
    centre(d, 638, plante["famille"].upper(), police("normal", 14, cfg), espacement=3)
    d.line((L / 2 - 30, 664, L / 2 + 30, 664), fill=0, width=1)
    centre(d, 674, mois_floraison(plante), police("normal", 19, cfg))
    f_note = police("italique", 17, cfg)
    for i, ligne in enumerate(couper(d, plante["note"], f_note, L - 70)[:3]):
        centre(d, 702 + i * 21, ligne, f_note)

    f_petit = police("normal", 14, cfg)
    if credit:
        f_credit = police("italique", 13, cfg)
        d.text((CADRE[2] - d.textlength(credit, font=f_credit), CADRE[3] + 4), credit, font=f_credit, fill=0)
    # pied de page : « 07/10 · Belles éclaircies, frais au matin — 9° à 21° »
    pied_page(d, date, meteo, cfg)

    # texte en noir et blanc net (seuil), puis on colle la planche tramée au centre de la zone
    page = page.point(lambda p: 255 if p > 150 else 0).convert("1")
    if planche_1bit is not None:
        zx0, zy0, zx1, zy1 = ZONE
        x = zx0 + (zx1 - zx0 - planche_1bit.width) // 2
        y = zy0 + (zy1 - zy0 - planche_1bit.height) // 2
        page.paste(planche_1bit, (x, y))
    return page


def pied_page(d, date, meteo, cfg):
    """Date courte en romain, puis la phrase météo en italique ; on prend la variante la plus longue qui tient."""
    largeur = L - 50
    date_txt = f"{date.day:02d}/{date.month:02d}"
    for taille in (16, 15, 14):
        f_date, f_meteo = police("normal", taille, cfg), police("italique", taille, cfg)
        sep = "  ·  "
        for phrase in (meteo or []):
            total = d.textlength(date_txt + sep, font=f_date) + d.textlength(phrase, font=f_meteo)
            if total <= largeur:
                x = (L - total) / 2
                d.text((x, H - 28), date_txt + sep, font=f_date, fill=0)
                d.text((x + d.textlength(date_txt + sep, font=f_date), H - 28), phrase, font=f_meteo, fill=0)
                return
    centre(d, H - 28, date_txt, police("normal", 16, cfg))     # pas de météo : la date seule


# ---------- données ----------

def charger():
    plantes = {p["id"]: p for p in csv.DictReader(open("plantes.csv", encoding="utf-8"))}
    candidats = {}
    if (DOSSIER_PLANCHES / "candidats.csv").exists():
        for c in csv.DictReader(open(DOSSIER_PLANCHES / "candidats.csv", encoding="utf-8")):
            c["fichier"] = c["fichier"].replace("\\", "/")   # chemins Windows -> compatibles partout
            candidats[(c["id"], str(c["rang"]))] = c
    choix = {}
    if (DOSSIER_PLANCHES / "choix.csv").exists():
        for c in csv.DictReader(open(DOSSIER_PLANCHES / "choix.csv", encoding="utf-8-sig")):
            if c["rang"]:
                choix[c["id"]] = candidats.get((c["id"], str(c["rang"])))
    return plantes, choix


def credit_de(c):
    if not c:
        return ""
    auteur = c.get("auteur", "").split("(")[0].strip()
    source = c.get("source", "")
    source = "" if source in ("", "Illustration") or source.lower() in auteur.lower() else source
    return " · ".join(x for x in (source, auteur) if x)[:70]


_cache = {}
def image_plante(p, choix, date, heure, cfg, tramage, meteo=None):
    c = choix.get(p["id"])
    planche = None
    if c and Path(c["fichier"]).exists():
        if c["fichier"] not in _cache:
            _cache[c["fichier"]] = preparer_planche(
                c["fichier"], ZONE[2] - ZONE[0], ZONE[3] - ZONE[1], tramage,
                cfg.get("contraste", 0.7), cfg.get("papier", 0.94), cfg.get("relief", 80))
        planche = _cache[c["fichier"]]
    else:
        print(f"   pas de planche pour {p['nom_fr']} : texte seul")
    return composer(p, planche, credit_de(c), date, heure, cfg, meteo)


def essais(p, choix, cfg, tramage):
    """Planche de comparaison : 3 reliefs x 3 réglages de papier (contraste pris dans config.json), pour choisir les valeurs de config.json."""
    c = choix.get(p["id"])
    if not c:
        sys.exit("Pas de planche pour cette plante.")
    reliefs, papiers = [0, 80, 160], [0.9, 0.94, 0.97]
    co = cfg.get("contraste", 0.7)
    w, h = ZONE[2] - ZONE[0], ZONE[3] - ZONE[1]
    grille = Image.new("1", (3 * (w + 20) + 20, 3 * (h + 40) + 20), 1)
    d = ImageDraw.Draw(grille)
    f = police("normal", 16, cfg)
    for i, pa in enumerate(papiers):
        for j, re_ in enumerate(reliefs):
            x, y = 20 + j * (w + 20), 20 + i * (h + 40)
            planche = preparer_planche(c["fichier"], w, h, tramage, co, pa, re_)
            grille.paste(planche, (x, y + 30))
            # et chaque essai en image complète, pour le voir tel qu'il sera sur l'écran
            (SORTIE / "test" / "essais").mkdir(parents=True, exist_ok=True)
            composer(p, planche, credit_de(c), dt.date.today(), None, cfg).save(
                SORTIE / "test" / "essais" / f"{p['id']}_relief{re_}_papier{pa}.png")
            d.text((x, y + 4), f"relief {re_}   papier {pa}", font=f, fill=0)
            print(f"   relief {re_}, papier {pa}")
    dossier = SORTIE / "test"
    dossier.mkdir(parents=True, exist_ok=True)
    grille.save(dossier / f"{p['id']}_essais.png")
    print(f"-> {dossier / (p['id'] + '_essais.png')}  (les 9 versions côte à côte)")
    print(f"-> {dossier / 'essais'}  (les 9 versions en images séparées)")


def main():
    args = sys.argv[1:]
    def option(nom, defaut=None):
        return args[args.index(nom) + 1] if nom in args else defaut
    tramage = option("--tramage", "atkinson")
    date = dt.date.fromisoformat(option("--date")) if option("--date") else dt.date.today()
    cfg = json.load(open("config.json", encoding="utf-8"))
    plantes, choix = charger()
    import meteo
    previsions = {} if ("--essais" in args or "--toutes" in args) else meteo.previsions(cfg)
    ciel = previsions.get(date)

    if "--essais" in args:
        essais(plantes[option("--essais")], choix, cfg, tramage)
    elif "--plante" in args:
        dossier = SORTIE / "test"
        dossier.mkdir(parents=True, exist_ok=True)
        pid = option("--plante")
        image_plante(plantes[pid], choix, date, None, cfg, tramage, ciel).save(dossier / f"{pid}_{tramage}.png")
        print(f"-> {dossier / f'{pid}_{tramage}.png'}")
    elif "--toutes" in args:
        dossier = SORTIE / "toutes"
        dossier.mkdir(parents=True, exist_ok=True)
        faites, sans = 0, []
        for pid, p in plantes.items():
            c = choix.get(pid)
            if c and Path(c["fichier"]).exists():
                image_plante(p, choix, date, None, cfg, tramage).save(dossier / f"{pid}.png")
                print(f"-> {pid}")
                faites += 1
            else:
                sans.append(p["nom_fr"])
        print(f"\n{faites} image(s) générée(s) dans {dossier}.")
        if sans:
            print(f"{len(sans)} plante(s) sans planche (ou marquées « Aucune »), donc ignorées :")
            for nom in sans:
                print(f"   - {nom}")
            print("-> lance d'abord « python3 telecharger_planches.py » pour télécharger les planches manquantes.")
    else:
        dossier = SORTIE / date.isoformat()
        dossier.mkdir(parents=True, exist_ok=True)
        # on privilégie les plantes qui ont une planche ; les autres ne servent que s'il n'y en a aucune
        avec_planche = {pid for pid, c in choix.items() if c and Path(c["fichier"]).exists()}
        du_jour = selection.plantes_du_jour(date, avec_planche)
        if len({p["id"] for p in du_jour}) < 4:      # presque aucune planche : on reprend toutes les plantes
            du_jour = selection.plantes_du_jour(date)
        for heure, p in enumerate(du_jour):
            image_plante(p, choix, date, heure, cfg, tramage, ciel).save(dossier / f"{heure:02d}.png")
            print(f"{heure:02d} h  {p['nom_fr']}")
        print(f"\nImages dans {dossier}")


if __name__ == "__main__":
    main()
