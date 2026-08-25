/* Le retour terrain (« cette stratégie a-t-elle fonctionné ? ») était la
   seule chose de l'ancienne page « Mes stratégies » qu'on ne retrouvait nulle
   part ailleurs dans la V2 — le reste (ouvrir, avancement) existe déjà via
   les workspaces. Ces tests verrouillent ce retour terrain, pas l'affichage
   général déjà couvert par les autres tests du shell. */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Sidebar } from '../Sidebar.jsx';

const STRATEGIES = [
  { strategy_id: 's1', title: 'Lancement Q4', created_at: '2026-01-10T10:00:00Z', resultat: '', analysis_id: 'a1' },
  { strategy_id: 's2', title: 'Repositionnement prix', created_at: '2026-02-01T10:00:00Z', resultat: 'fonctionne', analysis_id: 'a2' },
];

function afficherPanneau(strategies = STRATEGIES) {
  global.fetch = vi.fn((url, options = {}) => {
    if (url === '/strategies') {
      return Promise.resolve({ status: 200, redirected: false, url: '/strategies', text: () => Promise.resolve(JSON.stringify(strategies)) });
    }
    return Promise.resolve({ status: 200, redirected: false, url, text: () => Promise.resolve('{}') });
  });
  render(<Sidebar workspaces={[]} activeTab="conversation" collapsed={false} onToggleCollapsed={vi.fn()} onSelectWorkspace={vi.fn()} onCreateWorkspace={vi.fn()} onDeleteWorkspace={vi.fn()} onSelectConversation={vi.fn()} onStartNewConversation={vi.fn()} onSelectAgent={vi.fn()} onToggleDarkMode={vi.fn()} onStartGuide={vi.fn()} />);
  return userEvent.setup();
}

beforeEach(() => cleanup());
afterEach(() => { delete global.fetch; });

describe('Panneau Stratégies : le retour terrain', () => {
  it('ouvre le panneau depuis la navigation', async () => {
    const user = await afficherPanneau();
    await user.click(screen.getAllByRole('button', { name: /Stratégies/ })[0]);
    await waitFor(() => expect(screen.getByText('Lancement Q4')).toBeInTheDocument());
  });

  it('affiche le total et le nombre ayant fonctionné, pas seulement le total', async () => {
    /* Sur les deux stratégies du jeu de test, une seule a fonctionné :
       compter le total ne dit rien sur ce qui marche vraiment. */
    const user = await afficherPanneau();
    await user.click(screen.getAllByRole('button', { name: /Stratégies/ })[0]);
    await waitFor(() => expect(screen.getByText('Lancement Q4')).toBeInTheDocument());
    const stats = document.querySelector('.gv2-strategy-stats');
    expect(within(stats).getByText('2')).toBeInTheDocument();
    expect(within(stats).getByText('1')).toBeInTheDocument();
    expect(screen.getByText('Repositionnement prix')).toBeInTheDocument();
  });

  it('signale déjà le résultat enregistré', async () => {
    const user = await afficherPanneau();
    await user.click(screen.getAllByRole('button', { name: /Stratégies/ })[0]);
    await waitFor(() => expect(screen.getByText('A fonctionné')).toBeInTheDocument());
  });

  it('envoie le retour terrain au clic, sans écran intermédiaire', async () => {
    const user = await afficherPanneau();
    await user.click(screen.getAllByRole('button', { name: /Stratégies/ })[0]);
    await waitFor(() => expect(screen.getByText('Lancement Q4')).toBeInTheDocument());
    await user.click(screen.getAllByRole('button', { name: 'Oui, elle a marché' })[0]);
    await waitFor(() => {
      const appel = global.fetch.mock.calls.find(([url]) => url === '/feedback');
      expect(appel).toBeTruthy();
      expect(JSON.parse(appel[1].body)).toMatchObject({ strategy_id: 's1', resultat: 'fonctionne' });
    });
  });

  it('invite à l’action quand aucune stratégie n’existe', async () => {
    const user = await afficherPanneau([]);
    await user.click(screen.getAllByRole('button', { name: /Stratégies/ })[0]);
    await waitFor(() => expect(screen.getByText(/Aucune stratégie sauvegardée/)).toBeInTheDocument());
  });

  it('supprime après confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = await afficherPanneau();
    await user.click(screen.getAllByRole('button', { name: /Stratégies/ })[0]);
    await waitFor(() => expect(screen.getByText('Lancement Q4')).toBeInTheDocument());
    await user.click(screen.getAllByRole('button', { name: /Supprimer cette stratégie/ })[0]);
    await waitFor(() => {
      const appel = global.fetch.mock.calls.find(([url]) => url === '/strategies/s1');
      expect(appel).toBeTruthy();
      expect(appel[1].method).toBe('DELETE');
    });
    window.confirm.mockRestore();
  });

  it('n’efface rien si l’utilisateur annule la suppression', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const user = await afficherPanneau();
    await user.click(screen.getAllByRole('button', { name: /Stratégies/ })[0]);
    await waitFor(() => expect(screen.getByText('Lancement Q4')).toBeInTheDocument());
    await user.click(screen.getAllByRole('button', { name: /Supprimer cette stratégie/ })[0]);
    expect(global.fetch.mock.calls.some(([url]) => url === '/strategies/s1')).toBe(false);
    window.confirm.mockRestore();
  });
});
