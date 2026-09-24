/**
 * Salle Cross — sur une vraie Cross Analyse (deux vidéos YouTube réelles,
 * synthèse sémantique vérifiée). On ne fusionne jamais les audiences : chaque
 * affirmation dit à qui elle s'applique, et chaque audience garde son analyse
 * complète, consultable sans quitter la Salle.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PsychologueView } from '../PsychologueView.jsx';
import CROSS from './fixtures/cross-salle-reelle.json';
import ANALYSE_A from './fixtures/psychologue-analyse-youtube.json';

const R = CROSS.result;
const S = R.cross_synthesis;
const [A, B] = R.source_profiles;

function ouvrir(extra = {}) {
  global.fetch = vi.fn(async (adresse) => {
    const url = String(adresse);
    let corps = [];
    if (url.includes('/cross-analyses/')) corps = CROSS;
    else if (url.includes(`/history/${A.analysis_id}/load`)) corps = { full_result: { ...ANALYSE_A, analysis_id: A.analysis_id } };
    else if (url.includes(`/history/${B.analysis_id}/load`)) corps = { full_result: { ...ANALYSE_A, analysis_id: B.analysis_id, brief: { ...ANALYSE_A.brief, qui: 'Audience B : des débutants qui veulent comprendre les bases' } } };
    return { ok: true, status: 200, redirected: false, url: 'http://x', text: async () => JSON.stringify(corps) };
  });
  const user = userEvent.setup();
  const onNavigateAgent = extra.onNavigateAgent || vi.fn();
  render(<PsychologueView workspace={{ folder_id: 'dossier-7' }} openAnalysisRequest={{ crossId: CROSS.cross_analysis_id, at: 1 }} onNavigateAgent={onNavigateAgent} {...extra} />);
  return user;
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); window.sessionStorage.clear(); });

describe('Salle Cross', () => {
  it('ouvre sur la synthèse croisée avec les deux audiences identifiées', async () => {
    ouvrir();
    expect(await screen.findByRole('heading', { name: 'Salle Cross' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: new RegExp(`Ouvrir l’audience A · ${A.title.slice(0, 20)}`) })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: new RegExp(`Ouvrir l’audience B · ${B.title.slice(0, 15)}`) })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Synthèse croisée' })).toHaveAttribute('aria-selected', 'true');
    expect(document.querySelector('.gv2-cross-verdict-text').textContent).toContain(S.verdict.rassemble.replace(/\*/g, '').slice(0, 40));
    expect(screen.getByText('Points de prudence')).toBeInTheDocument();
  });

  it('dit ce qui les rassemble, avec le signal réel de chaque audience', async () => {
    const user = ouvrir();
    await user.click(await screen.findByRole('tab', { name: 'Ce qui les rassemble' }));
    const premier = S.rassemble[0];
    const lignes = [...document.querySelectorAll('.gv2-cross-row')];
    const ligne = lignes.find(l => l.querySelector('.gv2-cross-row-body > p').textContent.startsWith(premier.label.replace(/\*/g, '')));
    expect(within(ligne).getByText('Commun')).toBeInTheDocument();
    // Pas de doublon : le même point n'apparaît qu'une fois comme ligne.
    expect(lignes.filter(l => l.querySelector('.gv2-cross-row-body > p').textContent.startsWith(premier.label.replace(/\*/g, '')))).toHaveLength(1);
    expect(ligne.querySelectorAll('blockquote')).toHaveLength(premier.per_source.length);
  });

  it('distingue ce qui est propre à une audience de ce qui les oppose', async () => {
    const user = ouvrir();
    await user.click(await screen.findByRole('tab', { name: 'Ce qui les sépare' }));
    const oppose = S.separe.find(s => s.kind === 'oppose');
    const ligne = screen.getByText(oppose.label.replace(/\*/g, '')).closest('.gv2-cross-row');
    expect(within(ligne).getByText('Opposé')).toBeInTheDocument();
    expect(screen.getByText('Signaux propres à une seule audience')).toBeInTheDocument();
  });

  it('n’affiche jamais les identifiants internes de signaux ni de titres collés', async () => {
    const user = ouvrir();
    await user.click(await screen.findByRole('tab', { name: 'Ce qui les rassemble' }));
    expect(document.body.textContent).not.toMatch(/\(cross:/);
    await user.click(screen.getByRole('tab', { name: 'Ce qui les sépare' }));
    expect(document.body.textContent).not.toMatch(/\(cross:/);
    // Le titre de l'audience est un bloc à part, pas un suffixe de pastille insécable.
    const titres = [...document.querySelectorAll('.gv2-cross-own-title')].map(t => t.textContent);
    expect(titres).toContain(A.title);
  });

  it('fait de la Cross Analyse ouverte le contexte du Créateur', async () => {
    const onAnalysisReady = vi.fn();
    global.fetch = vi.fn(async () => ({ ok: true, status: 200, redirected: false, url: 'http://x', text: async () => JSON.stringify(CROSS) }));
    render(<PsychologueView workspace={null} openAnalysisRequest={{ crossId: CROSS.cross_analysis_id, at: 1 }} onNavigateAgent={vi.fn()} onAnalysisReady={onAnalysisReady} />);
    await screen.findByRole('heading', { name: 'Salle Cross' });
    expect(onAnalysisReady).toHaveBeenCalledWith(expect.objectContaining({ id: CROSS.cross_analysis_id, cross: true, title: expect.stringContaining(A.title.slice(0, 20)) }));
  });

  it('montre la carte dimension par audience sans mots vides', async () => {
    const user = ouvrir();
    await user.click(await screen.findByRole('tab', { name: 'Carte des audiences' }));
    const table = screen.getByRole('table');
    const entetes = within(table).getAllByRole('columnheader').map(th => th.textContent);
    expect(entetes[1]).toContain(A.title.slice(0, 20));
    expect(entetes[2]).toContain(B.title.slice(0, 15));
    expect(within(table).getByRole('rowheader', { name: 'Peurs' })).toBeInTheDocument();
    expect(within(table).queryByText('merci')).toBeNull();
  });

  it('propose des sujets, des centres d’intérêt, ce qu’il faut éviter et un message commun', async () => {
    const user = ouvrir();
    await user.click(await screen.findByRole('tab', { name: 'Sujets & angles' }));
    expect(screen.getByText('Sujets qui résolvent un problème commun')).toBeInTheDocument();
    expect(screen.getByText(S.sujets_qui_resolvent[0].title.replace(/\*/g, ''))).toBeInTheDocument();
    expect(screen.getByText('À éviter')).toBeInTheDocument();
    expect(screen.getByText('Un message pour toutes ces audiences')).toBeInTheDocument();
  });

  it('ouvre le détail d’une audience, passe à l’autre et revient à la synthèse', async () => {
    const user = ouvrir();
    await user.click(await screen.findByRole('button', { name: /Ouvrir l’audience A/ }));
    expect(await screen.findByText('Place dans la comparaison')).toBeInTheDocument();
    expect(await screen.findByText(ANALYSE_A.brief.qui.replace(/\*/g, '').slice(0, 30), { exact: false })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Synthèse' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: new RegExp(`^Audience B · `) }));
    expect(await screen.findByText(/Audience B : des débutants/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '← Synthèse croisée' }));
    expect(screen.getByRole('tab', { name: 'Synthèse croisée' })).toHaveAttribute('aria-selected', 'true');
  });

  it('transmet la Cross Analyse à Ariane : identifiant de la Cross et résumé des audiences', async () => {
    const onNavigateAgent = vi.fn();
    const user = ouvrir({ onNavigateAgent });
    await user.click(await screen.findByRole('tab', { name: 'Sujets & angles' }));
    await user.click(screen.getByRole('button', { name: /Construire la stratégie · Ariane/ }));

    const passage = JSON.parse(window.sessionStorage.getItem('gabriel_for_stratege'));
    expect(passage.analysis_id).toBe(CROSS.cross_analysis_id);       // pas l'analyse d'une seule audience
    expect(passage.folder_id).toBe('dossier-7');
    expect(passage.psycho_brief).toContain(`Audiences comparées : A = ${A.title}`);
    expect(passage.psycho_brief).toContain(`B = ${B.title}`);
    expect(passage.psycho_brief).toContain('Ce qui les rassemble');
    expect(passage.psycho_brief).toContain('Ce qui les sépare');
    expect(passage.psycho_brief).not.toContain('**');
    expect(onNavigateAgent).toHaveBeenCalledWith('stratege');
  });

  it('depuis le détail d’une audience, Ariane et le Créateur reçoivent l’analyse de cette audience', async () => {
    const onNavigateAgent = vi.fn();
    const onAnalysisReady = vi.fn();
    const user = ouvrir({ onNavigateAgent, onAnalysisReady });
    await user.click(await screen.findByRole('button', { name: /Ouvrir l’audience A/ }));
    await screen.findByText('Place dans la comparaison');

    await user.click(screen.getAllByRole('button', { name: /Construire la stratégie →/ })[0]);
    expect(JSON.parse(window.sessionStorage.getItem('gabriel_for_stratege')).analysis_id).toBe(A.analysis_id);
    expect(onNavigateAgent).toHaveBeenCalledWith('stratege');

    onAnalysisReady.mockClear();
    await user.click(screen.getAllByRole('tab').at(-1));                    // « Passer au Créateur » ferme la lecture, sur le dernier onglet
    await user.click(screen.getByRole('button', { name: /Passer au Créateur →/ }));
    expect(onAnalysisReady).toHaveBeenCalledWith({ id: A.analysis_id, title: A.title });
    expect(onNavigateAgent).toHaveBeenCalledWith('createur');
  });
});
