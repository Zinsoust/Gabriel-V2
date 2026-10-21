-- Studio UX du Stratège : brouillon, publication et historique limité.
CREATE TABLE IF NOT EXISTS gabriel_ux_settings (
    page_key     text PRIMARY KEY,
    draft        jsonb NOT NULL DEFAULT '{}'::jsonb,
    published    jsonb NOT NULL DEFAULT '{}'::jsonb,
    history      jsonb NOT NULL DEFAULT '[]'::jsonb,
    version      integer NOT NULL DEFAULT 0,
    updated_by   text,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);

ALTER TABLE gabriel_ux_settings ENABLE ROW LEVEL SECURITY;

-- Acces applicatif uniquement : les routes Flask verifient ADMIN_USER_IDS et
-- utilisent le client serveur. Aucun accès direct depuis le navigateur.
DROP POLICY IF EXISTS "gabriel_ux_settings_no_direct_access" ON gabriel_ux_settings;
CREATE POLICY "gabriel_ux_settings_no_direct_access"
ON gabriel_ux_settings FOR ALL
USING (false)
WITH CHECK (false);
