# Conventions du projet TeamFollowUP

## Rédaction / typographie
- **Jamais de tiret cadratin (em dash, U+2014) ni de point médian (middot ou
  interpunct, U+00B7)**
  dans le texte visible par l'utilisateur (libellés UI, i18n FR/EN, documents générés
  HTML/PPTX, messages, titres, tooltips). Ces signes "font IA". Utiliser une virgule,
  « : », des parenthèses, un retour à la ligne ou une simple espace selon le cas.
- Plus généralement, rien qui "fasse IA" dans le rendu.
- La règle vaut pour **tout le dépôt**, sans liste d'exceptions : code, commentaires,
  docstrings (FastAPI les publie dans l'OpenAPI et donc dans Swagger UI), documentation,
  CHANGELOG. Les deux caractères sont désignés ici par leur point de code, et les
  garde-fous les écrivent en échappement, pour que ces fichiers passent leur propre règle.
- Deux tests appliquent la règle et tournent avec les suites normales :
  `backend/tests/test_typography.py` (balayage de tout le dépôt) et
  `frontend/src/typography.test.ts` (retour rapide côté frontend). Un troisième,
  `backend/tests/test_report_typography.py`, lit les documents HTML et PPTX réellement
  produits, ce qu'aucun contrôle sur le code source ne peut garantir.
