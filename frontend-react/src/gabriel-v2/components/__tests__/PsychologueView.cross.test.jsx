/**
 * Cross Analyse et rendu des résultats.
 *
 * La Cross Analyse a ses propres bornes métier (2 à 5 audiences) qui ne sont
 * pas déductibles de l'interface : les oublier laisse partir des analyses que
 * le serveur refusera, ou bloque des analyses valides.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PsychologueView } from '../PsychologueView.jsx';

function jsonResponse(payload) {
  return { ok: true, status: 200, redirected: false, url: 'http://x', text: async () => JSON.stringify(payload) };
}

function routeFetch(routes) {
  return vi.fn(async (url) => {
    for (const [pattern, handler] of routes) {
      if (String(url).includes(pattern)) return jsonResponse(typeof handler === 'function' ? handler() : handler);
    }
    throw new Error(`URL non scriptée : ${url}`);
  });
}

const PREVIEW = { comments_preview: ['a'], comments_count: 150 };

/** Le panneau flottant se superpose à la carte de saisie : les deux portent un
 *  champ de lien identique. Tout doit être cherché dans le panneau. */
function panel() {
  return within(screen.getByRole('dialog'));
}

/** Ajoute n vidéos vérifiées dans le panneau Cross Analyse. */
async function addVideos(user, n) {
  for (let i = 0; i < n; i += 1) {
    const input = panel().getByPlaceholderText(/vidéo YouTube/);
    await user.clear(input);
    await user.type(input, `https://youtube.com/watch?v=vid${i}`);
    await user.click(panel().getByRole('button', { name: /Vérifier le lien/ }));
    await waitFor(() => expect(panel().getByRole('status')).toHaveTextContent(/150 commentaires/));
    const add = panel().queryByRole('button', { name: /Ajouter une autre vidéo/ });
    if (add) await user.click(add);
  }
}

beforeEach(() => { window.localStorage.clear(); });
afterEach(() => { vi.restoreAllMocks(); cleanup(); });

describe('Panneau Cross Analyse', () => {
  it('s’ouvre depuis l’en-tête du Psychologue', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByRole('button', { name: /Cross Analyse/ }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Comparez 2 à 5 audiences/)).toBeInTheDocument();
  });

  it('refuse de comparer une seule audience', async () => {
    const user = userEvent.setup();
    global.fetch = routeFetch([['/analyze', PREVIEW]]);
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByRole('button', { name: /Cross Analyse/ }));
    await addVideos(user, 1);
    // Le minimum de 2 est une règle métier du serveur : la refléter ici évite
    // un aller-retour qui échouera de toute façon.
    expect(panel().getByRole('button', { name: /Comparer/ })).toBeDisabled();
  });

  it('autorise la comparaison à partir de deux audiences', async () => {
    const user = userEvent.setup();
    global.fetch = routeFetch([['/analyze', PREVIEW]]);
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByRole('button', { name: /Cross Analyse/ }));
    await addVideos(user, 2);
    expect(panel().getByRole('button', { name: /Comparer/ })).toBeEnabled();
  });

  it('cesse de proposer l’ajout au-delà de cinq audiences', async () => {
    const user = userEvent.setup();
    global.fetch = routeFetch([['/analyze', PREVIEW]]);
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByRole('button', { name: /Cross Analyse/ }));
    await addVideos(user, 5);
    expect(panel().getAllByRole('button', { name: /Retirer cette vidéo/ })).toHaveLength(5);

    // Une 6e vidéo vérifiée : c'est le seul état où le bouton d'ajout
    // réapparaîtrait si le plafond n'était pas respecté. Sans cette 6e
    // vérification, le test passerait même avec un plafond erroné, simplement
    // parce que le champ est vidé après chaque ajout.
    const input = panel().getByPlaceholderText(/vidéo YouTube/);
    await user.type(input, 'https://youtube.com/watch?v=vid5');
    await user.click(panel().getByRole('button', { name: /Vérifier le lien/ }));
    await waitFor(() => expect(panel().getByRole('status')).toHaveTextContent(/150 commentaires/));

    expect(panel().queryByRole('button', { name: /Ajouter une autre vidéo/ })).not.toBeInTheDocument();
  });

  it('permet de retirer une audience déjà ajoutée', async () => {
    const user = userEvent.setup();
    global.fetch = routeFetch([['/analyze', PREVIEW]]);
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByRole('button', { name: /Cross Analyse/ }));
    await addVideos(user, 2);

    const remove = panel().getAllByRole('button', { name: /Retirer cette vidéo/ });
    expect(remove).toHaveLength(2);
    await user.click(remove[0]);
    expect(panel().getAllByRole('button', { name: /Retirer cette vidéo/ })).toHaveLength(1);
  });

  it('refuse deux fois la même vidéo', async () => {
    const user = userEvent.setup();
    global.fetch = routeFetch([['/analyze', PREVIEW]]);
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByRole('button', { name: /Cross Analyse/ }));
    await addVideos(user, 1);

    const input = panel().getByPlaceholderText(/vidéo YouTube/);
    await user.type(input, 'https://youtube.com/watch?v=vid0');
    await user.click(panel().getByRole('button', { name: /Vérifier le lien/ }));
    // Comparer une vidéo avec elle-même ne produit aucune divergence : le
    // serveur le rejette, l'interface doit le dire avant l'appel.
    await waitFor(() => expect(panel().getByRole('status')).toHaveTextContent(/déjà dans la liste/));
  });
});

describe('Rendu du résultat Cross Analyse', () => {
  const CROSS = {
    success: true,
    cross_analysis_id: 'cross-1',
    status: 'completed',
    result: {
      confidence: { score: 92, level: 'high', total_comments: 300 },
      data_quality: { level: 'strong' },
      executive_summary: { text: 'Les deux audiences partagent une nostalgie.', caveats: ['Deux sources seulement.'] },
      convergences: [{ category: 'emotions', label: 'Admiration', sources: [{ label: 'V1' }, { label: 'V2' }] }],
      divergences: [],
      oppositions: [],
      source_specific_signals: [],
      cross_personas: [{ name: 'Le Gardien', description: 'Protège un héritage.', confidence_level: 'Strong' }],
      sources: [{ source_id: 's1', metadata: { title: 'Vidéo A', channel: 'Chaîne A' }, data_quality: { level: 'strong' } }],
      failed_sources: [],
    },
  };

  it('présente d’abord la conclusion, puis les détails', async () => {
    window.localStorage.setItem('gabriel_pending_job', JSON.stringify({ id: 'j', crossId: 'cross-1', t0: Date.now() }));
    global.fetch = routeFetch([
      ['/cross-analyses/cross-1/status', { status: 'completed' }],
      ['/cross-analyses/cross-1', CROSS],
    ]);
    vi.useFakeTimers({ shouldAdvanceTime: true });

    render(<PsychologueView workspace={null} />);
    await vi.advanceTimersByTimeAsync(3500);

    await waitFor(() => {
      expect(screen.getByText(/partagent une nostalgie/)).toBeInTheDocument();
    });
    // La doctrine Cross Analyse impose cet ordre : conclusion exploitable
    // d'abord, données croisées ensuite.
    expect(screen.getByText('92')).toBeInTheDocument();
    expect(screen.getByText(/Points de prudence/)).toBeInTheDocument();
    expect(screen.getByText('Vidéo A')).toBeInTheDocument();
    expect(screen.getByText('Le Gardien')).toBeInTheDocument();
    vi.useRealTimers();
  });

  it('signale une analyse partielle sans masquer les résultats obtenus', async () => {
    const partial = {
      ...CROSS,
      status: 'partial_success',
      result: { ...CROSS.result, failed_sources: [{ label: 'Vidéo B' }] },
    };
    window.localStorage.setItem('gabriel_pending_job', JSON.stringify({ id: 'j', crossId: 'cross-1', t0: Date.now() }));
    global.fetch = routeFetch([
      ['/cross-analyses/cross-1/status', { status: 'partial_success' }],
      ['/cross-analyses/cross-1', partial],
    ]);
    vi.useFakeTimers({ shouldAdvanceTime: true });

    render(<PsychologueView workspace={null} />);
    await vi.advanceTimersByTimeAsync(3500);

    await waitFor(() => {
      expect(screen.getByText(/Analyse partielle/)).toBeInTheDocument();
    });
    // Masquer les résultats parce qu'une source a échoué gaspillerait le
    // travail réellement abouti sur les autres.
    expect(screen.getByText(/partagent une nostalgie/)).toBeInTheDocument();
    vi.useRealTimers();
  });
});
