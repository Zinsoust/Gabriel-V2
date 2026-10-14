-- GABRIEL PROSPECT MVP 3 — validation transactionnelle DEV
--
-- Préconditions :
--   1. Exécuter uniquement sur le projet Supabase DEV gabriel-prospect-dev-steph.
--   2. Exécuter depuis le SQL Editor avec le rôle administrateur du projet.
--   3. La migration 20261012_gabriel_prospect_mvp3.sql doit déjà être appliquée.
--
-- Garanties de ce script :
--   - aucune modification du schéma ;
--   - uniquement des données fictives ;
--   - toutes les écritures sont annulées par ROLLBACK ;
--   - les erreurs fonctionnelles attendues sont capturées et vérifiées ;
--   - le résultat final est explicitement PASS ou FAIL.
--
-- Limite volontaire : la phase 1 s'exécute comme administrateur et ne valide
-- donc PAS l'isolation RLS. La phase 2 change réellement de rôle afin de tester
-- les permissions SQL actuelles. Comme anon/authenticated n'ont aucun droit de
-- table dans l'architecture actuelle, elle vérifie leur refus d'accès, et non
-- le filtrage d'un JWT par les politiques RLS.

BEGIN;

SET LOCAL statement_timeout = '20s';
SET LOCAL lock_timeout = '5s';

SELECT set_config('gabriel.validation.result', 'PASS', true);
SELECT set_config('gabriel.validation.failures', '', true);

-- ---------------------------------------------------------------------------
-- PHASE 1 — contraintes et triggers fonctionnels (rôle administrateur)
-- ---------------------------------------------------------------------------

DO $functional_validation$
DECLARE
    import_a CONSTANT uuid := '10000000-0000-4000-8000-000000000001';
    import_b CONSTANT uuid := '10000000-0000-4000-8000-000000000002';
    ineligible_a CONSTANT uuid := '20000000-0000-4000-8000-000000000001';
    eligible_a CONSTANT uuid := '20000000-0000-4000-8000-000000000002';
    eligible_b CONSTANT uuid := '20000000-0000-4000-8000-000000000003';
    opposed_a CONSTANT uuid := '20000000-0000-4000-8000-000000000004';
    reimport_a CONSTANT uuid := '20000000-0000-4000-8000-000000000005';
    cross_owner CONSTANT uuid := '20000000-0000-4000-8000-000000000006';
    expected_error boolean;
    row_count integer;
BEGIN
    INSERT INTO public.gabriel_prospect_imports (
        import_id,
        user_id,
        source_filename,
        source_sha256,
        source_size_bytes,
        rows_received,
        rows_selected
    ) VALUES
        (
            import_a,
            'validation-user-a',
            'agences-validation-a.csv',
            repeat('1', 64),
            512,
            4,
            4
        ),
        (
            import_b,
            'validation-user-b',
            'agences-validation-b.csv',
            repeat('2', 64),
            256,
            1,
            1
        );

    -- La clé étrangère composite interdit de rattacher un prospect de B à
    -- l'import de A. Cette vérification porte sur l'intégrité des propriétaires,
    -- pas sur RLS.
    expected_error := false;
    BEGIN
        INSERT INTO public.gabriel_prospects (
            prospect_id,
            user_id,
            import_id,
            source_row,
            status,
            company_name,
            identity_hash,
            icp_score,
            eligibility
        ) VALUES (
            cross_owner,
            'validation-user-b',
            import_a,
            2,
            'to_enrich',
            'Entreprise intercompte fictive',
            repeat('6', 64),
            10,
            '{"eligible_for_contact_preparation": false}'::jsonb
        );
    EXCEPTION
        WHEN foreign_key_violation THEN
            expected_error := true;
    END;
    IF NOT expected_error THEN
        RAISE EXCEPTION 'séparation utilisateurs : la FK composite a accepté un import appartenant à un autre utilisateur';
    END IF;
    RAISE NOTICE 'PASS 1/7 — propriété user_id/import_id séparée';

    INSERT INTO public.gabriel_prospects (
        prospect_id,
        user_id,
        import_id,
        source_row,
        status,
        company_name,
        company_domain,
        contact_name,
        email_hash,
        identity_hash,
        icp_score,
        data,
        eligibility
    ) VALUES
        (
            ineligible_a,
            'validation-user-a',
            import_a,
            2,
            'to_enrich',
            'Agence À Enrichir Fictive',
            'a-enrichir.invalid',
            NULL,
            NULL,
            repeat('3', 64),
            55,
            '{"company_name":"Agence À Enrichir Fictive"}'::jsonb,
            '{"eligible_for_contact_preparation": false}'::jsonb
        ),
        (
            eligible_a,
            'validation-user-a',
            import_a,
            3,
            'qualified',
            'Agence Alpha Fictive',
            'alpha.invalid',
            'Alice Exemple',
            repeat('a', 64),
            NULL,
            90,
            '{"company_name":"Agence Alpha Fictive","email":"alice@alpha.invalid"}'::jsonb,
            '{"eligible_for_contact_preparation": true}'::jsonb
        ),
        (
            eligible_b,
            'validation-user-b',
            import_b,
            2,
            'qualified',
            'Agence Bêta Fictive',
            'beta.invalid',
            'Bob Exemple',
            repeat('a', 64),
            NULL,
            85,
            '{"company_name":"Agence Bêta Fictive","email":"bob@beta.invalid"}'::jsonb,
            '{"eligible_for_contact_preparation": true}'::jsonb
        ),
        (
            opposed_a,
            'validation-user-a',
            import_a,
            4,
            'qualified',
            'Agence Opposition Fictive',
            'opposition.invalid',
            'Camille Exemple',
            repeat('d', 64),
            NULL,
            80,
            '{"company_name":"Agence Opposition Fictive","email":"camille@opposition.invalid"}'::jsonb,
            '{"eligible_for_contact_preparation": true}'::jsonb
        );

    -- Un statut de prospection interdit doit être refusé pour une fiche non
    -- éligible, et le refus ne doit créer aucun événement de changement.
    expected_error := false;
    BEGIN
        UPDATE public.gabriel_prospects
        SET status = 'contacted'
        WHERE prospect_id = ineligible_a
          AND user_id = 'validation-user-a';
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLSTATE = 'P0001' AND SQLERRM = 'contact_not_eligible' THEN
                expected_error := true;
            ELSE
                RAISE;
            END IF;
    END;
    IF NOT expected_error THEN
        RAISE EXCEPTION 'éligibilité : le statut contacted a été accepté pour un prospect non éligible';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM public.gabriel_prospects
        WHERE prospect_id = ineligible_a
          AND user_id = 'validation-user-a'
          AND status = 'to_enrich'
    ) THEN
        RAISE EXCEPTION 'éligibilité : le statut initial n''a pas été conservé après le refus';
    END IF;
    SELECT count(*)
    INTO row_count
    FROM public.gabriel_prospect_events
    WHERE prospect_id = ineligible_a;
    IF row_count <> 1 THEN
        RAISE EXCEPTION 'éligibilité : % événement(s) trouvé(s), 1 événement created attendu', row_count;
    END IF;
    RAISE NOTICE 'PASS 2/7 — statut commercial interdit refusé pour un prospect non éligible';

    -- Le trigger d'historique doit produire created puis status_changed.
    UPDATE public.gabriel_prospects
    SET status = 'contacted'
    WHERE prospect_id = eligible_a
      AND user_id = 'validation-user-a';

    SELECT count(*)
    INTO row_count
    FROM public.gabriel_prospect_events
    WHERE prospect_id = eligible_a
      AND user_id = 'validation-user-a';
    IF row_count <> 2
       OR NOT EXISTS (
            SELECT 1
            FROM public.gabriel_prospect_events
            WHERE prospect_id = eligible_a
              AND user_id = 'validation-user-a'
              AND event_type = 'created'
              AND from_status IS NULL
              AND to_status = 'qualified'
       )
       OR NOT EXISTS (
            SELECT 1
            FROM public.gabriel_prospect_events
            WHERE prospect_id = eligible_a
              AND user_id = 'validation-user-a'
              AND event_type = 'status_changed'
              AND from_status = 'qualified'
              AND to_status = 'contacted'
       ) THEN
        RAISE EXCEPTION 'historique : séquence created/status_changed incorrecte';
    END IF;
    RAISE NOTICE 'PASS 3/7 — historique commercial généré correctement';

    -- Passage en opposition, horodatage, suppression et conservation du hash.
    UPDATE public.gabriel_prospects
    SET status = 'do_not_contact'
    WHERE prospect_id = opposed_a
      AND user_id = 'validation-user-a';

    IF NOT EXISTS (
        SELECT 1
        FROM public.gabriel_prospects
        WHERE prospect_id = opposed_a
          AND user_id = 'validation-user-a'
          AND status = 'do_not_contact'
          AND do_not_contact_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'opposition : statut ou horodatage do_not_contact absent';
    END IF;

    DELETE FROM public.gabriel_prospects
    WHERE prospect_id = opposed_a
      AND user_id = 'validation-user-a';

    IF EXISTS (
        SELECT 1 FROM public.gabriel_prospects WHERE prospect_id = opposed_a
    ) THEN
        RAISE EXCEPTION 'opposition : le prospect demandé n''a pas été supprimé';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM public.gabriel_prospect_suppressions
        WHERE user_id = 'validation-user-a'
          AND identifier_kind = 'email'
          AND identifier_hash = repeat('d', 64)
    ) THEN
        RAISE EXCEPTION 'opposition : l''empreinte email n''a pas été conservée';
    END IF;
    RAISE NOTICE 'PASS 4/7 — empreinte do_not_contact conservée après suppression';

    -- Un INSERT direct contournant le repository doit être bloqué par la base.
    expected_error := false;
    BEGIN
        INSERT INTO public.gabriel_prospects (
            prospect_id,
            user_id,
            import_id,
            source_row,
            status,
            company_name,
            company_domain,
            contact_name,
            email_hash,
            icp_score,
            data,
            eligibility
        ) VALUES (
            reimport_a,
            'validation-user-a',
            import_a,
            5,
            'to_enrich',
            'Agence Réimport Fictive',
            'reimport.invalid',
            'Camille Exemple',
            repeat('d', 64),
            80,
            '{"company_name":"Agence Réimport Fictive","email":"camille@opposition.invalid"}'::jsonb,
            '{"eligible_for_contact_preparation": false}'::jsonb
        );
    EXCEPTION
        WHEN unique_violation THEN
            IF SQLERRM = 'contact identifier is suppressed' THEN
                expected_error := true;
            ELSE
                RAISE;
            END IF;
    END;
    IF NOT expected_error THEN
        RAISE EXCEPTION 'opposition : le réimport direct de l''empreinte opposée a été accepté';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.gabriel_prospects WHERE prospect_id = reimport_a
    ) THEN
        RAISE EXCEPTION 'opposition : une ligne de réimport subsiste malgré le refus';
    END IF;
    RAISE NOTICE 'PASS 5/7 — réimport direct du contact opposé refusé';

    -- Le même hash peut appartenir à deux comptes : les index uniques et les
    -- historiques sont bien bornés par user_id. Ce contrôle n'est pas un test RLS.
    SELECT count(DISTINCT user_id)
    INTO row_count
    FROM public.gabriel_prospects
    WHERE email_hash = repeat('a', 64);
    IF row_count <> 2 THEN
        RAISE EXCEPTION 'séparation utilisateurs : le même hash n''est pas isolé sur deux comptes';
    END IF;
    IF (SELECT count(*) FROM public.gabriel_prospects WHERE user_id = 'validation-user-a') <> 2
       OR (SELECT count(*) FROM public.gabriel_prospects WHERE user_id = 'validation-user-b') <> 1 THEN
        RAISE EXCEPTION 'séparation utilisateurs : nombre de prospects inattendu par propriétaire';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM public.gabriel_prospect_events AS event
        JOIN public.gabriel_prospects AS prospect
          ON prospect.prospect_id = event.prospect_id
        WHERE event.user_id <> prospect.user_id
    ) THEN
        RAISE EXCEPTION 'séparation utilisateurs : historique attribué à un autre propriétaire';
    END IF;
    RAISE NOTICE 'PASS 6/7 — données et historiques séparés par user_id au niveau des contraintes';

    IF (SELECT count(*) FROM public.gabriel_prospect_suppressions
        WHERE user_id = 'validation-user-a'
          AND identifier_kind = 'email'
          AND identifier_hash = repeat('d', 64)) <> 1 THEN
        RAISE EXCEPTION 'opposition : empreinte absente ou dupliquée en fin de scénario';
    END IF;
    RAISE NOTICE 'PASS 7/7 — invariants fonctionnels finaux cohérents';
EXCEPTION
    WHEN OTHERS THEN
        PERFORM set_config('gabriel.validation.result', 'FAIL', true);
        PERFORM set_config(
            'gabriel.validation.failures',
            concat_ws(
                '; ',
                NULLIF(current_setting('gabriel.validation.failures', true), ''),
                format('phase fonctionnelle [%s] %s', SQLSTATE, SQLERRM)
            ),
            true
        );
        RAISE WARNING 'FAIL — phase fonctionnelle [%] %', SQLSTATE, SQLERRM;
END;
$functional_validation$;

-- ---------------------------------------------------------------------------
-- PHASE 2 — permissions SQL réelles des rôles Supabase
-- ---------------------------------------------------------------------------
-- Cette phase vérifie les REVOKE/GRANT en prenant réellement chaque rôle.
-- Elle ne prétend pas valider le filtrage RLS par auth.uid() : anon et
-- authenticated sont volontairement arrêtés avant RLS par les droits de table,
-- et service_role possède BYPASSRLS.

SET LOCAL ROLE anon;
DO $anon_permissions$
DECLARE
    access_denied boolean := false;
BEGIN
    BEGIN
        PERFORM 1 FROM public.gabriel_prospects LIMIT 1;
    EXCEPTION
        WHEN insufficient_privilege THEN
            access_denied := true;
    END;
    IF NOT access_denied THEN
        PERFORM set_config('gabriel.validation.result', 'FAIL', true);
        PERFORM set_config(
            'gabriel.validation.failures',
            concat_ws(
                '; ',
                NULLIF(current_setting('gabriel.validation.failures', true), ''),
                'permissions anon : SELECT autorisé'
            ),
            true
        );
        RAISE WARNING 'FAIL — le rôle anon peut lire gabriel_prospects';
    ELSE
        RAISE NOTICE 'PASS permissions — anon ne peut pas lire les prospects';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        PERFORM set_config('gabriel.validation.result', 'FAIL', true);
        PERFORM set_config(
            'gabriel.validation.failures',
            concat_ws(
                '; ',
                NULLIF(current_setting('gabriel.validation.failures', true), ''),
                format('permissions anon [%s] %s', SQLSTATE, SQLERRM)
            ),
            true
        );
        RAISE WARNING 'FAIL — permissions anon [%] %', SQLSTATE, SQLERRM;
END;
$anon_permissions$;
RESET ROLE;

SET LOCAL ROLE authenticated;
DO $authenticated_permissions$
DECLARE
    access_denied boolean := false;
BEGIN
    BEGIN
        PERFORM 1 FROM public.gabriel_prospects LIMIT 1;
    EXCEPTION
        WHEN insufficient_privilege THEN
            access_denied := true;
    END;
    IF NOT access_denied THEN
        PERFORM set_config('gabriel.validation.result', 'FAIL', true);
        PERFORM set_config(
            'gabriel.validation.failures',
            concat_ws(
                '; ',
                NULLIF(current_setting('gabriel.validation.failures', true), ''),
                'permissions authenticated : SELECT autorisé'
            ),
            true
        );
        RAISE WARNING 'FAIL — le rôle authenticated peut lire gabriel_prospects';
    ELSE
        RAISE NOTICE 'PASS permissions — authenticated ne peut pas lire les prospects';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        PERFORM set_config('gabriel.validation.result', 'FAIL', true);
        PERFORM set_config(
            'gabriel.validation.failures',
            concat_ws(
                '; ',
                NULLIF(current_setting('gabriel.validation.failures', true), ''),
                format('permissions authenticated [%s] %s', SQLSTATE, SQLERRM)
            ),
            true
        );
        RAISE WARNING 'FAIL — permissions authenticated [%] %', SQLSTATE, SQLERRM;
END;
$authenticated_permissions$;
RESET ROLE;

SET LOCAL ROLE service_role;
DO $service_role_permissions$
DECLARE
    visible_rows integer;
    insert_denied boolean := false;
BEGIN
    SELECT count(*) INTO visible_rows FROM public.gabriel_prospects;
    IF visible_rows <> 3 THEN
        PERFORM set_config('gabriel.validation.result', 'FAIL', true);
        PERFORM set_config(
            'gabriel.validation.failures',
            concat_ws(
                '; ',
                NULLIF(current_setting('gabriel.validation.failures', true), ''),
                format('permissions service_role : %s lignes visibles au lieu de 3', visible_rows)
            ),
            true
        );
        RAISE WARNING 'FAIL — service_role voit % lignes au lieu de 3', visible_rows;
    ELSE
        RAISE NOTICE 'PASS permissions — service_role peut lire les données nécessaires au repository';
    END IF;

    BEGIN
        INSERT INTO public.gabriel_prospect_suppressions (
            user_id,
            identifier_kind,
            identifier_hash
        ) VALUES (
            'validation-user-permission',
            'email',
            repeat('f', 64)
        );
    EXCEPTION
        WHEN insufficient_privilege THEN
            insert_denied := true;
    END;
    IF NOT insert_denied THEN
        PERFORM set_config('gabriel.validation.result', 'FAIL', true);
        PERFORM set_config(
            'gabriel.validation.failures',
            concat_ws(
                '; ',
                NULLIF(current_setting('gabriel.validation.failures', true), ''),
                'permissions service_role : INSERT suppression autorisé'
            ),
            true
        );
        RAISE WARNING 'FAIL — service_role peut insérer directement une opposition';
    ELSE
        RAISE NOTICE 'PASS permissions — service_role ne peut pas insérer directement une opposition';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        PERFORM set_config('gabriel.validation.result', 'FAIL', true);
        PERFORM set_config(
            'gabriel.validation.failures',
            concat_ws(
                '; ',
                NULLIF(current_setting('gabriel.validation.failures', true), ''),
                format('permissions service_role [%s] %s', SQLSTATE, SQLERRM)
            ),
            true
        );
        RAISE WARNING 'FAIL — permissions service_role [%] %', SQLSTATE, SQLERRM;
END;
$service_role_permissions$;
RESET ROLE;

-- Bilan visible dans les résultats du SQL Editor. Toute valeur différente de
-- PASS interdit de considérer la validation comme réussie.
SELECT
    current_setting('gabriel.validation.result', true) AS overall_result,
    CASE
        WHEN current_setting('gabriel.validation.failures', true) = ''
            THEN 'Tous les contrôles fonctionnels et de permissions ont réussi.'
        ELSE current_setting('gabriel.validation.failures', true)
    END AS details,
    'Les tests administrateur ne valident pas RLS ; les rôles API sont testés séparément.' AS rls_scope;

ROLLBACK;
