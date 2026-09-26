"""English wording of the error messages the routes raise in French.

Routes write ``HTTPException(detail="...")`` in French, the app's default
language. When the client asks for English (the SPA sends ``Accept-Language``),
the handler in ``errors.py`` looks the detail up here: an exact match in ``EN``
first, then the ``PATTERNS`` for messages built with values (names, numbers,
the text of an underlying error). Anything not found is sent unchanged.

Machine-readable codes such as ``access_pending`` / ``access_disabled`` are not
listed: the SPA reads them as they are.

``tests/test_errmsgs.py`` checks that every literal French detail in ``app/``
has an entry, so a new message cannot be forgotten.
"""
import re

EN: dict[str, str] = {
    # Not found
    "Absence introuvable": "Leave not found",
    "Clé introuvable": "Key not found",
    "Comité introuvable": "Committee not found",
    "Compte administrateur introuvable": "Administrator account not found",
    "Compte introuvable dans cette tribe": "Account not found in this tribe",
    "Demande introuvable": "Request not found",
    "Initiative introuvable": "Initiative not found",
    "Jalon introuvable": "Milestone not found",
    "KPI introuvable": "KPI not found",
    "Membre introuvable": "Member not found",
    "Message introuvable": "Message not found",
    "Notification introuvable": "Notification not found",
    "Nœud introuvable": "Node not found",
    "OTD introuvable": "OTD not found",
    "Plateforme introuvable": "Platform not found",
    "Réponse introuvable": "Reply not found",
    "Sauvegarde introuvable": "Backup not found",
    "Snapshot introuvable": "Snapshot not found",
    "Squad de dépendance introuvable": "Dependency squad not found",
    "Squad introuvable": "Squad not found",
    "Tribe de dépendance introuvable": "Dependency tribe not found",
    "Tribe introuvable": "Tribe not found",
    "Type d'absence introuvable": "Leave type not found",
    "Utilisateur (tribe leader) introuvable": "User (tribe leader) not found",
    "Utilisateur introuvable": "User not found",
    "Persona inconnu": "Unknown persona",
    "Porteur inconnu": "Unknown owner",

    # Authentication and sessions
    "Non authentifié": "Not signed in",
    "Session invalide": "Invalid session",
    "Identifiants invalides": "Invalid credentials",
    "Trop de tentatives de connexion. Réessayez plus tard.": "Too many sign-in attempts. Try again later.",
    "Clé d'API invalide, expirée ou révoquée": "API key is invalid, expired or revoked",
    "Authentification SAML refusée": "SAML authentication was refused",
    "OIDC désactivé": "OIDC is disabled",
    "OIDC désactivé ou mal configuré": "OIDC is disabled or misconfigured",
    "SAML désactivé": "SAML is disabled",
    "Réponse OIDC sans identité exploitable": "The OIDC response has no usable identity",
    "Fournisseur inconnu (attendu : oidc ou saml)": "Unknown provider (expected: oidc or saml)",
    "Votre accès à cette application a été révoqué.": "Your access to this application has been revoked.",
    "Votre domaine de messagerie n'est pas autorisé à accéder à cette application.":
        "Your email domain is not allowed to access this application.",

    # Rights and scope
    "Accès en écriture refusé": "Write access denied",
    "Accès non autorisé pour votre rôle": "Your role does not allow this",
    "Accès refusé à cette squad": "Access to this squad is denied",
    "Accès réservé au tribe leader": "Only the tribe leader can do this",
    "Accès réservé aux administrateurs": "Only administrators can do this",
    "Réservé au squad leader de cette squad": "Only this squad's leader can do this",
    "Réservé aux administrateurs et aux tribe leaders.": "Only administrators and tribe leaders can do this.",
    "Champs réservés au tribe leader": "These fields are reserved for the tribe leader",
    "Cet onglet d'administration ne vous est pas ouvert": "This administration tab is not open to you",
    "Hors de votre périmètre": "Outside your scope",
    "Tribe hors périmètre": "Tribe outside your scope",
    "Cette tribe n'est pas dans votre périmètre": "This tribe is not in your scope",
    "Cet utilisateur n'est pas dans votre périmètre": "This user is not in your scope",
    "Ce compte appartient à une autre tribe": "This account belongs to another tribe",
    "Ce compte n'est pas dans votre tribe.": "This account is not in your tribe.",
    "Cette squad n'est pas dans votre tribe.": "This squad is not in your tribe.",
    "Modification non autorisée": "You are not allowed to change this",
    "Suppression non autorisée": "You are not allowed to delete this",
    "L'organigramme est géré par le tribe leader": "The org chart is managed by the tribe leader",
    "Initiatives et OTD sont gérés par le tribe leader de la tribe":
        "Initiatives and OTDs are managed by the tribe's tribe leader",
    "Cet engagement appartient au leader de sa squad": "This commitment belongs to its squad's leader",
    "Seul l'administrateur peut déplacer une squad de tribe": "Only an administrator can move a squad to another tribe",
    "Seul un administrateur rétablit un administrateur.": "Only an administrator can restore an administrator.",
    "Seul un administrateur épingle un message global": "Only an administrator can pin a global message",
    "Seuls les leaders peuvent publier": "Only leaders can post",
    "Seuls un admin ou un tribe leader peuvent refuser un accès.": "Only an admin or a tribe leader can deny access.",
    "Épingler un message est réservé aux leaders": "Only leaders can pin a message",
    "Un tribe leader ne révoque pas un administrateur.": "A tribe leader cannot revoke an administrator.",
    "Vous ne contribuez pas à cette plateforme": "You do not contribute to this platform",
    "Vous ne dirigez pas cette squad": "You do not lead this squad",
    "Vous ne faites pas le reporting de cette squad": "You do not report for this squad",
    "Vous ne gérez pas cette personne": "You do not manage this person",
    "Vous ne pouvez créer des utilisateurs que dans votre tribe": "You can only create users in your own tribe",
    "Vous ne pouvez modifier que votre tribe": "You can only edit your own tribe",
    "Vous ne pouvez pas attribuer ce rôle.": "You cannot assign this role.",
    "Vous ne pouvez pas déplacer un utilisateur hors de votre tribe": "You cannot move a user out of your tribe",
    "Vous ne pouvez pas révoquer votre propre accès.": "You cannot revoke your own access.",
    "Vous ne pouvez pas supprimer votre propre compte": "You cannot delete your own account",
    "Vous ne pouvez saisir que pour votre périmètre": "You can only enter data for your own scope",
    "Vous ne pouvez supprimer que vos messages": "You can only delete your own messages",
    "Vous ne pouvez supprimer que vos réponses": "You can only delete your own replies",
    "Vous ne pouvez valider que pour vos squads.": "You can only approve for your own squads.",
    "Vous ne pouvez éditer que votre squad": "You can only edit your own squad",

    # Accounts
    "Ce compte est déjà actif.": "This account is already active.",
    "Cette demande a déjà été traitée.": "This request has already been handled.",
    "Email déjà utilisé": "Email already in use",
    "Adresse email invalide": "Invalid email address",
    "Il doit rester au moins un administrateur actif.": "At least one active administrator must remain.",
    "Le compte de secours doit rester administrateur": "The break-glass account must stay an administrator",
    "Le compte de secours ne peut pas être désactivé.": "The break-glass account cannot be disabled.",
    "Le compte de secours ne peut pas être supprimé": "The break-glass account cannot be deleted",
    "Le compte de secours ne peut pas être tribe leader": "The break-glass account cannot be a tribe leader",
    "Un administrateur ne peut pas être nommé tribe leader": "An administrator cannot be made tribe leader",
    "Choisissez la squad d'accueil.": "Choose the home squad.",
    "Au moins un scope est requis": "At least one scope is required",
    "Durée de validité invalide": "Invalid validity period",

    # Org, squads, tribes
    "Ce rattachement créerait une boucle": "This link would create a loop",
    "Nœud parent invalide": "Invalid parent node",
    "Un nœud ne peut pas être placé sous l'un de ses descendants": "A node cannot be placed under one of its descendants",
    "Un nœud ne peut pas être son propre parent": "A node cannot be its own parent",
    "Cette personne est déjà dans l'équipe": "This person is already on the team",
    "Indiquez l'email ou le nom de la personne": "Enter the person's email or name",
    "Le manager doit être un membre de la même squad": "The manager must be a member of the same squad",
    "La squad choisie n'appartient pas à cette tribe": "The chosen squad does not belong to this tribe",
    "Squad hors de cette tribe": "Squad outside this tribe",
    "Squad invalide pour cette tribe": "Invalid squad for this tribe",
    "Nom requis": "Name required",
    "Tribe requise": "Tribe required",
    "Précisez la tribe": "Specify the tribe",
    "Supprimez d'abord les OTD de cette tribe": "Delete this tribe's OTDs first",
    "Supprimez d'abord les initiatives de cette tribe": "Delete this tribe's initiatives first",
    "Supprimez ou déplacez d'abord les squads de cette tribe": "Delete or move this tribe's squads first",
    "Le budget n'est pas activé pour cette squad": "Budget is not enabled for this squad",

    # OTD, initiatives, milestones
    "Le porteur doit diriger une squad de cette tribe": "The owner must lead a squad in this tribe",
    "Le porteur doit être le leader ou un co-leader de cette squad": "The owner must be this squad's leader or a co-leader",
    "Un engagement de squad doit désigner sa squad": "A squad commitment must name its squad",
    "Un jalon n'appartient pas à cette tribe": "A milestone does not belong to this tribe",
    "Un jalon n'appartient pas à cette squad": "A milestone does not belong to this squad",
    "Un jalon n'est pas de l'année de cet engagement": "A milestone is not in this commitment's year",
    "Un jalon tient déjà un autre engagement de la squad": "A milestone already carries another commitment of the squad",

    # Leaves
    "Cette absence a déjà été traitée": "This leave has already been handled",
    "La date de fin précède la date de début": "The end date is before the start date",
    "Plage trop large (max 1 an)": "Range too wide (1 year at most)",
    "Une journée ne peut pas être demi le matin ET l'après-midi":
        "A day cannot be a half day both in the morning AND the afternoon",
    "Une précision est requise pour ce type d'absence": "This leave type needs a detail",

    # Platforms and Steerco
    "La plateforme doit avoir un nom": "The platform needs a name",
    "Une plateforme porte déjà ce nom": "A platform already has this name",
    "Précisez la tribe de la plateforme, ou au moins une squad contributrice":
        "Specify the platform's tribe, or at least one contributing squad",
    "Une squad contributrice n'appartient pas à cette tribe": "A contributing squad does not belong to this tribe",

    # Reports, mail, exports
    "Adresse destinataire requise": "Recipient address required",
    "Aucun template PPTX configuré.": "No PPTX template configured.",
    "Generation PPTX indisponible (python-pptx non installe)": "PPTX export unavailable (python-pptx not installed)",
    "Génération PPTX indisponible (python-pptx non installé)": "PPTX export unavailable (python-pptx not installed)",
    "SMTP désactivé": "SMTP is disabled",
    "L'envoi de l'email a échoué (vérifiez la configuration SMTP)":
        "The email could not be sent (check the SMTP settings)",
    "SMTP non configuré (activez-le dans l'Administration)": "SMTP is not configured (turn it on in Administration)",
    "Export des logs désactivé": "Log export is disabled",
    "since_days : entre 1 et 365 jours": "since_days: between 1 and 365 days",
    "since_days : nombre de jours attendu": "since_days: a number of days is expected",
    "Aucune squad disponible pour le test": "No squad available for the test",
    "Aucune tribe à configurer": "No tribe to configure",

    # Administration, data, ops
    "Aucune simulation en cours": "No impersonation in progress",
    "Service désactivé": "Service disabled",
    "Certificat d'autorité requis (fichier ou texte).": "A certificate authority is required (file or text).",
    "Choisissez au moins un domaine à effacer": "Choose at least one area to erase",
    "Confirmation manquante : cette opération efface des données": "Confirmation missing: this operation erases data",
    "Ce fichier ne contient aucune table de l'application": "This file contains none of the application's tables",
    "Le fichier doit définir une tribe (onglet 'Tribe' rempli).": "The file must define a tribe (fill in the 'Tribe' tab).",

    # Messages raised as ValueError by helpers and passed on as the detail
    "Fichier invalide : ce n'est pas un .pptx exploitable.": "Invalid file: this is not a usable .pptx.",
    "Aucun certificat d'autorité trouvé dans le PEM fourni.": "No certificate authority found in the given PEM.",
    "Autorité de certification introuvable.": "Certificate authority not found.",
    "Format non supporte: fournissez un fichier .xlsx ou .yaml": "Unsupported format: provide a .xlsx or .yaml file",
    "La tribe n'a pas de nom : renseignez la colonne \"Nom de la tribe\" de l'onglet Tribe.":
        "The tribe has no name: fill in the \"Nom de la tribe\" column of the Tribe tab.",
    "Renseignez le nom de la plateforme (onglet 'Infos').": "Enter the platform name ('Infos' tab).",
    "Renseignez le mois du rapport en cours (onglet 'Infos', format AAAA-MM).":
        "Enter the current report month ('Infos' tab, YYYY-MM format).",
}

# Field labels used by writeguard in its messages ("Le champ « titre » ...").
_LABELS = {"titre": "title", "nom": "name", "texte": "text", "thème": "theme", "porteur": "owner",
           "unité": "unit", "commentaire": "comment", "fonction": "role", "libellé": "label"}


def _label(m: re.Match) -> dict:
    d = m.groupdict()
    if "label" in d:
        d["label"] = _LABELS.get(d["label"], d["label"])
    return d


# Messages built with values. Named groups are reused in the English template.
PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^Le champ « (?P<label>.+?) » dépasse (?P<max>\d+) caractères \((?P<len>\d+)\)\.$"),
     "The \"{label}\" field is longer than {max} characters ({len})."),
    (re.compile(r"^Le champ « (?P<label>.+?) » ne peut pas être vide\.$"),
     "The \"{label}\" field cannot be empty."),
    (re.compile(r"^Le champ (?P<label>\S+) ne peut pas être vide$"),
     "The {label} field cannot be empty"),
    (re.compile(r"^Année invalide : (?P<val>.+)\.$"), "Invalid year: {val}."),
    (re.compile(r"^Cette clé d'API n'a pas le scope « (?P<scope>.+) »$"),
     "This API key does not have the \"{scope}\" scope"),
    (re.compile(r"^Rôle non autorisé \(autorisés : (?P<roles>.*)\)$"),
     "Role not allowed (allowed: {roles})"),
    (re.compile(r"^Ajout d'autorité impossible : (?P<err>.*)$", re.S),
     "Could not add the authority: {err}"),
    (re.compile(r"^Import impossible : (?P<err>.*)$", re.S), "Import failed: {err}"),
    (re.compile(r"^Fichier illisible : (?P<err>.*)$", re.S), "Unreadable file: {err}"),
    (re.compile(r"^(?P<max>\d+) engagements au plus par mois : (?P<month>\S+) en compte déjà (?P<n>\d+)$"),
     "{max} commitments per month at most: {month} already has {n}"),
    (re.compile(r"^Une squad s'appelle déjà « (?P<name>.+) » dans cette tribe$"),
     "A squad named \"{name}\" already exists in this tribe"),
    (re.compile(r"^(?P<name>.+) n'appartient pas à la tribe de cette squad$"),
     "{name} does not belong to this squad's tribe"),
    (re.compile(r"^(?P<name>.+) est déjà tribe leader d'une autre tribe$"),
     "{name} is already tribe leader of another tribe"),
    (re.compile(r"^Période invalide : (?P<p>.+) \(attendu AAAA-MM\)$"),
     "Invalid period: {p} (expected YYYY-MM)"),
    (re.compile(r"^Le fournisseur d'identité a refusé la connexion \((?P<err>[^)]*)\)\.(?P<rest>.*)$", re.S),
     "The identity provider refused the sign-in ({err}).{rest}"),
    (re.compile(r"^Métadonnées SP invalides: (?P<err>.*)$", re.S), "Invalid SP metadata: {err}"),
    (re.compile(r"^L'envoi de l'email a échoué \(vérifiez la configuration SMTP\) : (?P<err>.*)$", re.S),
     "The email could not be sent (check the SMTP settings): {err}"),
    # Helpers' ValueError messages passed on as the detail.
    (re.compile(r"^Niveau de log invalide: (?P<level>.*)$"), "Invalid log level: {level}"),
    (re.compile(r"^Date de version illisible : (?P<val>.*)$"), "Unreadable version date: {val}"),
    (re.compile(r"^Onglets manquants dans le fichier : (?P<tabs>.*)\.$"), "Tabs missing from the file: {tabs}."),
    (re.compile(r"^Mois du rapport invalide : « (?P<p>.*) »\. Format attendu : AAAA-MM\.$"),
     "Invalid report month: \"{p}\". Expected format: YYYY-MM."),
    (re.compile(r"^Plateforme introuvable : « (?P<name>.*) »\. Vérifiez le nom exact dans l'app\.$"),
     "Platform not found: \"{name}\". Check the exact name in the app."),
    (re.compile(r"^Plusieurs plateformes s'appellent « (?P<name>.*) »\. Renommez-en une pour lever l'ambiguïté\.$"),
     "Several platforms are named \"{name}\". Rename one to remove the ambiguity."),
]


def translate(detail: str) -> str:
    """English wording of a French detail, or the detail unchanged when unknown."""
    hit = EN.get(detail)
    if hit is not None:
        return hit
    for rx, tpl in PATTERNS:
        m = rx.match(detail)
        if m:
            return tpl.format(**_label(m))
    return detail
