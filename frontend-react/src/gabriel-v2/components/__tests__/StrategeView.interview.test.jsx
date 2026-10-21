/* Tranche B du Stratège natif : l'entretien textuel qui construit le
   contexte business depuis zéro. Le contrat est documenté dans
   docs/interview_frontend_contract.md — le frontend ne déduit aucun fait
   business et ne recalcule pas la complétude, il affiche ce que le serveur
   renvoie. Ces tests vérifient le fil de la conversation, pas une logique
   métier qui n'existe pas côté client. */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrategeView } from '../StrategeView.jsx';

const WORKSPACE = { folder_id: 'f-1', analysis_id: '', strategy_id: '' };

function routeFetch(routes) {
  return vi.fn((url, options = {}) => {
    for (const [pattern, handler] of routes) {
      if (typeof pattern === 'string' ? url === pattern : pattern.test(url)) {
        const body = handler(url, options);
        return Promise.resolve({ status: body.status || 200, ok: (body.status || 200) < 400, redirected: false, url,
          text: () => Promise.resolve(JSON.stringify(body.json)) });
      }
    }
    throw new Error(`Route non simulée : ${url}`);
  });
}

const OUVERTURE = { messages: [{ role: 'assistant', content: 'Parlez-moi de votre entreprise.' }],
  context_progress: { understood: [], remaining: ['Identité', 'Offre'] }, is_ready: false, updated_context: {} };

beforeEach(() => { cleanup(); try { window.sessionStorage.clear(); } catch (_) {} });
afterEach(() => { delete global.fetch; });

describe('Ouverture de l’entretien', () => {
  it('ne rouvre pas une session déjà chargée quand le dossier se re-résout au même endroit', async () => {
    /* Le bootstrap (workspace.folder_id/strategy_id/analysis_id) peut se
       redéclencher — un rafraîchissement de workspace, par exemple — et
       retomber sur le même stage 'interview'. Sans le garde-fou sur
       messages déjà chargés, chaque redéclenchement rouvrirait une
       session et dupliquerait la conversation affichée. */
    let appels = 0;
    global.fetch = routeFetch([[/^\/business-context/, () => { appels += 1; return { json: OUVERTURE }; }]]);
    const { rerender } = render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => expect(screen.getByText('Parlez-moi de votre entreprise.')).toBeInTheDocument());
    expect(appels).toBe(1);
    // Le dossier change de valeur (donc l'effet se redéclenche réellement),
    // tout en retombant sur le même stage 'interview'.
    rerender(<StrategeView workspace={{ ...WORKSPACE, folder_id: 'f-2' }} />);
    await waitFor(() => expect(screen.getByText('Parlez-moi de votre entreprise.')).toBeInTheDocument());
    expect(appels).toBe(1);
  });

  it('remonte « déjà compris » et « à éclaircir » tels que renvoyés par le serveur, pour le panneau de contexte', async () => {
    /* Depuis l'habillage Ariane, la progression ne s'affiche plus en ligne
       dans le fil (voir ContextPanel.jsx, panneau partagé monté par
       AppShell) — StrategeView se contente de la remonter fidèlement via
       onInterviewChange, sans rien recalculer lui-même. */
    global.fetch = routeFetch([[/^\/business-context/, () => ({ json: OUVERTURE })]]);
    const onInterviewChange = vi.fn();
    render(<StrategeView workspace={WORKSPACE} onInterviewChange={onInterviewChange} />);
    await waitFor(() => expect(onInterviewChange).toHaveBeenCalledWith(
      expect.objectContaining({ contextProgress: { understood: [], remaining: ['Identité', 'Offre'] } }),
    ));
  });
});

describe('Tour de conversation', () => {
  it('envoie le message et affiche la réponse structurée du serveur', async () => {
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: OUVERTURE })],
      [/^\/context-chat$/, () => ({ json: {
        reply: { display_text: 'Merci — et votre cible principale ?', state: 'waiting_for_answer' },
        context_progress: { understood: ['Identité'], remaining: ['Offre'] }, is_ready: false, updated_context: { role_utilisateur: 'Coach' } } })],
    ]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByPlaceholderText('Écrivez votre réponse…'));
    await user.type(screen.getByPlaceholderText('Écrivez votre réponse…'), 'Je suis coach business{Enter}');
    await waitFor(() => expect(screen.getByText('Merci — et votre cible principale ?')).toBeInTheDocument());
    expect(screen.getByText('Je suis coach business')).toBeInTheDocument();
    const appel = global.fetch.mock.calls.find(([url]) => url === '/context-chat');
    expect(JSON.parse(appel[1].body)).toEqual({ message: 'Je suis coach business' });
  });

  it('affiche l’observation et la dimension réellement renvoyées par le serveur', async () => {
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: OUVERTURE })],
      [/^\/context-chat$/, () => ({ json: {
        reply: {
          display_text: 'Votre cible est claire. Précisons maintenant votre vision.',
          strategic_observation: 'Votre offre est déjà compréhensible ; sa promesse doit encore être plus spécifique.',
        },
        current_dimension: 'Vision',
        context_progress: { understood: ['Identité'], remaining: ['Vision', 'Offre'] },
        is_ready: false,
        updated_context: { role_utilisateur: 'Coach' },
      } })],
    ]);
    const user = userEvent.setup();
    const onInterviewChange = vi.fn();
    render(<StrategeView workspace={WORKSPACE} onInterviewChange={onInterviewChange} />);
    await waitFor(() => screen.getByPlaceholderText('Écrivez votre réponse…'));
    await user.type(screen.getByPlaceholderText('Écrivez votre réponse…'), 'Je suis coach{Enter}');
    await waitFor(() => expect(screen.getByText('Observation stratégique')).toBeInTheDocument());
    expect(screen.getByText('Votre offre est déjà compréhensible ; sa promesse doit encore être plus spécifique.')).toBeInTheDocument();
    expect(onInterviewChange).toHaveBeenCalledWith(expect.objectContaining({ currentDimension: 'Vision' }));
  });

  it('ne propose « Générer la stratégie » qu’une fois is_ready', async () => {
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: OUVERTURE })],
      [/^\/context-chat$/, () => ({ json: { reply: { display_text: 'J’ai assez de contexte.', state: 'completed' },
        context_progress: { understood: ['Identité', 'Offre'], remaining: [] }, is_ready: true, updated_context: { offre: 'Coaching' } } })],
    ]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByPlaceholderText('Écrivez votre réponse…'));
    expect(screen.queryByRole('button', { name: /Générer mon diagnostic/ })).toBeNull();
    await user.type(screen.getByPlaceholderText('Écrivez votre réponse…'), 'Coaching business{Enter}');
    await waitFor(() => expect(screen.getByRole('button', { name: /Générer mon diagnostic/ })).toBeInTheDocument());
  });

  it('n’envoie rien pour un message vide', async () => {
    global.fetch = routeFetch([[/^\/business-context/, () => ({ json: OUVERTURE })]]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByPlaceholderText('Écrivez votre réponse…'));
    await user.type(screen.getByPlaceholderText('Écrivez votre réponse…'), '   {Enter}');
    expect(global.fetch).toHaveBeenCalledTimes(1); // seulement l'ouverture
  });
});

describe('Génération depuis l’entretien', () => {
  it('envoie le contexte accumulé, sans analyse liée', async () => {
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: { ...OUVERTURE, is_ready: true, updated_context: { offre: 'Coaching' } } })],
      [/^\/strategize$/, () => ({ json: { success: true, strategy_id: 'nouvelle-strat', decision_centrale: 'Se positionner premium' } })],
    ]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByRole('button', { name: /Générer mon diagnostic/ }));
    await user.click(screen.getByRole('button', { name: /Générer mon diagnostic/ }));
    await waitFor(() => expect(screen.getByText('Se positionner premium')).toBeInTheDocument());
    const appel = global.fetch.mock.calls.find(([url]) => url === '/strategize');
    const body = JSON.parse(appel[1].body);
    expect(body.context).toEqual({ offre: 'Coaching' });
    expect(body.analysis_id).toBeUndefined();
  });

  it('transmet immédiatement l’identifiant de la stratégie créée à Thomas', async () => {
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: { ...OUVERTURE, is_ready: true, updated_context: { offre: 'Coaching' } } })],
      [/^\/strategize$/, () => ({ json: { success: true, strategy_id: 'nouvelle-strat', decision_centrale: 'Décision fraîche' } })],
    ]);
    const onNavigateAgent = vi.fn();
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} onNavigateAgent={onNavigateAgent} />);
    await waitFor(() => screen.getByRole('button', { name: /Générer mon diagnostic/ }));
    await user.click(screen.getByRole('button', { name: /Générer mon diagnostic/ }));
    await waitFor(() => screen.getByText('Le Créateur →'));
    await user.click(screen.getByText('Le Créateur →'));
    expect(onNavigateAgent).toHaveBeenCalledWith('createur', {
      source: 'stratege', folder_id: 'f-1', strategy_id: 'nouvelle-strat',
    });
  });

  it('bascule en flux classique quand une analyse Psychologue a été transmise', async () => {
    try {
      window.sessionStorage.setItem('gabriel_for_stratege', JSON.stringify({
        schema_version: 1, created_at: Date.now(), analysis_id: 'a-transmise', folder_id: 'f-1',
        psycho_brief: 'Audience en quête de structure.', psycho_data: {} }));
    } catch (_) {}
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: { ...OUVERTURE, is_ready: true, updated_context: { offre: 'Coaching' } } })],
      [/^\/strategize$/, () => ({ json: { job_id: 'st_1' } })],
      [/^\/status\/st_1$/, () => ({ json: { status: 'done', data: { data: { strategie: { decision_centrale: 'Décision liée' } }, strategy_id: 'x' } } })],
    ]);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByRole('button', { name: /Générer mon diagnostic/ }));
    await user.click(screen.getByRole('button', { name: /Générer mon diagnostic/ }));
    await vi.advanceTimersByTimeAsync(3100);
    await waitFor(() => expect(screen.getByText('Décision liée')).toBeInTheDocument());
    const appel = global.fetch.mock.calls.find(([url]) => url === '/strategize');
    const body = JSON.parse(appel[1].body);
    expect(body.analysis_id).toBe('a-transmise');
    expect(body.brain_profile).toEqual({ offre: 'Coaching' });
    vi.useRealTimers();
  });

  it('affiche la bannière quand une analyse Psychologue a été transmise', async () => {
    try {
      window.sessionStorage.setItem('gabriel_for_stratege', JSON.stringify({
        schema_version: 1, created_at: Date.now(), analysis_id: 'a-2', folder_id: 'f-1', psycho_brief: 'x', psycho_data: {},
      }));
    } catch (_) {}
    global.fetch = routeFetch([[/^\/business-context/, () => ({ json: OUVERTURE })]]);
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => expect(screen.getByText(/Analyse Psychologue détectée/)).toBeInTheDocument());
  });

  it('ignore et consomme un handoff Psychologue périmé', async () => {
    window.sessionStorage.setItem('gabriel_for_stratege', JSON.stringify({
      schema_version: 1, created_at: Date.now() - 11 * 60 * 1000,
      analysis_id: 'a-old', folder_id: 'f-1', psycho_brief: 'ancien',
    }));
    global.fetch = routeFetch([[/^\/business-context/, () => ({ json: OUVERTURE })]]);
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => expect(screen.getByText('Parlez-moi de votre entreprise.')).toBeInTheDocument());
    expect(screen.queryByText(/Analyse Psychologue détectée/)).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem('gabriel_for_stratege')).toBeNull();
  });

  it('ignore un handoff Psychologue d’un autre dossier', async () => {
    window.sessionStorage.setItem('gabriel_for_stratege', JSON.stringify({
      schema_version: 1, created_at: Date.now(), analysis_id: 'a-other', folder_id: 'f-other', psycho_brief: 'autre',
    }));
    global.fetch = routeFetch([[/^\/business-context/, () => ({ json: OUVERTURE })]]);
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => expect(screen.getByText('Parlez-moi de votre entreprise.')).toBeInTheDocument());
    expect(screen.queryByText(/Analyse Psychologue détectée/)).not.toBeInTheDocument();
  });
});
