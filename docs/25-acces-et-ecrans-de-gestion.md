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

Les reglages d'une squad se decidaient a trois endroits : « Mes squads »
pour son identite et son budget, Administration > Squads pour ses KPI et ses
objectifs annuels, et nulle part pour son rattachement steerco, qu'il fallait
aller chercher dans l'ecran des plateformes.

Le menu d'une squad (Mes squads) tient maintenant en six etapes, qui repondent
chacune a une question. Mise a jour de la [31](31-coherence-saisie-et-reporting.md) :
les objectifs annuels ont ete retires, l'OTD est le seul engagement.

| Etape | La question |
|---|---|
| Infos | qui est cette squad (nom, tribe, squad leader, co-leaders, contributeurs, description, ordre, produits, materiel) |
| Options | ce qu'elle suit (KPI, budget) |
| OTD | les engagements du management, et les initiatives qu'elle mene |
| Equipe | ses membres |
| Budget | les montants, quand le suivi est actif |
| Comites | ses comites recurrents |

Un squad leader ouvre la meme fenetre sur les squads qu'il dirige, sans Options ni
choix du squad leader : fiche, contributeurs, ses propres OTD, equipe, budget,
comites.

Le panneau « Parametres » d'Administration > Squads a disparu : il proposait
l'interrupteur KPI et les objectifs annuels (retires depuis). Deux
endroits pour le meme reglage, c'est un endroit de trop : celui qu'on ne pense pas
a ouvrir finit par afficher l'ancien etat.

Les **OTD du management** s'ecrivent a l'etape OTD de Mes squads, par le tribe
leader ou l'admin. Ceux de la squad s'ecrivent dans la saisie, par son leader, ses
co-leaders et ses contributeurs. Les « objectifs annuels » qui vivaient a l'etape
Options ont ete retires, et le chiffre « objectifs rouges » de la synthese est
devenu « OTD en retard ».

Le **type de squad** a quitte l'etape Infos. Il annonce un style de reporting que
rien ne lit (voir [03](03-data-model.md)) : la colonne reste en base et l'import
la remplit toujours, mais un reglage inerte a l'ecran fait douter de tous les
autres.

**Le steerco ne s'active pas, il se deduit.** Une squad est au steerco parce
qu'elle alimente une plateforme (`app/platforms.py`, `sync_squad_flags`). Les
plateformes qu'une squad alimente se reglent dans Administration > Plateformes et
Steerco ; Mes squads y renvoie. Un interrupteur existe quand meme, parce qu'il fallait une facon de
dire « plus de steerco ici » sans retirer les plateformes une par une : l'eteindre
retire la squad de toutes celles qu'elle alimente, et c'est ecrit a cote. Il ne
peut pas s'allumer seul, puisque l'allumer sans choisir de plateforme ne voudrait
rien dire.

**Les initiatives** sont a l'etape OTD, avec les engagements : l'etape montre
exactement ce que la frise exportee montre, et dans son ordre. En haut de la frise,
les engagements dates. En dessous, une ligne par initiative portant les jalons qui
la servent. L'etape se lit donc comme le document qu'elle produit.

Chaque initiative menee par la squad **coche les jalons qui la servent**, du meme
geste que les jalons d'un engagement : c'est la meme question posee a deux niveaux,
elle merite le meme geste. Un jalon deja pris par une autre initiative se voit,
grise : le cacher laisserait croire qu'il n'existe pas.

**Les engagements OTD** se lisent en tableau : engagement, date, statut, jalons
couverts. Une carte par engagement, avec sa liste de jalons repliee dedans, tenait
sur deux engagements ; a sept, la page defilait sans qu'on puisse comparer deux
dates, alors que comparer des dates est ce qu'on vient faire ici. Le meme panneau
sert a trois endroits : la page de la squad, « Mes squads », et l'etape
Engagements du reporting. Il avait quitte le reporting quand personne ne pouvait
l'y ecrire ; la portee squad a change cela, et il y est revenu pour elle (voir
[27 - Le parcours de reporting](27-parcours-de-reporting-et-listes.md)).

Le tableau ne montre que les engagements qui concernent la squad. Le bloc replie
des « autres engagements de la tribu », qui les repetait tous sous chaque squad,
a ete retire : dans la saisie d'une squad il n'avait pas sa place. L'API continue
de les envoyer a un squad leader (en lecture), rien n'est cache.

**Les cartes de la page d'une squad se plient**, toutes, du meme geste que
l'equipe et l'historique qui le faisaient deja : on clique l'en-tete, le chevron
tourne. Une page de squad empile une dizaine de cartes, et on n'en regarde que
deux a la fois. Elles s'ouvrent par defaut, a la difference de l'equipe et de
l'historique : une page dont toutes les cartes seraient fermees ne montrerait plus
rien de ce qu'on vient y voir. Pliee, chaque carte garde son titre et un compte de
ce qu'elle contient, pour qu'on sache s'il vaut la peine de l'ouvrir.

**Les co-leaders** passent de cases a cocher a une liste deroulante. Une
rangee de cases tenait sur trois personnes et se deformait a dix : elle
s'enroulait sur plusieurs lignes de hauteur variable, et le champ ne s'alignait
plus sur ceux du dessus. Une liste a la hauteur d'un champ et ne grandit pas avec
le nombre de comptes.

## 3. Le moral se declare la ou l'on rend compte

Il etait saisissable sur la seule page de la squad, qui est un ecran de lecture.
Celui qui le connait est celui qui remplit son reporting : la question se pose
donc dans l'ecran de saisie, juste apres les messages cles, parce qu'elle prend une
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

## 7. L'equipe se gere la ou on la voit

La fiche squad disait « Ajoutez-les depuis le reporting », alors que le reporting
n'a jamais porte les membres. Un seul editeur d'equipe (`TeamEditor`) s'ouvre
desormais depuis trois endroits : la carte Equipe de la page squad, le bouton
« Modifier l'equipe » de chaque squad dans l'organigramme (arbre et liste) et
« Mes squads ». Le bouton n'apparait que
pour ceux que le serveur autorise (`deps.can_edit_squad`) : admin, tribe leader
de la tribu, leader et co-leaders. « Mes squads » ne listait que les squads dont
on est le leader nomme : un co-leader n'y voyait pas la sienne.

Le serveur verifie aussi le rattachement : le manager d'un membre appartient a la
meme squad et la chaine ne boucle pas (422 sinon). Supprimer un manager detache
ceux qui lui etaient rattaches, au lieu d'echouer sur la cle etrangere.

Le nom d'un membre et celui d'une squad sont obligatoires (1 a 255 caracteres) :
un champ vide renvoie 422, et un `null` explicite sur une colonne obligatoire de
la squad (nom, ordre, interrupteurs KPI ou budget) aussi, au lieu d'un 500 au
moment de l'ecriture en base.

**Un membre est relie a son compte par son email.** Le lien `members.user_id`
existait, mais aucun ecran ne le posait : un membre ajoute n'etait qu'un nom, alors
que ce lien decide qui valide ses conges et qui recoit les rapports de la squad.
On ajoute desormais quelqu'un par son email, prenom et nom facultatifs (a defaut,
le nom du compte, sinon celui qu'on lit dans l'email). Les comptes actifs de la
tribu sont proposes pendant la saisie (`GET /api/members/candidates`). Si un compte
de la tribu porte cet email, le lien est fait tout de suite ; sinon il se fait seul
des que le compte apparait : a la connexion, a sa creation par un admin, a la
validation de sa demande d'acces (`app/memberlink.py`). Chaque ligne de l'equipe
dit ou elle en est : compte relie, pas encore de compte, ou sans email.

Le lien ne traverse jamais une tribu : etre membre d'une squad donne a son leader
la main sur ses conges, et relier le compte d'une autre tribu le permettrait a qui
connait une adresse. L'email d'un compte d'une autre tribu est refuse (409), et un
compte qui change de tribu perd les liens qu'il avait dans l'ancienne. Une meme
personne n'apparait qu'une fois par squad (409).

## Ou est le code

| Role | Fichier |
|---|---|
| Revoquer, retablir, lister les comptes geres | `backend/app/access.py`, `backend/app/routers/access.py` |
| L'ecran des acces | `frontend/src/pages/AccessRequestsPage.tsx` |
| Le menu d'une squad, en quatre etapes | `frontend/src/pages/MySquadsPage.tsx` |
| Le tri et la vue liste du tableau de bord | `frontend/src/pages/DashboardPage.tsx` |
| L'etat vide de l'organigramme | `frontend/src/pages/OrgPage.tsx` |
| L'interrupteur de l'avancement trimestriel | `backend/app/modulesconfig.py` |
| L'editeur d'equipe partage | `frontend/src/components/TeamModal.tsx`, `backend/app/routers/members.py` |
| Le lien membre et compte | `backend/app/memberlink.py`, migration `0036_member_email` |
| Tests | `backend/tests/test_members.py`, `backend/tests/test_access_revoke.py`, `backend/tests/test_api_ui_parity.py` |
