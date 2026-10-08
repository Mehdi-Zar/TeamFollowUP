# ADR 0017 - Les modèles pilotent les renderers, et l'aperçu lit le deck

Statut : accepté (3.0.0). Prolonge l'ADR 0008 (rendu des rapports côté serveur).

## Contexte

Chaque export PowerPoint était un programme : six renderers écrits à la main, dont
toute la mise en page (position, ordre, contenu) était figée dans le code, sur un
seul gabarit `.pptx` global. Les équipes voulaient des formats différents par
tribe, squad ou plateforme, réglables dans l'application, avec un aperçu.

## Options examinées

1. **Des options sur les renderers** (cases à cocher). Rapide, mais ni ordre des
   slides, ni formats par portée, ni aperçu.
2. **Un PowerPoint à trous** conçu dans PowerPoint, rempli par jetons. Aucune
   visualisation calculée (frise, couloirs, graphiques à deux échelles) n'y est
   exprimable, pas d'aperçu dans l'application.
3. **Un moteur générique** réécrit de zéro (scène de primitives, deux écrivains).
   Il aurait fallu réécrire des centaines de règles d'ajustement fines, documentées
   dans les renderers, au risque de perdre la qualité acquise.
4. **Découper les renderers existants en sections et en blocs**, pilotés par une
   spécification, et lire le deck produit pour l'aperçu.

## Décision

Option 4, avec l'option 2 comme bloc (« slide PowerPoint importée »).

- Les renderers deviennent des constructeurs de sections (`report_deck`,
  `roadmap_deck`, `steerco_deck`...) dont chaque partie est un bloc, dessinable dans
  un cadre quelconque. Dans le cadre d'origine, ils produisent le même XML qu'avant ;
  le modèle Standard le garantit et un test le vérifie.
- L'aperçu ne recalcule rien : il lit le `Presentation` que l'export enregistrerait
  et l'écrit en HTML positionné. Fidèle par construction, sans LibreOffice.
- Un modèle dérivé stocke ses écarts (patch par identifiants), et le parent peut
  verrouiller des parties : la règle d'héritage est pure (`exportspec`), testée à
  part de la base.

## Conséquences

- Rien ne change pour qui ne touche pas au Studio.
- Une évolution d'un renderer se fait toujours dans le renderer ; elle profite à
  tous les modèles qui l'utilisent.
- Le texte de l'aperçu est mis en page par le navigateur : une ligne peut couper
  un mot plus tôt que PowerPoint. Accepté, et dit dans l'écran.
- Le harnais « scène contre scène » de la proposition est remplacé par la
  comparaison du XML des slides, Standard contre rendu d'origine.
