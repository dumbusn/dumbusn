"""Site public du ministère. Ouvert sans connexion.
Les menus de travail n’apparaissent qu’après la connexion.
Les textes d’actualité viennent des blocs que la cellule de communication rédige."""

from mahh.db import base
from mahh.presentation import page
from mahh.texte import echapper, fmt_date

A_COMPLETER = (
    '<p class="a-completer">Contenu à compléter par la cellule de communication du ministère.</p>'
)

MENU = (
    ("La Guinée", None, (("guinee", "Présentation du pays"), ("institutions", "Institutions de la République"))),
    ("Ministère", None, (
        ("mot-du-ministre", "Mot du Ministre"),
        ("missions", "Missions et attributions"),
        ("organigramme", "Organigramme"),
        ("structures", "Structures rattachées"),
    )),
    ("Actualités", None, (("actualites", "Actualités"), ("communiques", "Communiqués"))),
    ("Projets", None, (("projets", "Projets du ministère"), ("appels-offres", "Appels d’offres"))),
    ("Docs", None, (
        ("textes", "Textes législatifs et réglementaires"),
        ("rapports", "Rapports et publications"),
    )),
    ("Contact", "/p/contact", ()),
    ("Table ronde", "/p/table-ronde", ()),
)


def menu_public(chemin):
    elements = []
    for libelle, lien, sous in MENU:
        actif = " actif" if (lien and chemin == lien) or any(chemin == f"/p/{slug}" for slug, _ in sous) else ""
        if not sous:
            elements.append(f'<li class="menu-item{actif}"><a href="{lien}">{echapper(libelle)}</a></li>')
            continue
        liens = "".join(f'<li><a href="/p/{slug}">{echapper(nom)}</a></li>' for slug, nom in sous)
        elements.append(
            f'<li class="menu-item a-sous{actif}"><a href="/p/{sous[0][0]}" aria-haspopup="true">'
            f'{echapper(libelle)}<span class="chevron" aria-hidden="true">▾</span></a>'
            f'<ul class="sous-menu">{liens}</ul></li>'
        )
    return '<nav class="menu-public" aria-label="Menu public"><ul>' + "".join(elements) + "</ul></nav>"


def _publications(genre):
    with base() as conn:
        lignes = conn.execute(
            "SELECT * FROM bloc_public WHERE genre = ? ORDER BY publie_le DESC, ordre",
            (genre,),
        ).fetchall()
    if not lignes:
        return "<p>Aucune publication pour l’instant. La cellule de communication les rédige.</p>"
    return "".join(
        f'<article class="publication"><p class="meta">{echapper(fmt_date(bloc["publie_le"]))}</p>'
        f'<h3>{echapper(bloc["titre"])}</h3><p>{echapper(bloc["texte"])}</p></article>'
        for bloc in lignes
    )


def _arbre(enfants, parent):
    items = enfants.get(parent, [])
    if not items:
        return ""
    corps = []
    for item in items:
        titre = echapper(item["nom"])
        if item["intitule"]:
            titre += " — " + echapper(item["intitule"])
        corps.append(f"<li><strong>{titre}</strong>{_arbre(enfants, item['id'])}</li>")
    return "<ul>" + "".join(corps) + "</ul>"


def _organigramme():
    with base() as conn:
        lignes = conn.execute(
            "SELECT * FROM organigramme ORDER BY ordre, nom"
        ).fetchall()
    if not lignes:
        return (
            "<p>L’organigramme n’est pas encore publié. "
            "Le ministre, le secrétaire général, le chef de cabinet ou un administrateur "
            "le construit dans l’espace de travail.</p>"
        )
    enfants = {}
    for ligne in lignes:
        enfants.setdefault(ligne["parent_id"], []).append(ligne)
    return (
        "<p>Schéma construit par l’administration. "
        "Les attributions de chaque direction se lisent dans l’espace de travail.</p>"
        + _arbre(enfants, None)
    )


PAGES = {
    "guinee": ("Présentation du pays", lambda: (
        "<p>La République de Guinée est située en Afrique de l’Ouest, sur la façade atlantique. "
        "Sa capitale est Conakry. Le pays compte quatre régions naturelles : la Basse-Guinée, la "
        "Moyenne-Guinée, la Haute-Guinée et la Guinée forestière.</p>" + A_COMPLETER
    )),
    "institutions": ("Institutions de la République", lambda: A_COMPLETER),
    "mot-du-ministre": ("Mot du Ministre", lambda: A_COMPLETER),
    "missions": ("Missions et attributions", lambda: (
        "<p>Le Ministère de l’Assainissement, de l’Hydraulique et des Hydrocarbures conçoit, "
        "met en œuvre et suit la politique du Gouvernement dans trois domaines :</p>"
        "<ul><li><strong>Assainissement</strong> : salubrité publique, gestion des déchets et des eaux usées.</li>"
        "<li><strong>Hydraulique</strong> : accès à l’eau potable en ville (SEG) et en milieu rural (SNAPE).</li>"
        "<li><strong>Hydrocarbures</strong> : approvisionnement, distribution et contrôle des produits pétroliers et du gaz.</li></ul>"
        + A_COMPLETER
    )),
    "organigramme": ("Organigramme", _organigramme),
    "structures": ("Structures rattachées", lambda: (
        "<ul><li><strong>SEG</strong> — Société des Eaux de Guinée : eau potable dans les villes.</li>"
        "<li><strong>SNAPE</strong> — Service national d’aménagement des points d’eau : forages en zone rurale.</li>"
        "<li><strong>ANASP</strong> — Agence nationale d’assainissement et de la salubrité publique : points de collecte des déchets.</li></ul>"
        + A_COMPLETER
    )),
    "actualites": ("Actualités", lambda: _publications("actualite")),
    "communiques": ("Communiqués", lambda: _publications("communique")),
    "projets": ("Projets du ministère", lambda: (
        "<p>Le Bureau de stratégie et de développement suit les projets du ministère. "
        "Le détail de chaque projet est réservé aux agents, dans l’espace de travail.</p>"
        + A_COMPLETER
    )),
    "appels-offres": ("Appels d’offres", lambda: A_COMPLETER),
    "textes": ("Textes législatifs et réglementaires", lambda: A_COMPLETER),
    "rapports": ("Rapports et publications", lambda: A_COMPLETER),
    "contact": ("Contact", lambda: (
        "<p>Ministère de l’Assainissement, de l’Hydraulique et des Hydrocarbures — "
        "Conakry, République de Guinée.</p>" + A_COMPLETER
    )),
    "table-ronde": ("Table ronde", lambda: A_COMPLETER),
}


def page_publique(ctx, slug):
    if slug not in PAGES:
        from mahh.presentation import page_message

        return page_message(ctx, "Introuvable", "Cette page n’existe pas.", 404)
    titre, contenu = PAGES[slug]
    corps = (
        f'<div class="fil"><a href="/">Accueil</a> › {echapper(titre)}</div>'
        f"<h1>{echapper(titre)}</h1>" + contenu()
    )
    return page(titre, corps, ctx)


def accueil_public(ctx):
    with base() as conn:
        actus = conn.execute(
            """
            SELECT * FROM bloc_public
            WHERE genre IN ('actualite', 'communique')
            ORDER BY publie_le DESC LIMIT 3
            """
        ).fetchall()
        presentation = conn.execute(
            "SELECT * FROM bloc_public WHERE genre = 'presentation' ORDER BY ordre LIMIT 1"
        ).fetchone()
    if actus:
        cartes = "".join(
            f'<article class="actu"><p class="meta">{echapper(fmt_date(bloc["publie_le"]))}</p>'
            f'<h3>{echapper(bloc["titre"])}</h3>'
            f'<p>{echapper(bloc["texte"][:220])}{"…" if len(bloc["texte"]) > 220 else ""}</p></article>'
            for bloc in actus
        )
    else:
        cartes = "<p>Aucune actualité publiée. La cellule de communication les rédige.</p>"
    if presentation:
        intro = echapper(presentation["texte"])
    else:
        intro = (
            "Le ministère conçoit et conduit la politique du Gouvernement en matière "
            "d’assainissement, d’eau potable et d’hydrocarbures."
        )
    return f"""
<section class="heros">
  <div class="heros-texte">
    <p class="heros-sur">République de Guinée</p>
    <h1>Accueil</h1>
    <p class="heros-titre">Ministère de l’Assainissement, de l’Hydraulique et des Hydrocarbures</p>
    <p>{intro}</p>
    <p><a class="bouton" href="/p/missions">Nos missions</a>
       <a class="bouton secondaire" href="/connexion">Espace agents — se connecter</a></p>
  </div>
</section>
<section class="trois-domaines">
  <a class="domaine-carte d-ass" href="/p/missions"><h2>Assainissement</h2><p>Salubrité publique, collecte des déchets, eaux usées.</p></a>
  <a class="domaine-carte d-hyd" href="/p/structures"><h2>Hydraulique</h2><p>Eau potable en ville avec la SEG, en zone rurale avec le SNAPE.</p></a>
  <a class="domaine-carte d-hyc" href="/p/missions"><h2>Hydrocarbures</h2><p>Approvisionnement et distribution des produits pétroliers et du gaz.</p></a>
</section>
<section class="bloc-actus">
  <h2>Dernières actualités</h2>
  <div class="actus">{cartes}</div>
  <p><a href="/p/actualites">Toutes les actualités</a> · <a href="/p/communiques">Communiqués</a></p>
</section>
"""
