import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProspectView } from '../ProspectView.jsx';

const prospect = ({
  row,
  company,
  score,
  eligible = true,
  duplicate = null,
  unknowns = [],
  validationErrors = [],
}) => ({
  source_row: row,
  data: {
    company_name: company,
    agency_type: 'Agence branding',
    services: 'Identité de marque',
    contact_full_name: `Contact ${row}`,
    contact_first_name: 'Contact',
    contact_last_name: String(row),
    job_title: 'Fondatrice',
    email: `contact${row}@example.test`,
    linkedin_url: null,
  },
  sources: [{
    source_id: `csv-row-${row}`,
    type: 'csv_import',
    filename: 'agences.csv',
    row,
    verification: 'not_independently_verified',
  }],
  facts: [{
    fact_id: `csv-row-${row}:company_name`,
    field: 'company_name',
    value: company,
    status: 'declared_unverified',
    source_id: `csv-row-${row}`,
    source_column: 'Entreprise',
  }],
  hypotheses: [],
  unknowns,
  validation_errors: validationErrors,
  score: {
    total: score,
    maximum: 100,
    icp_name: 'Agences B2B cibles Gabriel',
    icp_version: '1.0',
    criteria: [{
      criterion: 'agency_type',
      weight: 25,
      points: 25,
      matched: true,
      status: 'matched',
      explanation: "Le type d'agence déclaré correspond à la cible.",
      fact_ids: [`csv-row-${row}:agency_type`],
    }],
  },
  duplicate,
  eligibility: {
    eligible_for_contact_preparation: eligible,
    status: eligible ? 'eligible' : 'ineligible',
    blocking_reasons: eligible ? [] : [{ code: 'missing_professional_channel', message: 'Aucun canal professionnel valide.' }],
    requires_human_review: true,
    assessment_basis: 'declared_unverified_data',
  },
});

const preview = {
  import: {
    filename: 'agences.csv',
    size_bytes: 412,
    persisted: false,
  },
  summary: {
    rows_received: 3,
    rows_valid: 2,
    rows_with_errors: 1,
    exact_duplicates: 1,
    possible_duplicates: 0,
    contact_eligible: 1,
    contact_ineligible: 2,
  },
  prospects: [
    prospect({ row: 2, company: 'Studio Nord', score: 100 }),
    prospect({
      row: 3,
      company: 'Atelier Rivage',
      score: 65,
      eligible: false,
      unknowns: ['linkedin_url'],
      validationErrors: [{ field: 'email', code: 'invalid_email', message: "L'email est invalide.", blocking: true }],
    }),
    prospect({
      row: 4,
      company: 'Studio Nord bis',
      score: 85,
      eligible: false,
      duplicate: { kind: 'exact', matched_row: 2, reason: 'Même email normalisé.' },
    }),
  ],
};

function jsonResponse(payload, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    redirected: false,
    url: 'http://localhost/api/v2/prospects/imports/preview',
    text: async () => JSON.stringify(payload),
  };
}

async function uploadAndSubmit(user, file = new File(['Entreprise\nStudio Nord\n'], 'agences.csv', { type: 'text/csv' })) {
  await user.upload(screen.getByLabelText('Fichier CSV de prospects'), file);
  await user.click(screen.getByRole('button', { name: 'Analyser le CSV' }));
}

describe('Gabriel Prospect', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => jsonResponse({ success: true, preview }));
  });

  it('présente un import vide sans inventer de prospect et rappelle la provenance déclarative', () => {
    render(<ProspectView />);

    expect(screen.getByRole('heading', { name: 'Gabriel Prospect' })).toBeInTheDocument();
    expect(screen.getByText(/données déclaratives issues du CSV/i)).toBeInTheDocument();
    expect(screen.getByText(/ne sont pas vérifiées indépendamment/i)).toBeInTheDocument();
    expect(screen.getByText(/aucun prospect n’est affiché avant l’analyse/i)).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('envoie le fichier au véritable endpoint en multipart puis affiche uniquement la réponse', async () => {
    const user = userEvent.setup();
    render(<ProspectView />);

    await uploadAndSubmit(user);

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/v2/prospects/imports/preview');
    expect(options.method).toBe('POST');
    expect(options.credentials).toBe('same-origin');
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.get('file')).toBeInstanceOf(File);
    expect(options.headers).not.toHaveProperty('Content-Type');

    const table = await screen.findByRole('table', { name: 'Prospects qualifiés' });
    expect(within(table).getByText('Studio Nord')).toBeInTheDocument();
    expect(within(table).getByText('100 / 100')).toBeInTheDocument();
    expect(within(table).getByText('Éligible à préparer')).toBeInTheDocument();
    const summary = screen.getByRole('region', { name: 'Résumé de l’import' });
    expect(within(summary).getByText('3')).toBeInTheDocument();
    expect(within(summary).getByText('prospects analysés')).toBeInTheDocument();
  });

  it('affiche les critères, déclarations, erreurs bloquantes et inconnues sans les qualifier de faits vérifiés', async () => {
    const user = userEvent.setup();
    render(<ProspectView />);
    await uploadAndSubmit(user);

    await user.click(await screen.findByRole('button', { name: /Voir le détail de Atelier Rivage/ }));

    const detail = screen.getByRole('region', { name: 'Détail de Atelier Rivage' });
    expect(within(detail).getByText("Le type d'agence déclaré correspond à la cible.")).toBeInTheDocument();
    expect(within(detail).getByText('Déclaré · non vérifié')).toBeInTheDocument();
    expect(within(detail).getByText("L'email est invalide.")).toBeInTheDocument();
    expect(within(detail).getByText('Profil LinkedIn')).toBeInTheDocument();
    expect(within(detail).queryByText(/fait vérifié/i)).toBeNull();
  });

  it('filtre par score, éligibilité et doublon sans modifier les scores reçus', async () => {
    const user = userEvent.setup();
    render(<ProspectView />);
    await uploadAndSubmit(user);

    await user.clear(screen.getByLabelText('Score ICP minimum'));
    await user.type(screen.getByLabelText('Score ICP minimum'), '80');
    expect(screen.queryByText('Atelier Rivage')).toBeNull();
    expect(screen.getByText('Studio Nord bis')).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Éligibilité commerciale'), 'ineligible');
    await user.selectOptions(screen.getByLabelText('Doublons'), 'exact');
    expect(screen.queryByText('Studio Nord')).toBeNull();
    expect(screen.getByText('Studio Nord bis')).toBeInTheDocument();
    expect(screen.getByText('1 prospect affiché sur 3')).toBeInTheDocument();
  });

  it('refuse localement un fichier trop volumineux sans requête réseau', async () => {
    const user = userEvent.setup();
    render(<ProspectView />);
    const oversized = new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'trop-grand.csv', { type: 'text/csv' });

    await uploadAndSubmit(user, oversized);

    expect(await screen.findByRole('alert')).toHaveTextContent('2 Mo');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('rend les erreurs du backend sans exposer le contenu du fichier', async () => {
    global.fetch = vi.fn(async () => jsonResponse({
      success: false,
      error: 'Le fichier contient plus de 1 000 lignes.',
      error_code: 'too_many_rows',
    }, { ok: false, status: 400 }));
    const user = userEvent.setup();
    render(<ProspectView />);

    await uploadAndSubmit(user);

    expect(await screen.findByRole('alert')).toHaveTextContent('plus de 1 000 lignes');
    expect(screen.queryByText('Studio Nord')).toBeNull();
  });
});
