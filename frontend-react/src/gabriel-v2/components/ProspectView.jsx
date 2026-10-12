import React, { useMemo, useRef, useState } from 'react';
import { Icon } from '../icons.jsx';
import { fetchV2, isLoginResponse, readApiPayload } from '../api-client.js';

const MAX_FILE_BYTES = 2 * 1024 * 1024;

const FIELD_LABELS = {
  company_name: 'Entreprise',
  website: 'Site web',
  domain: 'Domaine',
  agency_type: "Type d’agence",
  services: 'Prestations',
  market_type: 'Marché déclaré',
  employee_count: 'Effectif',
  country: 'Pays',
  city: 'Ville',
  contact_first_name: 'Prénom du contact',
  contact_last_name: 'Nom du contact',
  contact_full_name: 'Contact',
  job_title: 'Fonction',
  email: 'Email professionnel',
  phone: 'Téléphone',
  linkedin_url: 'Profil LinkedIn',
};

const CRITERION_LABELS = {
  agency_type: "Type d’agence pertinent",
  services_fit: 'Prestations en adéquation',
  decision_maker: 'Fonction décisionnaire',
  employee_count: 'Effectif cible',
  geography: 'Zone géographique',
  professional_channel: 'Canal professionnel',
};

function fieldLabel(field) {
  return FIELD_LABELS[field] || field || 'Information';
}

function criterionLabel(criterion) {
  return CRITERION_LABELS[criterion] || criterion || 'Critère';
}

function displayValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  if (value === null || value === undefined || value === '') return 'Non renseigné';
  return String(value);
}

function prospectName(prospect) {
  return prospect?.data?.company_name || prospect?.data?.domain || `Ligne ${prospect?.source_row || 'inconnue'}`;
}

function contactName(data = {}) {
  return data.contact_full_name
    || [data.contact_first_name, data.contact_last_name].filter(Boolean).join(' ')
    || 'Contact non renseigné';
}

function scoreTotal(prospect) {
  const value = Number(prospect?.score?.total);
  return Number.isFinite(value) ? value : 0;
}

function duplicateLabel(duplicate) {
  if (!duplicate) return 'Aucun signal';
  if (duplicate.kind === 'exact') return 'Exact';
  if (duplicate.kind === 'possible') return 'Possible';
  return 'Signalé';
}

function Summary({ preview }) {
  const summary = preview?.summary || {};
  const count = Number(summary.rows_received) || 0;
  return <section className="gv2-prospect-summary" aria-label="Résumé de l’import">
    <div><span>Import</span><strong>{count}</strong><small>{count > 1 ? 'prospects analysés' : 'prospect analysé'}</small></div>
    <div><span>Préparation</span><strong>{Number(summary.contact_eligible) || 0}</strong><small>contacts éligibles</small></div>
    <div><span>À vérifier</span><strong>{Number(summary.contact_ineligible) || 0}</strong><small>contacts non éligibles</small></div>
    <div><span>Doublons</span><strong>{(Number(summary.exact_duplicates) || 0) + (Number(summary.possible_duplicates) || 0)}</strong><small>signaux détectés</small></div>
  </section>;
}

function ProspectDetail({ prospect }) {
  const criteria = Array.isArray(prospect?.score?.criteria) ? prospect.score.criteria : [];
  const facts = Array.isArray(prospect?.facts) ? prospect.facts : [];
  const unknowns = Array.isArray(prospect?.unknowns) ? prospect.unknowns : [];
  const validationErrors = Array.isArray(prospect?.validation_errors) ? prospect.validation_errors : [];
  const blockingReasons = Array.isArray(prospect?.eligibility?.blocking_reasons)
    ? prospect.eligibility.blocking_reasons
    : [];

  return <section className="gv2-prospect-detail" role="region" aria-label={`Détail de ${prospectName(prospect)}`}>
    <div className="gv2-prospect-detail-grid">
      <section>
        <header><p>Score ICP</p><strong>{scoreTotal(prospect)} / {prospect?.score?.maximum || 100}</strong></header>
        <div className="gv2-prospect-criteria">
          {criteria.map((criterion, index) => <article key={`${criterion.criterion || 'criterion'}-${index}`} className={`is-${criterion.status || 'unknown'}`}>
            <div>
              <span>{criterionLabel(criterion.criterion)}</span>
              <strong>{Number(criterion.points) || 0} / {Number(criterion.weight) || 0}</strong>
            </div>
            <p>{criterion.explanation || 'Aucune explication fournie.'}</p>
          </article>)}
        </div>
      </section>

      <section>
        <header><p>Déclarations importées</p><span className="gv2-prospect-unverified">Déclaré · non vérifié</span></header>
        {facts.length ? <dl className="gv2-prospect-facts">
          {facts.map((fact, index) => <div key={fact.fact_id || `${fact.field}-${index}`}>
            <dt>{fieldLabel(fact.field)}</dt>
            <dd>{displayValue(fact.value)}<small>Colonne « {fact.source_column || fieldLabel(fact.field)} »</small></dd>
          </div>)}
        </dl> : <p className="gv2-prospect-detail-empty">Aucune déclaration exploitable.</p>}
      </section>
    </div>

    <div className="gv2-prospect-review-grid">
      <section>
        <h3>Informations manquantes</h3>
        {unknowns.length
          ? <ul>{unknowns.map(field => <li key={field}>{fieldLabel(field)}</li>)}</ul>
          : <p>Aucune information canonique manquante.</p>}
      </section>
      <section>
        <h3>Vérifications nécessaires</h3>
        {validationErrors.length || blockingReasons.length
          ? <ul>
            {validationErrors.map((error, index) => <li key={`validation-${error.code || index}`}>{error.message || error.code}</li>)}
            {blockingReasons
              .filter(reason => !validationErrors.some(error => error.code === reason.code))
              .map((reason, index) => <li key={`blocking-${reason.code || index}`}>{reason.message || reason.code}</li>)}
          </ul>
          : <p>Aucune erreur bloquante détectée. Une validation humaine reste requise.</p>}
      </section>
      <section>
        <h3>Hypothèses</h3>
        <p>{prospect?.hypotheses?.length ? `${prospect.hypotheses.length} hypothèse(s) séparée(s) du score.` : 'Aucune hypothèse ajoutée au score.'}</p>
      </section>
    </div>
  </section>;
}

export function ProspectView() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState('');
  const [expandedRows, setExpandedRows] = useState(() => new Set());
  const [minimumScore, setMinimumScore] = useState('0');
  const [eligibilityFilter, setEligibilityFilter] = useState('all');
  const [duplicateFilter, setDuplicateFilter] = useState('all');

  const prospects = Array.isArray(preview?.prospects) ? preview.prospects : [];
  const filteredProspects = useMemo(() => {
    const minimum = Math.max(0, Math.min(100, Number(minimumScore) || 0));
    return prospects.filter(prospect => {
      if (scoreTotal(prospect) < minimum) return false;
      const eligible = prospect?.eligibility?.eligible_for_contact_preparation === true;
      if (eligibilityFilter === 'eligible' && !eligible) return false;
      if (eligibilityFilter === 'ineligible' && eligible) return false;
      const duplicateKind = prospect?.duplicate?.kind || 'none';
      if (duplicateFilter !== 'all' && duplicateKind !== duplicateFilter) return false;
      return true;
    });
  }, [prospects, minimumScore, eligibilityFilter, duplicateFilter]);

  function chooseFile(event) {
    const nextFile = event.target.files?.[0] || null;
    setFile(nextFile);
    setError('');
  }

  async function submitImport(event) {
    event.preventDefault();
    setError('');
    if (!file) {
      setError('Sélectionnez un fichier CSV à analyser.');
      return;
    }
    if (!file.name.toLocaleLowerCase('fr-FR').endsWith('.csv')) {
      setError('Le fichier doit utiliser le format CSV.');
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setError('Le fichier dépasse la limite de 2 Mo.');
      return;
    }

    setStatus('loading');
    try {
      const body = new FormData();
      body.append('file', file);
      const response = await fetchV2('/api/v2/prospects/imports/preview', {
        method: 'POST',
        body,
      });
      if (isLoginResponse(response)) {
        window.location.assign('/login');
        return;
      }
      const payload = await readApiPayload(response, 'Gabriel Prospect');
      if (!response.ok || payload?.success !== true) {
        throw new Error(payload?.error || "L’import n’a pas pu être analysé.");
      }
      if (!payload.preview || !Array.isArray(payload.preview.prospects)) {
        throw new Error('Gabriel Prospect a renvoyé une prévisualisation invalide.');
      }
      setPreview(payload.preview);
      setExpandedRows(new Set());
      setMinimumScore('0');
      setEligibilityFilter('all');
      setDuplicateFilter('all');
      setStatus('success');
    } catch (requestError) {
      setPreview(null);
      setStatus('error');
      setError(requestError?.message || "L’import n’a pas pu être analysé.");
    }
  }

  function toggleRow(row) {
    setExpandedRows(current => {
      const next = new Set(current);
      if (next.has(row)) next.delete(row); else next.add(row);
      return next;
    });
  }

  const total = prospects.length;
  const visible = filteredProspects.length;
  const resultCountLabel = `${visible} prospect${visible > 1 ? 's' : ''} affiché${visible > 1 ? 's' : ''} sur ${total}`;

  return <section className="gv2-prospect-view">
    <header className="gv2-prospect-hero">
      <div>
        <p className="gv2-prospect-kicker">Acquisition interne</p>
        <h1>Gabriel Prospect</h1>
        <p>Importez, normalisez et qualifiez jusqu’à 1 000 prospects avec le moteur ICP déterministe de Gabriel.</p>
      </div>
      <span className="gv2-prospect-local-badge"><Icon name="check" size={14} />Traitement local, sans IA</span>
    </header>

    <aside className="gv2-prospect-disclaimer">
      <Icon name="file" size={20} />
      <p><strong>Données déclaratives issues du CSV.</strong> Elles ne sont pas vérifiées indépendamment. Le score mesure l’adéquation à l’ICP, pas la véracité des déclarations. Aucun message n’est envoyé.</p>
    </aside>

    <form className="gv2-prospect-import" onSubmit={submitImport} noValidate>
      <div className="gv2-prospect-import-copy">
        <span><Icon name="briefcase" size={21} /></span>
        <div><h2>Prévisualiser un import CSV</h2><p>2 Mo maximum · 1 000 lignes · aucun fichier brut conservé</p></div>
      </div>
      <div className="gv2-prospect-file-actions">
        <input ref={inputRef} className="gv2-prospect-file-input" type="file" accept=".csv,text/csv" aria-label="Fichier CSV de prospects" onChange={chooseFile} />
        <button className="gv2-prospect-file-button" type="button" onClick={() => inputRef.current?.click()}><Icon name="paperclip" size={16} />{file ? 'Changer de CSV' : 'Choisir un CSV'}</button>
        <span className="gv2-prospect-file-name" title={file?.name || ''}>{file?.name || 'Aucun fichier sélectionné'}</span>
        <button className="gv2-prospect-submit" type="submit" disabled={!file || status === 'loading'}>
          {status === 'loading' ? <><span className="gv2-prospect-spinner" aria-hidden="true" />Analyse en cours…</> : <><Icon name="search" size={16} />Analyser le CSV</>}
        </button>
      </div>
    </form>

    {error && <p className="gv2-prospect-error" role="alert"><Icon name="close" size={17} />{error}</p>}
    {status === 'loading' && <p className="gv2-prospect-loading" role="status">Lecture, normalisation, déduplication et calcul des scores…</p>}

    {!preview && status !== 'loading'
      ? <section className="gv2-prospect-empty"><Icon name="briefcase" size={28} /><h2>Votre qualification apparaîtra ici</h2><p>Aucun prospect n’est affiché avant l’analyse du fichier sélectionné.</p></section>
      : null}

    {preview && <>
      <Summary preview={preview} />
      <section className="gv2-prospect-results" aria-label="Résultats de qualification">
        <header className="gv2-prospect-results-head">
          <div><h2>Prospects qualifiés</h2><p>{resultCountLabel}</p></div>
          <div className="gv2-prospect-filters" aria-label="Filtres des prospects">
            <label>Score ICP minimum<input aria-label="Score ICP minimum" type="number" min="0" max="100" value={minimumScore} onChange={event => setMinimumScore(event.target.value)} /></label>
            <label>Éligibilité commerciale<select aria-label="Éligibilité commerciale" value={eligibilityFilter} onChange={event => setEligibilityFilter(event.target.value)}><option value="all">Toutes</option><option value="eligible">Éligibles</option><option value="ineligible">Non éligibles</option></select></label>
            <label>Doublons<select aria-label="Doublons" value={duplicateFilter} onChange={event => setDuplicateFilter(event.target.value)}><option value="all">Tous</option><option value="none">Sans doublon</option><option value="exact">Exacts</option><option value="possible">Possibles</option></select></label>
          </div>
        </header>

        {filteredProspects.length ? <div className="gv2-prospect-table-wrap">
          <table className="gv2-prospect-table" aria-label="Prospects qualifiés">
            <thead><tr><th>Entreprise</th><th>Secteur</th><th>Contact</th><th>Score ICP</th><th>Validation</th><th>Doublon</th><th><span className="gv2-visually-hidden">Détail</span></th></tr></thead>
            <tbody>{filteredProspects.map(prospect => {
              const row = prospect.source_row;
              const isExpanded = expandedRows.has(row);
              const eligible = prospect?.eligibility?.eligible_for_contact_preparation === true;
              const validationCount = Array.isArray(prospect.validation_errors) ? prospect.validation_errors.length : 0;
              return <React.Fragment key={row}>
                <tr>
                  <td><strong>{prospectName(prospect)}</strong><small>Ligne {row}</small></td>
                  <td>{prospect?.data?.agency_type || 'Non renseigné'}</td>
                  <td><strong>{contactName(prospect?.data)}</strong><small>{prospect?.data?.job_title || 'Fonction non renseignée'}</small></td>
                  <td><span className={`gv2-prospect-score is-${scoreTotal(prospect) >= 75 ? 'high' : scoreTotal(prospect) >= 50 ? 'medium' : 'low'}`}>{scoreTotal(prospect)} / {prospect?.score?.maximum || 100}</span></td>
                  <td><span className={`gv2-prospect-status ${eligible ? 'is-eligible' : 'is-ineligible'}`}>{eligible ? 'Éligible à préparer' : 'Non éligible'}</span>{validationCount > 0 && <small>{validationCount} anomalie{validationCount > 1 ? 's' : ''}</small>}</td>
                  <td><span className={`gv2-prospect-duplicate is-${prospect?.duplicate?.kind || 'none'}`}>{duplicateLabel(prospect?.duplicate)}</span>{prospect?.duplicate?.matched_row && <small>Avec ligne {prospect.duplicate.matched_row}</small>}</td>
                  <td><button className="gv2-prospect-detail-button" type="button" onClick={() => toggleRow(row)} aria-expanded={isExpanded} aria-label={`${isExpanded ? 'Masquer' : 'Voir'} le détail de ${prospectName(prospect)}`}><Icon name="chevronDown" size={17} /></button></td>
                </tr>
                {isExpanded && <tr className="gv2-prospect-detail-row"><td colSpan="7"><ProspectDetail prospect={prospect} /></td></tr>}
              </React.Fragment>;
            })}</tbody>
          </table>
        </div> : <div className="gv2-prospect-filter-empty"><Icon name="search" size={22} /><p>Aucun prospect ne correspond aux filtres sélectionnés.</p></div>}
      </section>
    </>}
  </section>;
}
