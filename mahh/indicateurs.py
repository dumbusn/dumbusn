"""Indicateurs d’assainissement. Les comptes viennent des enregistrements, pas d’un chiffre posé."""

from decimal import Decimal
from urllib.parse import urlencode

from mahh.db import base
from mahh.decoupage import GENRES, PARENT, ancre, libelle_maille, options, selection
from mahh.droits import est_hierarchie, nom_structure
from mahh.presentation import jeton_cache
from mahh.reponse import Redirection, ValeurRefusee
from mahh.securite import maintenant
from mahh.texte import echapper, fmt_pourcent
from mahh.validation import ligne

_LIBELLES = dict(GENRES)

LIBELLES = (
    "Nombre de ZTT",
    "Nombre et liste de PME /zone",
    "Nombre d’abonnée/préfecture",
    "Taux de couverture/préfecture",
)


def peut_creer_ztt(conn, utilisateur):
    if est_hierarchie(utilisateur):
        return True
    return nom_structure(conn, utilisateur) == "DGA"


def rendu(ctx, conn, retour):
    choisi = selection(conn, ctx.requete)
    identifiant = ancre(choisi)
    comptes = _compter(conn, identifiant)
    adresse = retour
    if choisi:
        adresse = retour + "?" + urlencode({cle: str(valeur) for cle, valeur in choisi.items()})
    return (
        '<section class="indicateurs-assainissement" data-indicateurs="assainissement">'
        "<h2>Indicateurs d’assainissement</h2>"
        "<p class=\"chapeau\">Zones de traitement et de tri, PME et abonnés du découpage officiel. "
        "Le nombre affiché est le nombre enregistré. Choisir une région, puis une préfecture ou une "
        "commune, une sous-préfecture, jusqu’au secteur.</p>"
        + _filtres(retour, conn, choisi)
        + _cartes(comptes)
        + _liste_ztt(comptes["ztt"])
        + _liste_pme(comptes["pme"])
        + _enfants(conn, identifiant, choisi)
        + _forme_ztt(ctx, conn, identifiant, adresse)
        + "</section>"
    )


def action_ztt(ctx):
    from mahh.droits import exiger_connexion
    from mahh.reponse import Interdit

    exiger_connexion(ctx)
    with base() as conn:
        if not peut_creer_ztt(conn, ctx.utilisateur):
            raise Interdit("Les zones de traitement et de tri sont créées par la direction de l’assainissement.")
        try:
            nom = ligne(ctx.formulaire.get("nom"), 2, 120, "Nom")
            maille_id = int(ctx.formulaire.get("maille_id") or "0")
        except (ValeurRefusee, ValueError):
            message = "Le nom et le rattachement sont requis."
            return _retour_erreur(ctx, message)
        maille = conn.execute("SELECT id FROM maille WHERE id = ?", (maille_id,)).fetchone()
        if maille is None:
            return _retour_erreur(ctx, "Choisissez un niveau du découpage officiel.")
        conn.execute(
            "INSERT INTO ztt (nom, maille_id, cree_par, cree_le) VALUES (?, ?, ?, ?)",
            (nom, maille_id, ctx.utilisateur["id"], maintenant()),
        )
    return Redirection(_adresse(ctx, "ztt-creee"))


def _retour_erreur(ctx, message):
    from mahh.presentation import page

    return page("Indicateurs", f"<h1>Indicateurs</h1><p class=\"alerte\">{echapper(message)}</p>", ctx, statut=400)


def _adresse(ctx, message):
    from mahh.securite import url_sure

    retour = url_sure(ctx.formulaire.get("retour") or "/ordures")
    separateur = "&" if "?" in retour else "?"
    return f"{retour}{separateur}message={message}"


def _compter(conn, maille_id):
    if maille_id is None:
        prefixe = ""
        params = ()
        sous = "SELECT id FROM maille"
    else:
        prefixe = """
            WITH RECURSIVE sous(id) AS (
                SELECT id FROM maille WHERE id = ?
                UNION ALL
                SELECT m.id FROM maille m JOIN sous s ON m.parent_id = s.id
            )
        """
        params = (maille_id,)
        sous = "SELECT id FROM sous"
    ztt = conn.execute(
        prefixe + f" SELECT nom FROM ztt WHERE maille_id IN ({sous}) ORDER BY nom",
        params,
    ).fetchall()
    pme = conn.execute(
        prefixe + f"""
        SELECT DISTINCT p.nom FROM pme p
        JOIN pme_secteur ps ON ps.pme_id = p.id
        WHERE ps.secteur_id IN ({sous})
        ORDER BY p.nom
        """,
        params,
    ).fetchall()
    abonnes = conn.execute(
        prefixe + f" SELECT COUNT(*) AS n FROM abonnement WHERE secteur_id IN ({sous})",
        params,
    ).fetchone()["n"]
    secteurs = conn.execute(
        prefixe + f" SELECT COUNT(*) AS n FROM maille WHERE genre = 'secteur' AND id IN ({sous})",
        params,
    ).fetchone()["n"]
    couverts = conn.execute(
        prefixe + f" SELECT COUNT(DISTINCT secteur_id) AS n FROM abonnement WHERE secteur_id IN ({sous})",
        params,
    ).fetchone()["n"]
    if secteurs:
        taux = Decimal(couverts) / Decimal(secteurs)
    else:
        taux = None
    return {
        "ztt": [ligne["nom"] for ligne in ztt],
        "pme": [ligne["nom"] for ligne in pme],
        "abonnes": abonnes,
        "taux": taux,
    }


def _cartes(comptes):
    taux = fmt_pourcent(comptes["taux"])
    return (
        '<div class="cartes">'
        f'<article class="carte" data-indicateur="ztt" data-nombre="{len(comptes["ztt"])}">'
        "<h3>Nombre de ZTT</h3>"
        f"<p>{len(comptes['ztt'])}</p></article>"
        f'<article class="carte" data-indicateur="pme" data-nombre="{len(comptes["pme"])}">'
        "<h3>Nombre et liste des PME / zone</h3>"
        f"<p>{len(comptes['pme'])}</p></article>"
        f'<article class="carte" data-indicateur="abonnes" data-nombre="{comptes["abonnes"]}">'
        "<h3>Nombre d’abonnés / préfecture</h3>"
        f"<p>{comptes['abonnes']}</p></article>"
        '<article class="carte" data-indicateur="couverture">'
        "<h3>Taux de couverture / préfecture</h3>"
        f"<p>{echapper(taux)}</p>"
        "<p class=\"aide\">Part des secteurs ou villages du découpage qui ont au moins un abonné.</p>"
        "</article></div>"
    )


def _liste_ztt(noms):
    if not noms:
        return "<h3>Zones de traitement et de tri</h3><p>Aucune zone enregistrée dans cette vue.</p>"
    items = "".join(f"<li>{echapper(nom)}</li>" for nom in noms)
    return f"<h3>Zones de traitement et de tri</h3><ul>{items}</ul>"


def _liste_pme(noms):
    if not noms:
        return "<h3>PME</h3><p>Aucune PME enregistrée dans cette vue.</p>"
    items = "".join(f"<li>{echapper(nom)}</li>" for nom in noms)
    return f"<h3>PME</h3><ul>{items}</ul>"


def _enfants(conn, maille_id, choisi):
    if maille_id is None:
        genre = "region"
        parent = None
    else:
        ligne = conn.execute("SELECT genre FROM maille WHERE id = ?", (maille_id,)).fetchone()
        suivant = None
        vu = False
        for cle, _libelle in GENRES:
            if vu:
                suivant = cle
                break
            if cle == ligne["genre"]:
                vu = True
        if suivant is None:
            return ""
        genre = suivant
        parent = maille_id
    lignes = options(conn, genre, parent)
    if not lignes:
        return ""
    rangs = []
    for enfant in lignes:
        comptes = _compter(conn, enfant["id"])
        rangs.append(
            "<tr>"
            f"<td>{echapper(libelle_maille(enfant))}</td>"
            f"<td>{len(comptes['ztt'])}</td>"
            f"<td>{len(comptes['pme'])}</td>"
            f"<td>{comptes['abonnes']}</td>"
            f"<td>{echapper(fmt_pourcent(comptes['taux']))}</td>"
            "</tr>"
        )
    titre = _LIBELLES[genre]
    return (
        f"<h3>{echapper(titre)}</h3>"
        "<table><thead><tr><th>Nom</th><th>ZTT</th><th>PME</th><th>Abonnés</th><th>Couverture</th></tr></thead>"
        f"<tbody>{''.join(rangs)}</tbody></table>"
    )


def _filtres(retour, conn, choisi):
    selects = []
    for genre, libelle in GENRES:
        parent_cle = PARENT.get(genre)
        parent_id = choisi.get(parent_cle) if parent_cle else None
        if genre != "region" and parent_id is None:
            break
        lignes = options(conn, genre, parent_id)
        if not lignes and genre not in choisi:
            break
        options_html = ['<option value="">Tous</option>']
        for ligne in lignes:
            sel = " selected" if ligne["id"] == choisi.get(genre) else ""
            options_html.append(
                f'<option value="{int(ligne["id"])}"{sel}>{echapper(libelle_maille(ligne))}</option>'
            )
        selects.append(
            f'<label for="filtre-{genre}">{echapper(libelle)}</label>'
            f'<select id="filtre-{genre}" name="{genre}">{"".join(options_html)}</select>'
        )
    return (
        f'<form method="get" action="{echapper(retour)}" class="formulaire" data-decoupage="1">'
        + "".join(selects)
        + '<button type="submit">Afficher ce découpage</button></form>'
    )


def _forme_ztt(ctx, conn, maille_id, retour):
    if not peut_creer_ztt(conn, ctx.utilisateur):
        return (
            "<p>La direction de l’assainissement crée les zones de traitement et de tri. "
            "L’ANASP crée les PME. Les abonnés sont enregistrés dans l’application.</p>"
        )
    if maille_id is None:
        return (
            "<p>Choisissez d’abord un niveau du découpage, puis enregistrez la zone de traitement et de tri.</p>"
        )
    return (
        "<h3>Nouvelle zone de traitement et de tri</h3>"
        '<form method="post" action="/ordures/ztt" class="formulaire">'
        + jeton_cache(ctx)
        + f'<input type="hidden" name="retour" value="{echapper(retour)}">'
        + f'<input type="hidden" name="maille_id" value="{int(maille_id)}">'
        + '<label for="nom-ztt">Nom</label>'
        + '<input id="nom-ztt" name="nom" required maxlength="120">'
        + '<button type="submit">Enregistrer la zone</button></form>'
    )

