"""Carte des points GPS enregistrés. Dessinée sur le serveur, sans service extérieur."""

from mahh.db import base
from mahh.droits import (
    est_hierarchie,
    exiger_connexion,
    peut_voir_ordures,
    peut_voir_seg,
    peut_voir_snape,
)
from mahh.presentation import page
from mahh.reponse import Interdit
from mahh.texte import echapper

# Cadre par défaut : la Guinée.
CADRE = (7.1, 12.7, -15.1, -7.6)
LARGEUR, HAUTEUR = 900, 640
COUCHES = (
    ("point", "Points de collecte ANASP", "c-point"),
    ("abonne", "Abonnés ordures", "c-abonne"),
    ("seg", "Sites SEG", "c-seg"),
    ("snape", "Forages SNAPE", "c-snape"),
)


def _nombre(valeur):
    try:
        return float(str(valeur).replace(",", "."))
    except (TypeError, ValueError):
        return None


def points_visibles(conn, utilisateur):
    points = []
    if peut_voir_ordures(conn, utilisateur):
        for l in conn.execute("SELECT nom, latitude, longitude FROM point_collecte"):
            points.append(("point", l["nom"], l["latitude"], l["longitude"]))
        for l in conn.execute("SELECT reference, nom, latitude, longitude FROM abonnement"):
            points.append(("abonne", f"{l['reference']} — {l['nom']}", l["latitude"], l["longitude"]))
    for reseau, permis in (("seg", peut_voir_seg(conn, utilisateur)), ("snape", peut_voir_snape(conn, utilisateur))):
        if not permis:
            continue
        for l in conn.execute(
            "SELECT s.nom, s.latitude, s.longitude FROM eau_site s JOIN eau_lieu e ON e.id = s.lieu_id WHERE e.reseau = ?",
            (reseau,),
        ):
            points.append((reseau, l["nom"], l["latitude"], l["longitude"]))
    propres = []
    for genre, nom, lat, lon in points:
        lat, lon = _nombre(lat), _nombre(lon)
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        propres.append((genre, nom, lat, lon))
    return propres


def _cadre(points):
    if not points:
        return CADRE
    lats = [p[2] for p in points]
    lons = [p[3] for p in points]
    marge_lat = max((max(lats) - min(lats)) * 0.1, 0.02)
    marge_lon = max((max(lons) - min(lons)) * 0.1, 0.02)
    return (min(lats) - marge_lat, max(lats) + marge_lat, min(lons) - marge_lon, max(lons) + marge_lon)


def svg(points):
    lat_min, lat_max, lon_min, lon_max = _cadre(points)
    marques = []
    for genre, nom, lat, lon in points:
        x = (lon - lon_min) / (lon_max - lon_min) * LARGEUR
        y = (lat_max - lat) / (lat_max - lat_min) * HAUTEUR
        classe = dict((c[0], c[2]) for c in COUCHES)[genre]
        marques.append(
            f'<circle class="{classe}" cx="{x:.1f}" cy="{y:.1f}" r="7">'
            f"<title>{echapper(nom)} ({lat:.5f}, {lon:.5f})</title></circle>"
        )
    return (
        f'<svg class="carte-svg" viewBox="0 0 {LARGEUR} {HAUTEUR}" role="img" aria-label="Carte des points">'
        f'<rect width="{LARGEUR}" height="{HAUTEUR}" class="carte-fond"/>' + "".join(marques) + "</svg>"
    )


def page_carte(ctx):
    exiger_connexion(ctx)
    with base() as conn:
        u = ctx.utilisateur
        if not (est_hierarchie(u) or peut_voir_ordures(conn, u) or peut_voir_seg(conn, u) or peut_voir_snape(conn, u)):
            raise Interdit("La carte est ouverte à la hiérarchie, au BSD, à l’ANASP, à la SEG et au SNAPE.")
        points = points_visibles(conn, u)
    legende = "".join(
        f'<li><span class="pastille {classe}"></span>{echapper(libelle)} : {sum(1 for p in points if p[0] == genre)}</li>'
        for genre, libelle, classe in COUCHES
    )
    liste = "".join(
        f"<tr><td>{echapper(dict((c[0], c[1]) for c in COUCHES)[g])}</td><td>{echapper(n)}</td>"
        f'<td><a href="https://www.openstreetmap.org/?mlat={la}&amp;mlon={lo}#map=17/{la}/{lo}" '
        f'target="_blank" rel="noopener">{la:.5f}, {lo:.5f}</a></td></tr>'
        for g, n, la, lo in points
    )
    corps = (
        "<h1>Carte</h1>"
        "<p class=\"aide\">Chaque point vient des coordonnées GPS enregistrées. Survolez un point pour son nom ; "
        "le lien de la liste ouvre l’emplacement exact sur OpenStreetMap.</p>"
        f'<ul class="legende">{legende}</ul>'
        + svg(points)
        + (
            "<h2>Liste des points</h2><table><thead><tr><th>Type</th><th>Nom</th><th>GPS</th></tr></thead>"
            f"<tbody>{liste}</tbody></table>"
            if points
            else "<p>Aucun point GPS dans votre vue.</p>"
        )
    )
    return page("Carte", corps, ctx, actif="carte")
