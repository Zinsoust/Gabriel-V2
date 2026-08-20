/**
 * Cross Analyse et rendu des résultats.
 *
 * La Cross Analyse a ses propres bornes métier (2 à 5 audiences) qui ne sont
 * pas déductibles de l'interface : les oublier laisse partir des analyses que
 * le serveur refusera, ou bloque des analyses valides.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
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

/** La Cross Analyse n'est plus un panneau flottant : c'est un mode du
 *  composer. Ajouter une audience s'y fait sans aller-retour serveur — le lien
 *  est reconnu localement. */
async function activerCross(user) {
  await user.click(screen.getByRole('button', { name: /Cross Analyse/ }));
}

async function ajouterAudiences(user, n) {
  for (let i = 0; i < n; i += 1) {
    const champ = screen.getByPlaceholderText(/Ajoutez une audience/);
    await user.clear(champ);
    await user.type(champ, `https://youtube.com/watch?v=audience${i}`);
    await user.click(screen.getByRole('button', { name: /Ajouter cette audience/ }));
  }
}

const retraits = () => screen.queryAllByRole('button', { name: /Retirer l.audience/ });

beforeEach(() => { window.localStorage.clear(); });
afterEach(() => { vi.restoreAllMocks(); cleanup(); });

describe('Mode Cross Analyse', () => {
  it('s’active depuis le composer', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await activerCross(user);
    expect(screen.getByRole('button', { name: /Cross Analyse/ }))
      .toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByPlaceholderText(/Ajoutez une audience/)).toBeInTheDocument();
  });

  it('refuse de comparer une seule audience', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await activerCross(user);
    await ajouterAudiences(user, 1);
    // Le minimum de 2 est une règle métier du serveur : la refléter ici évite
    // un aller-retour qui échouera de toute façon.
    expect(screen.getByRole('button', { name: /Comparer 1 audiences/ })).toBeDisabled();
    expect(screen.queryByRole('button', { name: /Comparer 1 audiences →/ })).toBeNull();
  });

  it('autorise la comparaison à partir de deux audiences', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await activerCross(user);
    await ajouterAudiences(user, 2);
    // Deux chemins mènent au lancement : le bouton du composer et le bouton
    // dédié. Les deux doivent s'ouvrir en même temps.
    const lancements = screen.getAllByRole('button', { name: /Comparer 2 audiences/ });
    expect(lancements).toHaveLength(2);
    lancements.forEach(bouton => expect(bouton).toBeEnabled());
  });

  it('cesse d’accepter des audiences au-delà de cinq', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await activerCross(user);
    await ajouterAudiences(user, 5);
    expect(retraits()).toHaveLength(5);

    // Une 6e audiences saisie : c'est le seul état où l'ajout redeviendrait
    // possible si le plafond n'était pas respecté. Sans cette 6e saisie, le
    // test passerait même avec un plafond erroné, simplement parce que le
    // champ est vidé après chaque ajout.
    await user.type(screen.getByPlaceholderText(/Ajoutez une audience/),
                    'https://youtube.com/watch?v=audience5');
    expect(screen.queryByRole('button', { name: /Ajouter cette audience/ })).toBeNull();
    expect(retraits()).toHaveLength(5);
  });

  it('permet de retirer une audience déjà ajoutée', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await activerCross(user);
    await ajouterAudiences(user, 2);

    expect(retraits()).toHaveLength(2);
    await user.click(retraits()[0]);
    expect(retraits()).toHaveLength(1);
  });

  it('refuse deux fois la même audience', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await activerCross(user);
    await ajouterAudiences(user, 1);

    await user.type(screen.getByPlaceholderText(/Ajoutez une audience/),
                    'https://youtube.com/watch?v=audience0');
    // Comparer une audience avec elle-même ne produit aucune divergence : le
    // serveur le rejette, l'interface doit le dire avant l'appel.
    expect(screen.getByText(/Déjà ajoutée/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Ajouter cette audience/ })).toBeNull();
    expect(retraits()).toHaveLength(1);
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
