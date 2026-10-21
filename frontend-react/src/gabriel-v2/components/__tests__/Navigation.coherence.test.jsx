/* Menu de l'application cohérent avec le repositionnement : le Psychologue
   est l'accueil, chaque destination n'apparaît qu'une fois, les agents
   suivent la même hiérarchie que les onglets. */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Sidebar } from '../Sidebar.jsx';
import { WorkspaceTabs } from '../WorkspaceTabs.jsx';

function afficher(props = {}) {
  const handlers = { onStartAnalysis: vi.fn(), onStartNewConversation: vi.fn(), onSelectAgent: vi.fn(), onToggleCollapsed: vi.fn() };
  render(<Sidebar workspaces={[]} activeTab="psychologue" collapsed={false} onSelectWorkspace={vi.fn()} onCreateWorkspace={vi.fn()} onDeleteWorkspace={vi.fn()} onSelectConversation={vi.fn()} onToggleDarkMode={vi.fn()} onStartGuide={vi.fn()} {...handlers} {...props} />);
  return handlers;
}

describe('Menu latéral', () => {
  it('ramène l’accueil au Psychologue, pas à une conversation vide', async () => {
    const user = userEvent.setup();
    const { onStartAnalysis, onStartNewConversation } = afficher();
    const rail = screen.getByRole('navigation', { name: 'Navigation globale' });
    await user.click(within(rail).getByRole('button', { name: 'Accueil' }));
    expect(onStartAnalysis).toHaveBeenCalledTimes(1);
    expect(onStartNewConversation).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /Nouvelle analyse/ })).toBeInTheDocument();
  });

  it('ne répète pas l’Activité, déjà présente dans les onglets', () => {
    afficher();
    const rail = screen.getByRole('navigation', { name: 'Navigation globale' });
    expect(within(rail).queryByRole('button', { name: 'Activité' })).toBeNull();
  });

  it('présente les agents dans la hiérarchie des onglets', async () => {
    const user = userEvent.setup();
    afficher();
    const rail = screen.getByRole('navigation', { name: 'Navigation globale' });
    await user.click(within(rail).getByRole('button', { name: 'Agents' }));
    const libelles = screen.getAllByText(/PORTE D’ENTRÉE|PROLONGEMENTS/).map(n => n.textContent);
    expect(libelles).toEqual(['PORTE D’ENTRÉE', 'PROLONGEMENTS']);
    const noms = [...document.querySelectorAll('.gv2-agent-nav-row strong')].map(n => n.textContent);
    expect(noms).toEqual(['Psychologue', 'Ariane', 'Créateur']);
  });

  it('ouvre les espaces quand un ancien lien demande la section retirée', () => {
    afficher({ initialSection: 'activity' });
    expect(screen.getByRole('heading', { name: 'Espaces' })).toBeInTheDocument();
    expect(screen.getByText('VOS ESPACES')).toBeInTheDocument();
  });
});

describe('Onglets', () => {
  it('séparent comprendre, prolonger et suivre', () => {
    const onChange = vi.fn();
    render(<WorkspaceTabs currentTab="psychologue" onChange={onChange} />);
    const nav = screen.getByRole('navigation');
    const suite = [...nav.children].map(el => el.classList.contains('gv2-tabs-divider') ? '|' : el.textContent);
    expect(suite).toEqual(['Psychologue', '|', 'Ariane', 'Créateur', '|', 'Conversation', 'Activité', 'Mémoire']);
    expect(within(nav).queryByRole('button', { name: 'Prospect' })).toBeNull();
  });
});

describe('Menu : architecture multi-agents', () => {
  const HISTORIQUE = [
    { analysis_id: 'a-1', title: 'Lancement produit', source: 'YouTube', nb_commentaires: 115, created_at: '2026-09-13T01:30:00Z' },
    { analysis_id: 'a-2', title: 'Avis clients', source: 'Texte libre', nb_commentaires: 18, created_at: '2026-09-12T01:30:00Z' },
  ];
  beforeEach(() => {
    global.fetch = vi.fn(async () => ({ ok: true, status: 200, redirected: false, url: 'http://x', text: async () => JSON.stringify(HISTORIQUE) }));
  });

  it('présente les trois agents à l’accueil, le Psychologue comme agent principal', async () => {
    const user = userEvent.setup();
    const { onSelectAgent } = afficher();
    const rail = screen.getByRole('navigation', { name: 'Navigation globale' });
    await user.click(within(rail).getByRole('button', { name: 'Accueil' }));
    const noms = [...document.querySelectorAll('.gv2-agent-nav-row strong')].map(n => n.textContent);
    expect(noms).toEqual(['PsychologuePrincipal', 'Ariane', 'Créateur']);
    await user.click(screen.getByRole('button', { name: /Ariane/ }));
    expect(onSelectAgent).toHaveBeenCalledWith('stratege');
  });

  it('rouvre une analyse enregistrée depuis le panneau Analyses', async () => {
    const user = userEvent.setup();
    const onOpenAnalysis = vi.fn();
    afficher({ onOpenAnalysis });
    const rail = screen.getByRole('navigation', { name: 'Navigation globale' });
    await user.click(within(rail).getByRole('button', { name: 'Analyses' }));
    await user.type(screen.getByRole('textbox', { name: 'Rechercher une analyse' }), 'avis');
    expect(screen.queryByText('Lancement produit')).toBeNull();
    await user.click(await screen.findByRole('button', { name: /Avis clients/ }));
    expect(onOpenAnalysis).toHaveBeenCalledWith('a-2');
  });
});

describe('Menu : Cross Analyses', () => {
  const CROSS = [
    { cross_analysis_id: 'c-1', status: 'completed', created_at: '2026-09-14T10:00:00Z', sources: [{ title: 'IA locale' }, { title: 'IA pour débutants' }] },
    { cross_analysis_id: 'c-2', status: 'running', created_at: '2026-09-14T11:00:00Z', sources: [{ title: 'Vidéo en cours' }, { title: 'Autre' }] },
  ];
  beforeEach(() => {
    global.fetch = vi.fn(async (adresse) => ({ ok: true, status: 200, redirected: false, url: 'http://x',
      text: async () => JSON.stringify(String(adresse).includes('cross-analyses') ? { success: true, cross_analyses: CROSS } : []) }));
  });

  it('liste les comparaisons et rouvre celle qu’on choisit', async () => {
    const user = userEvent.setup();
    const onOpenCross = vi.fn();
    afficher({ onOpenCross });
    const rail = screen.getByRole('navigation', { name: 'Navigation globale' });
    await user.click(within(rail).getByRole('button', { name: 'Cross Analyses' }));
    await user.click(await screen.findByRole('button', { name: /IA locale × IA pour débutants/ }));
    expect(onOpenCross).toHaveBeenCalledWith('c-1');
    expect(screen.getByRole('button', { name: /Vidéo en cours/ })).toBeDisabled();
  });
});
