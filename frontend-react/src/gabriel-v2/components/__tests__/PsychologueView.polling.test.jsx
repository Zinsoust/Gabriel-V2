/**
 * Cycle de vie d'une analyse : lancement, suivi, états dégradés, reprise.
 *
 * Le suivi d'analyse est la partie la plus risquée de la vue : elle boucle
 * pendant plusieurs minutes, survit à un rechargement de page, et doit
 * s'arrêter proprement quand l'utilisateur navigue ailleurs. Une boucle
 * fantôme y est invisible à l'œil nu mais consomme requêtes et batterie.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PsychologueView } from '../PsychologueView.jsx';
import CROSS from './fixtures/cross-salle-reelle.json';

const PENDING_JOB_KEY = 'gabriel_pending_job';

/** La saisie manuelle se choisit dans le sélecteur de source de la barre. */
async function choisirSaisieManuelle(user) {
  await user.click(screen.getByRole('button', { name: /Changer de source/ }));
  const menu = screen.getByRole('listbox', { name: 'Choisir une source' });
  await user.click(within(menu).getByRole('option', { name: 'Commentaires' }));
}

function jsonResponse(payload, ok = true) {
  return {
    ok,
    status: ok ? 200 : 500,
    redirected: false,
    url: 'http://localhost/x',
    text: async () => JSON.stringify(payload),
  };
}

/** Répond selon l'URL appelée, pour scripter un scénario complet. */
function routeFetch(routes) {
  return vi.fn(async (url) => {
    for (const [pattern, handler] of routes) {
      if (String(url).includes(pattern)) {
        const value = typeof handler === 'function' ? handler() : handler;
        return jsonResponse(value);
      }
    }
    throw new Error(`URL non scriptée : ${url}`);
  });
}

const RESULT = {
  analysis_id: 'a-1',
  meta: { total_commentaires: 150, commentaires_analyses: 40 },
  brief: { synthese: 'Une audience en quête de reconnaissance.' },
  dashboard: { positions: { favorable: { pct: 53, count: 78 } } },
  personas: [{ nom: 'Le Sceptique' }],
};

beforeEach(() => {
  window.localStorage.clear();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  cleanup();
});

describe('Suivi d’une analyse', () => {
  it('affiche le résultat quand le job aboutit', async () => {
    global.fetch = routeFetch([
      ['/analyze', () => ({ job_id: 'job-1' })],
      ['/status/', () => ({ status: 'done', data: RESULT })],
    ]);

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<PsychologueView workspace={null} />);
    await choisirSaisieManuelle(user);
    await user.type(screen.getByPlaceholderText(/Collez vos commentaires ici/), 'un\ndeux\ntrois');
    await user.click(screen.getByRole('button', { name: /Lancer l'analyse/ }));

    await vi.advanceTimersByTimeAsync(3500);
    await waitFor(() => {
      expect(screen.getByText(/Une audience en quête de reconnaissance/)).toBeInTheDocument();
    });
  });

  it('affiche un écran d’erreur quand le job échoue', async () => {
    global.fetch = routeFetch([
      ['/analyze', () => ({ job_id: 'job-2' })],
      ['/status/', () => ({ status: 'error', error: 'Le fournisseur est indisponible.' })],
    ]);

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<PsychologueView workspace={null} />);
    await choisirSaisieManuelle(user);
    await user.type(screen.getByPlaceholderText(/Collez vos commentaires ici/), 'un\ndeux\ntrois');
    await user.click(screen.getByRole('button', { name: /Lancer l'analyse/ }));

    await vi.advanceTimersByTimeAsync(3500);
    await waitFor(() => {
      expect(screen.getByText(/Le fournisseur est indisponible/)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Réessayer/ })).toBeInTheDocument();
  });

  it('traite un job interrompu par un redémarrage comme une erreur explicite', async () => {
    global.fetch = routeFetch([
      ['/analyze', () => ({ job_id: 'job-3' })],
      ['/status/', () => ({ status: 'interrupted', error: 'Analyse interrompue par un redémarrage du serveur.' })],
    ]);

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<PsychologueView workspace={null} />);
    await choisirSaisieManuelle(user);
    await user.type(screen.getByPlaceholderText(/Collez vos commentaires ici/), 'un\ndeux\ntrois');
    await user.click(screen.getByRole('button', { name: /Lancer l'analyse/ }));

    await vi.advanceTimersByTimeAsync(3500);
    await waitFor(() => {
      expect(screen.getByText(/interrompue par un redémarrage/)).toBeInTheDocument();
    });
  });
});

describe('Reprise après rechargement', () => {
  it('reprend le suivi d’un job encore en cours', async () => {
    window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify({ id: 'job-repris', t0: Date.now() }));
    global.fetch = routeFetch([
      ['/status/', () => ({ status: 'done', data: RESULT })],
    ]);

    render(<PsychologueView workspace={null} />);
    // Sans reprise, l'utilisateur retomberait sur un écran de saisie vide en
    // croyant son analyse perdue, alors qu'elle tourne encore côté serveur.
    expect(screen.getByText(/Gabriel analyse votre audience/)).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(3500);
    await waitFor(() => {
      expect(screen.getByText(/Une audience en quête de reconnaissance/)).toBeInTheDocument();
    });
  });

  it('oublie le job une fois le résultat obtenu', async () => {
    window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify({ id: 'job-fini', t0: Date.now() }));
    global.fetch = routeFetch([['/status/', () => ({ status: 'done', data: RESULT })]]);

    render(<PsychologueView workspace={null} />);
    await vi.advanceTimersByTimeAsync(3500);

    await waitFor(() => {
      // Un job terminé laissé en mémoire relancerait un suivi inutile à
      // chaque ouverture de la page.
      expect(window.localStorage.getItem(PENDING_JOB_KEY)).toBeNull();
    });
  });

  it('ne reprend rien quand aucun job n’est en attente', () => {
    global.fetch = vi.fn();
    render(<PsychologueView workspace={null} />);
    expect(screen.getByRole('button', { name: /Changer de source/ })).toBeInTheDocument();
    expect(screen.queryByText(/Gabriel analyse votre audience/)).not.toBeInTheDocument();
  });
});

describe('Arrêt du suivi', () => {
  it('cesse d’interroger le serveur après démontage du composant', async () => {
    const fetchMock = routeFetch([['/status/', () => ({ status: 'running', progress: 20 })]]);
    global.fetch = fetchMock;
    window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify({ id: 'job-zombie', t0: Date.now() }));

    const { unmount } = render(<PsychologueView workspace={null} />);
    await vi.advanceTimersByTimeAsync(3500);
    const callsBeforeUnmount = fetchMock.mock.calls.length;
    expect(callsBeforeUnmount).toBeGreaterThan(0);

    unmount();
    await vi.advanceTimersByTimeAsync(15000);

    // Une boucle de suivi qui survit au démontage continue d'appeler le
    // serveur en arrière-plan à chaque changement d'onglet.
    expect(fetchMock.mock.calls.length).toBe(callsBeforeUnmount);
  });
});


describe('Analyses longues : attente au temps réel', () => {
  async function avancer(secondes) {
    for (let i = 0; i < secondes / 3; i += 1) await vi.advanceTimersByTimeAsync(3000);
  }

  it('attend une Cross Analyse de plus de huit minutes (mesurée : plus de neuf)', async () => {
    window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify({ id: 'job-cross', crossId: CROSS.cross_analysis_id, t0: Date.now() }));
    let suivis = 0;
    global.fetch = vi.fn(async (url) => {
      if (String(url).endsWith('/status')) { suivis += 1; return jsonResponse({ status: suivis < 190 ? 'running' : 'completed', progress: 50 }); }
      return jsonResponse(CROSS);
    });
    render(<PsychologueView workspace={null} />);
    await avancer(190 * 3 + 6);                    // 9 min 30 : l'ancien plafond (160 suivis = 8 min) est dépassé
    expect(await screen.findByRole('heading', { name: 'Salle Cross' })).toBeInTheDocument();
    expect(screen.queryByText(/prend plus de temps que prévu/)).not.toBeInTheDocument();
  });

  it('attend une analyse simple de plus de huit minutes', async () => {
    window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify({ id: 'job-long', t0: Date.now() }));
    let suivis = 0;
    global.fetch = vi.fn(async () => { suivis += 1; return jsonResponse(suivis < 170 ? { status: 'running' } : { status: 'done', data: RESULT }); });
    render(<PsychologueView workspace={null} />);
    await avancer(170 * 3 + 6);
    expect(await screen.findByText(/Une audience en quête de reconnaissance/)).toBeInTheDocument();
  });

  it('supporte quelques coupures réseau pendant le suivi d’une analyse', async () => {
    window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify({ id: 'job-coupure', t0: Date.now() }));
    let suivis = 0;
    global.fetch = vi.fn(async () => { suivis += 1; if (suivis <= 3) throw new TypeError('Failed to fetch'); return jsonResponse({ status: 'done', data: RESULT }); });
    render(<PsychologueView workspace={null} />);
    await avancer(20);
    expect(await screen.findByText(/Une audience en quête de reconnaissance/)).toBeInTheDocument();
  });

  it('supporte quelques coupures réseau pendant le suivi d’une Cross Analyse', async () => {
    window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify({ id: 'job-cross-coupure', crossId: CROSS.cross_analysis_id, t0: Date.now() }));
    let suivis = 0;
    global.fetch = vi.fn(async (url) => {
      if (String(url).endsWith('/status')) { suivis += 1; if (suivis <= 3) throw new TypeError('Failed to fetch'); return jsonResponse({ status: 'completed' }); }
      return jsonResponse(CROSS);
    });
    render(<PsychologueView workspace={null} />);
    await avancer(24);
    expect(await screen.findByRole('heading', { name: 'Salle Cross' })).toBeInTheDocument();
  });

  it('annonce une connexion perdue au bout de plusieurs échecs, sans boucler indéfiniment', async () => {
    window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify({ id: 'job-perdu', t0: Date.now() }));
    const appels = vi.fn(async () => { throw new TypeError('Failed to fetch'); });
    global.fetch = appels;
    render(<PsychologueView workspace={null} />);
    await avancer(40);
    expect(await screen.findByText(/connexion au serveur est perdue/)).toBeInTheDocument();
    const avant = appels.mock.calls.length;
    await avancer(30);
    expect(appels.mock.calls.length).toBe(avant);
  });
});
