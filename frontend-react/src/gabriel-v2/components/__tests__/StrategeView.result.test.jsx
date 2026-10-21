/* Tranche A du Stratège natif : reprise d'une stratégie déjà enregistrée,
   génération classique depuis une analyse Psychologue, rapport à 5 sections
   (habillage « Ariane » — document déroulant avec sommaire, plus d'onglets
   à cliquer, mêmes données réelles). L'entretien conversationnel et la
   couche vocale sont hors périmètre de cette tranche — leur absence doit se
   voir honnêtement à l'écran, pas être masquée. */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrategeView } from '../StrategeView.jsx';

const WORKSPACE_NEW = { folder_id: 'f-1', analysis_id: 'a-1', strategy_id: '' };
const WORKSPACE_DONE = { folder_id: 'f-2', analysis_id: 'a-2', strategy_id: 's-2' };
const WORKSPACE_EMPTY = { folder_id: 'f-3', analysis_id: '', strategy_id: '' };

/* Forme réelle : le champ synthèse/marketing/branding/plan/décision d'une
   stratégie, telle que renvoyée par gabriel.run_stratege (voir
   app.py:/strategize) — vérifiée en lisant templates/stratege.html. */
const STRATEGIE = {
  executive_decision: { one_sentence_decision: 'Lancer une offre premium ciblée sur les indépendants pressés.',
    what_to_do_this_week: 'Publier le premier post de positionnement.', confidence_score: 0.82,
    expected_business_impact: '+30% de conversions en 60 jours' },
  audience_psychology_used: { main_problem: 'Manque de temps', main_desire: 'Liberté',
    main_fear: 'Échouer seul', decision_drivers: ['preuve sociale', 'urgence'] },
  value_to_create: { core_value: 'Un système clé en main', why_this_value_matters: 'Ils veulent aller vite' },
  message_central: 'Arrêtez de tout faire seul.',
  offre_recommandee: { nom: 'Accélérateur Solo', cible_precise: 'Consultants indépendants',
    livrables: ['Audit initial', 'Plan 90 jours'], prix_recommande: '1 490 €',
    canaux_acquisition: ['LinkedIn', 'Email'], objections_a_traiter: ['Trop cher'] },
  pricing_logic: { fourchette: '900 € – 1 900 €', valeur_percue: 'Élevée', justification: 'Marché premium' },
  immediate_monetization_plan: { next_24h_action: 'Publier une offre limitée', next_7_days_action: 'Contacter 10 prospects' },
  opportunites_marche: [{ recommandation: 'Cibler les créateurs solo', signal: 'Forte demande de structure' }],
  social_media_decision: { best_platform: 'LinkedIn', first_post_or_video_to_create: 'Témoignage client' },
  strategie_contenu: { format_prioritaire: 'Carrousel', frequence: '3x/semaine', sujets_a_eviter: ['Politique'] },
  recommandations_prioritaires: [{ action: 'Clarifier l’offre', signal_source: 'Confusion des prospects', impact: 'Fort', delai: '7 jours' }],
  plan_90_jours: { phase_1: { titre: 'Fondations', periode: 'Semaines 1-4', objectifs: ['Positionner l’offre'],
    taches: ['Écrire la page de vente'], kpis: ['10 prospects qualifiés'] } },
  critique_strategique: { verdict: 'Solide', point_faible_principal: 'Dépendance à un seul canal',
    confidence_score_independant: 0.7 },
  risques: [{ risque: 'Saturation du canal LinkedIn', mitigation: 'Diversifier vers l’email' }],
  indicateurs_succes: ['Taux de réponse', 'Coût par lead'],
  questions_a_clarifier: ['Quel budget publicitaire mensuel ?'],
};

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

beforeEach(() => cleanup());
afterEach(() => { delete global.fetch; vi.useRealTimers(); });

describe('Reprise d’une stratégie déjà enregistrée', () => {
  it('affiche directement le tableau de bord', async () => {
    global.fetch = routeFetch([
      [/^\/strategies\/s-2$/, () => ({ json: { success: true, strategy_result: STRATEGIE } })],
    ]);
    render(<StrategeView workspace={WORKSPACE_DONE} />);
    await waitFor(() => expect(screen.getByText(/Lancer une offre premium/)).toBeInTheDocument());
    expect(screen.getByRole('heading', { name: 'Synthèse' })).toBeInTheDocument();
  });
});

describe('Génération classique depuis une analyse existante', () => {
  it('propose de générer, puis affiche le résultat après le job', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    global.fetch = routeFetch([
      [/^\/strategize$/, () => ({ json: { job_id: 'st_123' } })],
      [/^\/status\/st_123$/, () => ({ json: { status: 'done', data: { data: { strategie: STRATEGIE }, strategy_id: 'new-id' } } })],
    ]);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<StrategeView workspace={WORKSPACE_NEW} />);
    await waitFor(() => expect(screen.getByText('Une analyse est disponible pour ce dossier')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Générer la stratégie' }));
    await vi.advanceTimersByTimeAsync(3100);
    await waitFor(() => expect(screen.getByText(/Lancer une offre premium/)).toBeInTheDocument());
  });

  it('affiche les champs manquants renvoyés par le serveur, sans deviner', async () => {
    global.fetch = routeFetch([
      [/^\/strategize$/, () => ({ status: 400, json: { error: 'Contexte insuffisant',
        missing_fields: [{ field: 'offre', label: 'votre offre principale' }] } })],
    ]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE_NEW} />);
    await waitFor(() => screen.getByRole('button', { name: 'Générer la stratégie' }));
    await user.click(screen.getByRole('button', { name: 'Générer la stratégie' }));
    await waitFor(() => expect(screen.getByText('votre offre principale')).toBeInTheDocument());
    expect(screen.getByText('Votre profil business est incomplet')).toBeInTheDocument();
  });

  it('affiche une erreur de crédits sans planter', async () => {
    global.fetch = routeFetch([
      [/^\/strategize$/, () => ({ status: 402, json: { error: 'credits_insufficient', cost: 5, credits: 2 } })],
    ]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE_NEW} />);
    await waitFor(() => screen.getByRole('button', { name: 'Générer la stratégie' }));
    await user.click(screen.getByRole('button', { name: 'Générer la stratégie' }));
    await waitFor(() => expect(screen.getByText(/Il vous faut 5 crédits/)).toBeInTheDocument());
  });
});

describe('Aucun déclencheur disponible : l’entretien démarre directement', () => {
  it('ouvre l’entretien plutôt que de dériver vers un écran mort', async () => {
    /* Sans analyse ni stratégie, l'ancienne page allait déjà directement à
       l'entretien (loadBusinessContext) — la Tranche A y renvoyait un
       message honnête faute d'entretien construit ; la Tranche B le
       remplace par le vrai entretien. */
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: { messages: [{ role: 'assistant', content: 'Parlez-moi de votre activité.' }],
        context_progress: { understood: [], remaining: ['Identité'] }, is_ready: false, updated_context: {} } })],
    ]);
    render(<StrategeView workspace={WORKSPACE_EMPTY} />);
    await waitFor(() => expect(screen.getByText('Parlez-moi de votre activité.')).toBeInTheDocument());
    expect(screen.getByPlaceholderText('Écrivez votre réponse…')).toBeInTheDocument();
  });
});

describe('Rapport : chaque bloc disparaît s’il est vide', () => {
  it('n’affiche pas une section dont aucun champ n’est fourni', async () => {
    global.fetch = routeFetch([
      [/^\/strategies\/s-2$/, () => ({ json: { success: true, strategy_result: { decision_centrale: 'x' } } })],
    ]);
    render(<StrategeView workspace={WORKSPACE_DONE} />);
    await waitFor(() => expect(screen.getByText('x')).toBeInTheDocument());
    // Le rapport rend désormais toutes les sections à la suite (plus
    // d'onglets à ouvrir un par un) : un bloc vide doit rester absent
    // partout dans le document, pas seulement hors d'un onglet fermé.
    expect(screen.queryByText('Offre recommandée')).toBeNull();
    expect(screen.queryByText('Regard critique · 2ᵉ avis indépendant')).toBeNull();
  });

  it('affiche le plan 90 jours avec ses objectifs, tâches et KPIs', async () => {
    global.fetch = routeFetch([
      [/^\/strategies\/s-2$/, () => ({ json: { success: true, strategy_result: STRATEGIE } })],
    ]);
    render(<StrategeView workspace={WORKSPACE_DONE} />);
    await waitFor(() => expect(screen.getByText('Fondations')).toBeInTheDocument());
    expect(screen.getByText('Positionner l’offre')).toBeInTheDocument();
    expect(screen.getByText('10 prospects qualifiés')).toBeInTheDocument();
  });
});

describe('Passerelle vers Le Créateur', () => {
  it('propose de continuer vers Le Créateur une fois la stratégie prête', async () => {
    global.fetch = routeFetch([
      [/^\/strategies\/s-2$/, () => ({ json: { success: true, strategy_result: STRATEGIE } })],
    ]);
    const onNavigateAgent = vi.fn();
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE_DONE} onNavigateAgent={onNavigateAgent} />);
    await waitFor(() => screen.getByText('Le Créateur →'));
    await user.click(screen.getByText('Le Créateur →'));
    expect(onNavigateAgent).toHaveBeenCalledWith('createur', {
      source: 'stratege', folder_id: 'f-2', strategy_id: 's-2',
    });
  });
});
