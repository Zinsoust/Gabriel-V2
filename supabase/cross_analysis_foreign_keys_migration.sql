-- ─── Gabriel V2 — Clés étrangères Cross Analyse (correctif additif) ─────────
--
-- Constat d'audit : gabriel_cross_analysis_sources et gabriel_source_comments
-- n'avaient aucune contrainte de clé étrangère vers leurs tables parentes —
-- supprimer une gabriel_cross_analyses ou gabriel_psychologue_sources
-- laissait des lignes orphelines invisibles pour les lectures normales.
--
-- IMPORTANT — non testé en conditions réelles (pas d'instance Supabase
-- disponible dans cet environnement). À exécuter dans le SQL Editor Supabase
-- en environnement de test avant la production, et à relire avant d'exécuter.
--
-- Le script est idempotent (peut être rejoué sans erreur) et défensif :
-- il retire d'abord les lignes déjà orphelines (qui empêcheraient sinon
-- l'ajout des contraintes) avant de les poser. Si des lignes orphelines
-- existent, elles seront supprimées — vérifier le résultat du SELECT de
-- diagnostic en bas de fichier après exécution.
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Nettoyage défensif : une contrainte FK ne peut pas être ajoutée si des
--    lignes existantes la violent déjà (ex: état orphelin laissé par un
--    échec d'écriture avant le correctif de compensation de create_cross_analysis).

DELETE FROM gabriel_cross_analysis_sources cas
WHERE NOT EXISTS (
  SELECT 1 FROM gabriel_cross_analyses ca
  WHERE ca.cross_analysis_id = cas.cross_analysis_id
);

DELETE FROM gabriel_cross_analysis_sources cas
WHERE NOT EXISTS (
  SELECT 1 FROM gabriel_psychologue_sources ps
  WHERE ps.source_id = cas.source_id
);

DELETE FROM gabriel_source_comments sc
WHERE NOT EXISTS (
  SELECT 1 FROM gabriel_psychologue_sources ps
  WHERE ps.source_id = sc.source_id
);

-- 2. Contraintes de clé étrangère.
--
--    gabriel_cross_analysis_sources n'a de sens que rattachée à sa session
--    Cross ET à sa source : CASCADE des deux côtés — supprimer l'une ou
--    l'autre supprime le lien, jamais un état à moitié référencé.
--
--    gabriel_source_comments appartient au cycle de vie de sa source
--    (gabriel_psychologue_sources), pas à une session Cross précise —
--    CASCADE uniquement depuis la source, jamais depuis gabriel_cross_analyses.

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'gabriel_cross_analysis_sources_cross_fk'
  ) THEN
    ALTER TABLE gabriel_cross_analysis_sources
      ADD CONSTRAINT gabriel_cross_analysis_sources_cross_fk
      FOREIGN KEY (cross_analysis_id)
      REFERENCES gabriel_cross_analyses (cross_analysis_id)
      ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'gabriel_cross_analysis_sources_source_fk'
  ) THEN
    ALTER TABLE gabriel_cross_analysis_sources
      ADD CONSTRAINT gabriel_cross_analysis_sources_source_fk
      FOREIGN KEY (source_id)
      REFERENCES gabriel_psychologue_sources (source_id)
      ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'gabriel_source_comments_source_fk'
  ) THEN
    ALTER TABLE gabriel_source_comments
      ADD CONSTRAINT gabriel_source_comments_source_fk
      FOREIGN KEY (source_id)
      REFERENCES gabriel_psychologue_sources (source_id)
      ON DELETE CASCADE;
  END IF;
END $$;

-- Vérification post-migration : les 3 contraintes doivent apparaître.
SELECT conname, conrelid::regclass AS table_name, confrelid::regclass AS references_table, confdeltype
FROM pg_constraint
WHERE conname IN (
  'gabriel_cross_analysis_sources_cross_fk',
  'gabriel_cross_analysis_sources_source_fk',
  'gabriel_source_comments_source_fk'
);
