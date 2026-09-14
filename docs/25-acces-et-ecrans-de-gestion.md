# 25 - Les acces, et les ecrans qui gerent une squad

Six corrections tirees d'un meme constat : plusieurs ecrans savaient poser une
question mais pas revenir sur la reponse.

## 1. Un acces se reprend, et se rend

L'ecran des acces ne montrait que la file d'attente. Une fois la demande traitee
le compte en sortait, et plus rien ne permettait d'y revenir : cote serveur,
valider refusait tout ce qui n'etait pas « en attente », si bien qu'un compte
revoque restait revoque pour toujours. Un droit d'acces qui ne se defait pas
n'est pas un droit.

Trois changements :

- **« Acces en place »**, sous la file d'attente : les comptes deja decides, avec
  leur etat, de quoi chercher, et les deux gestes qui vont avec. Cette liste
  repond a « qui a acces », qui est la question du lendemain, alors que la file
  ne repond qu'a « que reste-t-il a faire ».
- **Retablir** un acces revoque emprunte le formulaire de validation, parce que
  c'est la meme decision : un role, une tribu, une squad. Le journal distingue
  les deux (`from: disabled`), car « valide » et « retabli » ne racontent pas la
  meme histoire.
- **Revoquer** devient un geste ordinaire, donc encadre : on ne se revoque pas
  soi-meme, on ne revoque pas le dernier administrateur actif, un tribe leader
  ne revoque ni un administrateur ni quelqu'un d'une autre tribu. Ce dernier
  point etait un trou : l'ecran ne le proposait pas, l'API l'acceptait.

**Qui relit les acces.** Admin et tribe leader, et eux seuls. Un squad leader
validait autrefois un compte dans une de ses squads sans pouvoir ni le revoquer
ni le retablir : une file ou l'on ne peut qu'ajouter. Accorder l'entree dans
l'application n'est pas composer une equipe.

Le compte de secours n'apparait pas dans la liste et ne se revoque pas : c'est la
porte qui reste ouverte quand les autres se referment. Il compte en revanche
comme administrateur actif, sinon revoquer un administrateur compromis serait
impossible dans une installation qui n'en a qu'un, ce qui est exactement la
situation ou il faut pouvoir le faire.

## 2. Tout ce qui concerne une squad, au meme endroit

Les reglages d'une squad se decidaient a trois endroits : « Gerer mes squads »
pour son identite et son budget, Administration > Squads pour ses KPI et ses
objectifs annuels, et nulle part pour son rattachement steerco, qu'il fallait
aller chercher dans l'ecran des plateformes.

Le menu d'une squad tient maintenant en quatre etapes, qui repondent chacune a
une question :

| Etape | La question |
|---|---|
| Infos | qui est cette squad (nom, tribu, responsable, co-responsables, description, ordre, produits, materiel) |
| Options | ce qu'elle suit (KPI, budget, plateformes steerco) |
| OTD | ce sur quoi elle s'engage pour l'annee |
| Budget | les montants, quand le suivi est actif |

Le panneau « Parametres » d'Administration > Squads a disparu : il proposait
l'interrupteur KPI et les objectifs annuels, qui vivent ici tous les deux. Deux
endroits pour le meme reglage, c'est un endroit de trop : celui qu'on ne pense pas
a ouvrir finit par afficher l'ancien etat.

Les **OTD de l'annee** se sont longtemps ecrits dans l'ecran de saisie, a cote des
jalons qu'ils portent. C'etait le mauvais ecran : seuls un tribe leader ou un
admin peuvent les ecrire, et un tribe leader n'entre pas dans la saisie, si bien
qu'un admin etait en pratique le seul a pouvoir en creer un. Ils sont a l'etape
OTD, sous les engagements qu'ils servent.

Le **type de squad** a quitte l'etape Infos. Il annonce un style de reporting que
rien ne lit (voir [03](03-data-model.md)) : la colonne reste en base et l'import
la remplit toujours, mais un reglage inerte a l'ecran fait douter de tous les
autres.

**Le steerco ne s'active pas, il se deduit.** Une squad est au steerco parce
qu'elle alimente une plateforme (`app/platforms.py`, `sync_squad_flags`). Le menu
montre donc les plateformes et laisse choisir celles que la squad alimente ;
l'etat suit. Un interrupteur existe quand meme, parce qu'il fallait une facon de
dire « plus de steerco ici » sans retirer les plateformes une par une : l'eteindre
retire la squad de toutes celles qu'elle alimente, et c'est ecrit a cote. Il ne
peut pas s'allumer seul, puisque l'allumer sans choisir de plateforme ne voudrait
rien dire.

**Les initiatives** sont dans la meme etape : une initiative appartient a la tribu
et designe la squad qui la mene, et ce sont elles qui remplissent ses lignes dans
les documents. Se regler ailleurs qu'ici n'avait pas de raison.

**Les engagements OTD** se lisent en tableau : engagement, date, statut, jalons
couverts. Une carte par engagement, avec sa liste de jalons repliee dedans, tenait
sur deux engagements ; a sept, la page defilait sans qu'on puisse comparer deux
dates, alors que comparer des dates est ce qu'on vient faire ici. Le meme panneau
sert sur la page de la squad et dans « Gerer mes squads ». Il a quitte le
reporting, ou personne ne pouvait l'ecrire.

**Les co-responsables** passent de cases a cocher a une liste deroulante. Une
rangee de cases tenait sur trois personnes et se deformait a dix : elle
s'enroulait sur plusieurs lignes de hauteur variable, et le champ ne s'alignait
plus sur ceux du dessus. Une liste a la hauteur d'un champ et ne grandit pas avec
le nombre de comptes.

## 3. Le moral se declare la ou l'on rend compte

Il etait saisissable sur la seule page de la squad, qui est un ecran de lecture.
Celui qui le connait est celui qui remplit son reporting : la question se pose
donc en tete de l'ecran de saisie, avant les jalons, parce qu'elle prend une
seconde et qu'elle explique souvent tout le reste. Elle reste visible sur la page
de la squad et sur les cartes du tableau de bord, et part dans les exports
(voir [24](24-exports-frise-annuelle-et-moral.md)).

## 4. Le tableau de bord se trie

Le tri existait, cache dans la quatrieme liste deroulante d'une rangee de cinq :
personne ne le trouvait. Il devient une rangee de boutons, risque, avancement,
nom, fraicheur. Le critere actif porte une fleche et la retourne quand on le
reclique, ce que tout tableau apprend a faire.

A cote, une **vue liste** : une grille de cartes se lit bien a dix squads et se
parcourt mal a quarante, ou la question devient « ou est la mienne ». Les
colonnes sont celles sur lesquelles on trie, pour qu'un tri se voie.

Le tri, son sens et la densite sont retenus d'une visite a l'autre, dans le
navigateur de celui qui regarde : ce sont ses preferences de lecture, elles ne
concernent que lui. Un bouton « reinitialiser » apparait des qu'un filtre est
pose.

## 5. Un organigramme vide qui ne dit pas pourquoi

Une tribu avec onze squads affichait un organigramme vide et s'arretait la : rien
n'indiquait que les squads existaient deja ailleurs, ni comment les y faire
entrer, et la seule porte etait « ajouter un noeud », qui demande de retaper une
a une des donnees que l'application connait.

L'etat vide compte donc ce qui manque et propose de le poser : **« Partir de mes
squads »** cree une racine au nom de la tribu et une boite par squad. C'est le
point de depart que tout le monde recree a la main, en moins bien.

## 6. L'avancement trimestriel, mis en sommeil

La section n'etait pas jugee prete. Elle n'est ni supprimee ni commentee : elle
devient un interrupteur de module, eteint par defaut, visible et rallumable dans
Administration > Modules (`squad_content.quarter_progress`), comme les KPI qui
sont dans le meme cas. La route qui l'alimente est gardee par le meme
interrupteur, sinon l'API repondrait a un ecran qui n'existe plus.

## Ou est le code

| Role | Fichier |
|---|---|
| Revoquer, retablir, lister les comptes geres | `backend/app/access.py`, `backend/app/routers/access.py` |
| L'ecran des acces | `frontend/src/pages/AccessRequestsPage.tsx` |
| Le menu d'une squad, en quatre etapes | `frontend/src/pages/MySquadsPage.tsx` |
| Le tri et la vue liste du tableau de bord | `frontend/src/pages/DashboardPage.tsx` |
| L'etat vide de l'organigramme | `frontend/src/pages/OrgPage.tsx` |
| L'interrupteur de l'avancement trimestriel | `backend/app/modulesconfig.py` |
| Tests | `backend/tests/test_access_revoke.py`, `backend/tests/test_api_ui_parity.py` |
