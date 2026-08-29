/* Bouton Tarifs dans la barre latérale — ouvre l'écran natif V2 (TarifsView),
   pas l'ancienne page /tarifs. Cette dernière reste servie par Flask, mais
   uniquement pour les visiteurs non connectés (décidé plus tôt dans ce
   chantier) — un utilisateur déjà dans le shell ne doit plus jamais y être
   renvoyé : avant ce changement, le bouton menait à une page au thème forcé
   sombre, sans lien visuel avec le reste de l'app. */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Sidebar } from '../Sidebar.jsx';

function afficher(activeTab = 'conversation') {
  global.fetch = vi.fn(() => Promise.resolve({ status: 200, redirected: false, url: '', text: () => Promise.resolve('{}') }));
  const onSelectAgent = vi.fn();
  render(<Sidebar workspaces={[]} activeTab={activeTab} collapsed={false} onToggleCollapsed={vi.fn()} onSelectWorkspace={vi.fn()} onCreateWorkspace={vi.fn()} onDeleteWorkspace={vi.fn()} onSelectConversation={vi.fn()} onStartNewConversation={vi.fn()} onSelectAgent={onSelectAgent} onToggleDarkMode={vi.fn()} onStartGuide={vi.fn()} />);
  return { onSelectAgent, user: userEvent.setup() };
}

beforeEach(() => cleanup());
afterEach(() => { delete global.fetch; });

describe('Bouton Tarifs dans la barre latérale', () => {
  it('ouvre l’écran natif au clic, pas une navigation externe', async () => {
    const { onSelectAgent, user } = afficher();
    const bouton = screen.getByRole('button', { name: 'Voir les tarifs' });
    expect(bouton).not.toHaveAttribute('href');
    await user.click(bouton);
    expect(onSelectAgent).toHaveBeenCalledWith('tarifs');
  });

  it('se marque actif quand l’écran Tarifs est ouvert', () => {
    afficher('tarifs');
    expect(screen.getByRole('button', { name: 'Voir les tarifs' })).toHaveAttribute('aria-pressed', 'true');
  });
});
