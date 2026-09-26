"""Regenerer le guide des menus a partir de l'application telle qu'elle est.

Le guide etait ecrit a la main, avec des captures collees en base64. Il montrait
donc l'application d'il y a plusieurs versions: un menu « Tribes » qui n'existe
plus depuis que l'organigramme l'a absorbe, et un reporting « en 4 temps » devenu
un parcours en six etapes.

Un guide en images se perime en silence: rien ne previent quand l'ecran change.
Il se regenere donc, en ouvrant vraiment chaque ecran et en le photographiant. Le
texte, lui, reste ecrit ici: c'est le seul endroit ou l'on explique a quoi sert un
menu, et aucune capture ne le dira.

Usage: l'application doit tourner sur http://localhost:8000 avec le compte de
secours. Les modules optionnels sont allumes le temps des captures, puis rendus
dans l'etat ou ils etaient.
"""
import base64
import html
import io
import os
import sys

from playwright.sync_api import sync_playwright

# GUIDE_BASE_URL: a throwaway instance with demo data, never the real organisation.
BASE = os.environ.get("GUIDE_BASE_URL", "http://localhost:8000")
ADMIN = {"email": "admin@local", "password": "changeme-admin"}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "Guide-des-menus.html")

# Chaque entree: le chemin, le titre, ce a quoi elle sert, et de quoi attendre que
# l'ecran soit vraiment peint avant de le photographier.
PAGES = [
    ("/login", "Connexion",
     "Le point d'entree. Selon ce que l'administrateur a configure, on y trouve le "
     "mot de passe, un fournisseur d'identite (OIDC ou SAML), ou les deux, dans "
     "l'ordre choisi. Le compte de secours, lui, passe par un lien discret.",
     "form"),
    ("/prise-en-main", "Prise en main",
     "Un guide adapte a votre role, avec les premieres choses a faire. C'est la "
     "porte d'entree quand on decouvre l'application.", ".card"),
    ("/", "Tableau de bord",
     "La sante de chaque squad d'un coup d'oeil : avancement annuel, jalons bloques "
     "ou a risque, fraicheur du reporting, moral de l'equipe. Une recherche, un tri "
     "en boutons et un choix entre cartes et liste ; l'onglet Steerco consolide les "
     "plateformes et l'onglet Initiatives liste les engagements de la tribe.",
     ".squad-grid-2, .otd-tbl, table"),
    ("/roadmap", "Roadmap",
     "La roadmap consolidee : les quatre trimestres en colonnes, les squads en "
     "lignes, les jalons dans les cases (EA = acces anticipe, GA = disponibilite "
     "generale). On peut chercher, trier, et n'afficher que les squads qui "
     "interessent. Exportable en HTML, image et PowerPoint.", ".rmv"),
    ("/saisie", "Reporting (saisie)",
     "L'ecran ou le squad leader, ses co-leaders et les contributeurs mettent la "
     "squad a jour, etape par etape : les jalons, les engagements OTD de la "
     "squad (ceux du management s'y lisent), les KPI, le commentaire "
     "d'avancement, les messages cles, le moral, le Steerco, puis la soumission "
     "du cycle. Un bandeau rappelle quelle squad et quelle semaine on remplit, "
     "et la barre d'etapes dit ce qui est deja renseigne. L'avancement en "
     "pourcentage ne se saisit pas : il se calcule a partir des jalons termines.", ".step-rail"),
    ("/organigramme", "Organigramme",
     "L'organisation de la tribe, en liste ou en arbre, avec ses squads et leurs "
     "equipes. Les tribes se choisissent dans la barre du haut de l'ecran, avec "
     "leur nombre de squads : c'est ici qu'on les compare, il n'y a plus de menu "
     "separe. Exportable en HTML et PowerPoint.", ".card"),
    ("/squads/{squad}", "Detail d'une squad",
     "Tout ce qu'une squad porte : ses initiatives, ses engagements OTD avec "
     "leur date et leur statut, sa roadmap par trimestre, ses messages cles, les "
     "actions decidees en comite, son budget, son equipe et l'historique de ses "
     "soumissions. Chaque section renvoie vers l'endroit ou elle se modifie ; le "
     "budget n'est visible que par la direction de la squad, son tribe leader et "
     "les admins. Exportable en HTML, image et PowerPoint.", ".otd-tbl, .card"),
    ("/mes-squads", "Mes squads",
     "L'endroit ou une squad se regle. Le tribe leader et l'admin y voient "
     "toutes les squads de leur tribe : fiche, squad leader, co-leaders, "
     "contributeurs, options (KPI, budget), OTD du management, initiatives, "
     "equipe, budget et comites. Un squad leader n'y voit que les squads qu'il "
     "dirige : fiche, contributeurs, ses propres OTD, equipe, budget et comites.", ".card"),
    ("/acces", "Acces",
     "La file des demandes d'acces a valider, et la liste des acces deja en place, "
     "que l'on peut reprendre ou rendre. Reserve aux administrateurs et aux tribe "
     "leaders.", ".card, .banner"),
    ("/admin", "Administration",
     "Quatre familles, dans l'ordre ou l'on se pose les questions en montant une "
     "installation : l'organisation (tribes, squads, plateformes, comptes, "
     "personas, import), les services et l'apparence, la connexion et la "
     "messagerie, puis l'exploitation (audit, journaux, sauvegardes, maintenance).",
     ".admin-nav, nav"),
    ("/preferences", "Preferences",
     "Vos reglages personnels : langue, notifications, mot de passe, et l'abonnement au rapport.", ".card"),
    ("/fil", "Fil",
     "Le fil interne de la tribe : publier une information, un incident ou un "
     "succes, reagir et repondre. Service optionnel, eteint dans une installation "
     "neuve.", ".card"),
    ("/conges", "Conges",
     "Declarer et suivre les absences de l'equipe, avec l'alerte de chevauchement. "
     "Service optionnel, eteint dans une installation neuve.", ".card, table"),
]

OPTIONAL = {"feed": {"enabled": True}, "leaves": {"enabled": True},
            "committees": {"enabled": True}, "steerco": {"enabled": True}}

STYLE = """
  :root { --navy:#1E2761; --ink:#1E293B; --grey:#64748B; --line:#E2E8F0; --bg:#F5F7FA; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:Calibri,Carlito,"Segoe UI",system-ui,sans-serif; line-height:1.5; }
  .hero { background:var(--navy); color:#fff; padding:38px 0; }
  .wrap, main { max-width:1080px; margin:0 auto; padding:0 24px; }
  .hero h1 { margin:0 0 6px; font-size:30px; }
  .hero p { margin:0; color:#CADCFC; }
  main { padding-bottom:48px; }
  .intro { color:var(--grey); margin:26px 0 22px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:14px;
          padding:20px; margin:0 0 22px; }
  .card-head { display:flex; align-items:center; gap:12px; margin-bottom:8px; }
  .num { display:inline-flex; align-items:center; justify-content:center;
         width:28px; height:28px; border-radius:9px; background:var(--navy);
         color:#fff; font-weight:700; font-size:14px; flex:0 0 auto; }
  .card h2 { margin:0; font-size:19px; color:var(--navy); }
  .card p { margin:0 0 14px; color:var(--ink); }
  .card img { width:100%; border:1px solid var(--line); border-radius:10px; display:block; }
  footer { color:var(--grey); font-size:13px; padding:0 24px 40px; max-width:1080px; margin:0 auto; }
"""


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)

        page.goto(f"{BASE}/login")
        page.wait_for_selector("input[type=email]", timeout=20000)
        shots: dict[str, str] = {}
        # La page de connexion se photographie avant d'entrer.
        page.wait_for_timeout(500)
        shots["/login"] = base64.b64encode(page.screenshot()).decode()

        page.fill("input[type=email]", ADMIN["email"])
        page.fill("input[type=password]", ADMIN["password"])
        page.click("button[type=submit]")
        page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
        page.wait_for_timeout(600)
        later = page.query_selector(".modal-overlay button")
        if later:
            later.click()
            page.wait_for_timeout(300)

        # Les services optionnels, allumes le temps des captures et rendus ensuite.
        before = page.evaluate(
            "fetch('/api/admin/modules-config').then(r => r.json())")
        keep = {k: {"enabled": bool(before.get(k, {}).get("enabled"))} for k in OPTIONAL}
        page.evaluate(
            "cfg => fetch('/api/admin/modules-config', {method:'PUT',"
            "headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)})",
            OPTIONAL)
        page.reload()
        page.wait_for_timeout(800)

        squads = page.evaluate("fetch('/api/squads').then(r => r.json())")
        squad_id = squads[0]["id"] if isinstance(squads, list) and squads else None

        try:
            for path, title, _text, wait in PAGES:
                if path == "/login":
                    continue
                url = path.replace("{squad}", str(squad_id)) if "{squad}" in path else path
                if "{squad}" in path and squad_id is None:
                    print(f"  (aucune squad: {path} sans capture)")
                    continue
                page.goto(BASE + url, wait_until="networkidle")
                try:
                    page.wait_for_selector(wait, timeout=8000)
                except Exception:                      # noqa: BLE001
                    print(f"  (pas de {wait} sur {path}, capture quand meme)")
                page.wait_for_timeout(900)
                shots[path] = base64.b64encode(page.screenshot()).decode()
                print(f"  capture {url}")
        finally:
            page.evaluate(
                "cfg => fetch('/api/admin/modules-config', {method:'PUT',"
                "headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)})",
                keep)
            print("  services optionnels rendus a leur etat:",
                  {k: v["enabled"] for k, v in keep.items()})
        b.close()

    cards = []
    for i, (path, title, text, _w) in enumerate(PAGES, 1):
        img = shots.get(path)
        pic = (f'\n      <img src="data:image/png;base64,{img}" alt="{html.escape(title)}"/>'
               if img else "")
        cards.append(
            '    <section class="card">\n'
            f'      <div class="card-head"><span class="num">{i}</span>'
            f'<h2>{html.escape(title)}</h2></div>\n'
            f'      <p>{html.escape(text)}</p>{pic}\n'
            '    </section>')

    doc = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TeamFollowUP - Guide des menus</title>
  <style>{STYLE}</style>
</head>
<body>
  <header class="hero"><div class="wrap">
    <h1>TeamFollowUP - Guide des menus</h1>
    <p>A quoi sert chaque ecran, en quelques lignes.</p>
  </div></header>
  <main>
    <p class="intro">L'application se pilote depuis le menu de gauche. Voici chaque
    menu et son role, avec une capture. Les menus visibles dependent de votre role
    (membre, contributeur, squad leader, tribe leader, admin) et des services actifs : le fil et
    les conges, par exemple, sont eteints dans une installation neuve.</p>
{chr(10).join(cards)}
  </main>
  <footer>TeamFollowUP, guide des menus. Captures prises sur une instance de
  demonstration, regenerees avec <code>scripts/regen-guide</code>.</footer>
</body>
</html>
"""
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(doc)
    print(f"\necrit: {OUT} ({len(doc) // 1024} ko, {len(shots)} captures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
