# Gabriel — Protocole Sécurité Beta Fermée

**Version** : 1.0 — Niveau 2 Sécurité  
**Statut** : Prêt pour beta fermée (Supabase RLS en attente de validation finale)

---

## 1. Nombre de testeurs recommandés

**5 à 10 testeurs maximum** pour la première vague.

- Personnes de confiance uniquement (pas de liens publics partagés).
- Profils recommandés : créateurs de contenu, coachs, consultants, agences.
- Langue : français uniquement pour la beta v1.
- Accès : par invitation directe via email (compte créé manuellement ou par lien).

---

## 2. Données autorisées en beta

| Type | Autorisé |
|------|----------|
| Commentaires YouTube / TikTok / Instagram publics | ✅ |
| Textes libres de l'utilisateur (contexte business, briefs) | ✅ |
| Données business non sensibles (secteur, offre, cible) | ✅ |
| Feedbacks sur les analyses et stratégies | ✅ |
| Export PDF des analyses et stratégies | ✅ |

---

## 3. Données à éviter en beta

| Type | Interdit / Déconseillé |
|------|------------------------|
| Données personnelles de tiers (noms réels, emails, téléphones) | ❌ Interdit |
| Données financières précises (revenus, marges) | ⚠️ Déconseillé |
| Secrets commerciaux confidentiels | ⚠️ Déconseillé |
| Données de mineurs | ❌ Interdit |
| Commentaires haineux, illégaux ou à caractère discriminatoire | ❌ Interdit |

> **Rappel** : Gabriel analyse des données pour produire des insights. Ces données sont stockées de façon isolée par utilisateur. Supabase RLS sera activé dès validation.

---

## 4. Comment signaler un bug

**Canal prioritaire** : Email direct à `gabrielaigithub@gmail.com`

**Format de signalement** :
```
Objet : [BUG GABRIEL] Titre court

Étapes pour reproduire :
1. ...
2. ...
3. ...

Comportement observé :
...

Comportement attendu :
...

Capture d'écran ou message d'erreur visible :
...

Navigateur / OS :
...
```

**Délai de réponse** : sous 48h.

---

## 5. Comment donner un feedback

Deux niveaux de feedback :

### a) Feedback intégré (dans l'application)
- Après chaque analyse : bouton étoile / pouce
- Champs disponibles : note globale (1-5), utilité, précision, actionabilité
- Commentaire libre : 2 000 caractères max
- **Ne jamais coller de secrets, de clés API ou de données personnelles dans le feedback**

### b) Feedback qualitatif (email)
- Partager ce qui a fonctionné ou non
- Indiquer les cas d'usage les plus utiles
- Signaler les réponses IA incorrectes ou hors sujet

---

## 6. Comment mesurer la qualité d'une stratégie

Une stratégie est de qualité si elle répond à ces critères :

| Critère | Indicateur |
|---------|------------|
| **Pertinence** | La décision prioritaire correspond à la réalité de l'utilisateur |
| **Ancrage données** | Chaque recommandation cite un signal audience réel |
| **Actionabilité** | L'utilisateur peut commencer cette semaine |
| **Précision** | Pas de conseil vague ou générique |
| **Cohérence** | La stratégie découle logiquement de l'analyse psychologique |

**Score de confiance** : Gabriel affiche un score entre 0 et 1. Un score < 0.6 signifie que les données sont insuffisantes pour une recommandation fiable — demandez à l'utilisateur de fournir plus de contexte.

---

## 7. Comment vérifier l'absence de fuite entre utilisateurs

### Tests manuels (à faire avant l'ouverture)

1. **Créer deux comptes** : A (admin@test.com) et B (user@test.com).
2. **Avec le compte A** : lancer une analyse, générer une stratégie. Noter l'`analysis_id` et le `job_id`.
3. **Avec le compte B** : tenter d'accéder à `GET /status/<job_id_de_A>` → attendu : **404**.
4. **Avec le compte B** : tenter `GET /history/<analysis_id_de_A>/load` → attendu : **404**.
5. **Avec le compte B** : consulter `GET /history` → la liste ne doit **pas** contenir les analyses de A.
6. **Avec le compte B** : consulter `GET /strategies` → la liste ne doit **pas** contenir les stratégies de A.

### Tests automatiques
```bash
venv/bin/pytest tests/test_ux_backend.py::test_job_isolation_other_user_gets_404 -v
venv/bin/pytest tests/security/ -v
```

---

## 8. Comment surveiller les coûts IA

### Coûts approximatifs par action (Mistral)

| Action | Modèle | Tokens estimés | Coût estimé |
|--------|--------|---------------|-------------|
| Analyse psychologique (Layer 2) | mistral-large | ~4 000–8 000 | ~0,03–0,06 € |
| Génération stratégie | mistral-large | ~3 000–5 000 | ~0,02–0,04 € |
| Chat stratégique (par message) | mistral-large | ~2 000–4 000 | ~0,015–0,03 € |
| Création de contenu | mistral-large | ~2 000–4 000 | ~0,015–0,03 € |
| Extraction contexte (PDF/texte) | mistral-small | ~500–1 500 | ~0,001–0,003 € |

### Limites en place
- `/analyze` : 10 par heure par utilisateur
- `/strategize` : 20 par heure
- `/creator/generate` : 30 par heure
- `/strategy_chat` : 60 par heure
- `/export/strategy_pdf` : 10 par heure

### Surveillance
- Vérifier les dashboards Mistral et Anthropic quotidiennement pendant la beta.
- Alerter si un utilisateur dépasse 50 analyses en 24h (comportement anormal).
- Configurer une alerte de budget sur le dashboard Mistral (recommandé : 20 €/semaine max en beta).

---

## 9. Quand arrêter la beta si problème critique

**Arrêt immédiat requis si** :

| Condition | Action |
|-----------|--------|
| Fuite de données entre utilisateurs (A voit les données de B) | Couper l'accès, investiguer |
| Exposition de clé API dans les réponses | Révoquer les clés, corriger, relancer |
| Erreur 500 systématique sur une route critique | Désactiver la route, investiguer |
| Coût IA anormalement élevé (>3× la normale) | Suspendre les comptes suspects |
| Contenu illégal généré ou traité | Bloquer l'utilisateur, signaler si nécessaire |
| Crash du serveur répété | Rollback vers la version précédente |

**Comment couper l'accès rapidement** :
```bash
# Arrêter le serveur
kill $(lsof -ti:5050)

# Ou bloquer un utilisateur en DB (Supabase dashboard)
# DELETE FROM gabriel_users WHERE email = 'user@suspect.com';
```

---

## 10. Checklist avant ouverture plus large

### Sécurité application
- [x] Auth obligatoire (`AUTH_ENABLED=true`)
- [x] Rate limiting actif (`RATE_LIMIT_ENABLED=true`)
- [x] Validation des inputs (taille, type)
- [x] Anti prompt injection dans tous les agents
- [x] Pas de `str(e)` exposé dans les réponses
- [x] Pas de stack trace dans les réponses
- [x] `FLASK_SECRET_KEY` fort (64 chars hex minimum)
- [x] `.env` dans `.gitignore`

### Sécurité base de données
- [ ] Supabase RLS activé et testé sur toutes les tables
- [ ] Clé anon Supabase vérifiée (ne donne pas accès aux données autres utilisateurs)
- [ ] Clé service role jamais exposée côté client
- [ ] Backup automatique Supabase activé

### Qualité produit
- [x] Parcours complet testable sans erreur
- [x] Routes API retournent JSON propre
- [x] Pages protégées redirigent correctement
- [x] Session expirée → message clair + redirect login
- [x] Rate limit atteint → message clair
- [ ] Test manuel avec 2 utilisateurs réels
- [ ] Test avec 50+ commentaires réels

### Opérationnel
- [ ] URL de production configurée (`APP_URL` dans `.env`)
- [ ] Google OAuth configuré pour le domaine de production
- [ ] Stripe webhook configuré et testé
- [ ] Monitoring basique (Sentry ou équivalent) activé
- [ ] Email de support configuré et testé

---

*Protocole préparé dans le cadre du Niveau 2 Sécurité Gabriel — beta fermée prévue avant déploiement public.*
