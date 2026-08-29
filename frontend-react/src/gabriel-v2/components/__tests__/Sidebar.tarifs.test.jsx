/* Lien direct vers /tarifs dans la barre latérale, en plus de celui déjà
   présent dans le menu du compte (AppShell.jsx) — demandé pour qu'il reste
   accessible sans ouvrir de menu. /tarifs est une page publique et reste en
   V1 (décidé plus tôt dans ce chantier : elle doit s'afficher aux visiteurs
   non connectés, que le shell V2 ne peut pas servir) — c'est donc un lien de
   navigation directe, pas un onglet interne. */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { Sidebar } from '../Sidebar.jsx';

function afficher() {
  global.fetch = vi.fn(() => Promise.resolve({ status: 200, redirected: false, url: '', text: () => Promise.resolve('{}') }));
  render(<Sidebar workspaces={[]} activeTab="conversation" collapsed={false} onToggleCollapsed={vi.fn()} onSelectWorkspace={vi.fn()} onCreateWorkspace={vi.fn()} onDeleteWorkspace={vi.fn()} onSelectConversation={vi.fn()} onStartNewConversation={vi.fn()} onSelectAgent={vi.fn()} onToggleDarkMode={vi.fn()} onStartGuide={vi.fn()} />);
}

beforeEach(() => cleanup());
afterEach(() => { delete global.fetch; });

describe('Lien Tarifs dans la barre latérale', () => {
  it('pointe vers /tarifs, toujours visible sans ouvrir de menu', () => {
    afficher();
    const lien = screen.getByRole('link', { name: 'Voir les tarifs' });
    expect(lien).toHaveAttribute('href', '/tarifs');
  });
});
