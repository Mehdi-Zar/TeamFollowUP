# Conventions du projet TeamFollowUP

## Rédaction / typographie
- **Jamais de tiret cadratin (—, em dash) ni de point médian (·, middot/interpunct)**
  dans le texte visible par l'utilisateur (libellés UI, i18n FR/EN, documents générés
  HTML/PPTX, messages, titres, tooltips). Ces signes "font IA". Utiliser une virgule,
  « : », des parenthèses, un retour à la ligne ou une simple espace selon le cas.
- Plus généralement, rien qui "fasse IA" dans le rendu.
- Deux tests garde-fou appliquent la règle, et tournent avec les suites normales :
  `backend/tests/test_typography.py` (tous les littéraux de chaînes sous `backend/app`,
  hors docstrings, la prose de développeur n'étant pas visée) et
  `frontend/src/typography.test.ts` (tout `frontend/src`, hors lignes de commentaire).
