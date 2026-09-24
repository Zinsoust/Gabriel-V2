/**
 * Navigation sur téléphone. Sous 640 px, le menu latéral et la barre des agents étaient
 * masqués par le CSS sans autre moyen de naviguer (constaté à l'audit du 24/09/2026) :
 * on ne pouvait pas quitter le premier écran. Un bouton ouvre désormais le menu en tiroir.
 *
 * (jsdom n'applique pas les media queries : ces tests vérifient le comportement — ouverture,
 * fermeture, focus — et le CSS est contrôlé en vrai dans le navigateur.)
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppShell } from '../AppShell.jsx';

const espace = { id: 'w1', folder_id: 'w1', title: 'Mon espace', mission: null };
const bootstrap = { user: { name: 'Camille', email: 'camille@example.com' }, workspaces: [espace], selectedWorkspaceId: 'w1' };

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem('gabriel-v2:onboarding-completed-2026', '1');
  window.matchMedia = vi.fn(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn() }));
  Element.prototype.scrollTo = vi.fn();
  global.fetch = vi.fn(async () => ({ ok: true, status: 200, redirected: false, url: 'http://x', text: async () => JSON.stringify([]) }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const shell = () => document.querySelector('main.gv2-shell');

describe('Menu en tiroir sur téléphone', () => {
  it('propose un bouton pour ouvrir le menu, fermé au départ', async () => {
    render(<AppShell bootstrap={bootstrap} />);
    const bouton = await screen.findByRole('button', { name: 'Ouvrir le menu de navigation' });
    expect(bouton).toHaveAttribute('aria-expanded', 'false');
    expect(shell()).not.toHaveClass('is-mobile-menu-open');
    expect(screen.queryByRole('button', { name: 'Fermer le menu de navigation' })).toBeNull();
  });

  it('ouvre le tiroir avec le menu déployé et un fond cliquable', async () => {
    const user = userEvent.setup();
    render(<AppShell bootstrap={bootstrap} />);
    await user.click(await screen.findByRole('button', { name: 'Ouvrir le menu de navigation' }));
    expect(shell()).toHaveClass('is-mobile-menu-open');
    expect(document.querySelector('.gv2-sidebar')).not.toHaveClass('is-collapsed');     // le détail du menu est visible
    expect(screen.getByRole('button', { name: 'Fermer le menu de navigation' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ouvrir le menu de navigation' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('se ferme en touchant le fond', async () => {
    const user = userEvent.setup();
    render(<AppShell bootstrap={bootstrap} />);
    await user.click(await screen.findByRole('button', { name: 'Ouvrir le menu de navigation' }));
    await user.click(screen.getByRole('button', { name: 'Fermer le menu de navigation' }));
    expect(shell()).not.toHaveClass('is-mobile-menu-open');
  });

  it('se ferme avec Échap', async () => {
    const user = userEvent.setup();
    render(<AppShell bootstrap={bootstrap} />);
    await user.click(await screen.findByRole('button', { name: 'Ouvrir le menu de navigation' }));
    await user.keyboard('{Escape}');
    expect(shell()).not.toHaveClass('is-mobile-menu-open');
  });

  it('se ferme dès qu’on choisit un autre agent', async () => {
    const user = userEvent.setup();
    render(<AppShell bootstrap={bootstrap} />);
    await user.click(await screen.findByRole('button', { name: 'Ouvrir le menu de navigation' }));
    const rail = screen.getAllByRole('navigation').find(n => n.getAttribute('aria-label') === 'Navigation globale');
    await user.click(rail.querySelector('button[aria-label="Agents"]'));
    const ligne = [...document.querySelectorAll('.gv2-agent-nav-row')].find(row => row.textContent.includes('Créateur'));
    await user.click(ligne);
    await waitFor(() => expect(document.querySelector('nav.gv2-tabs button.is-active')).toHaveTextContent('Créateur'));   // l'agent a bien changé
    await waitFor(() => expect(shell()).not.toHaveClass('is-mobile-menu-open'));
  });

  it('garde la barre des agents dans l’en-tête, pour changer d’agent sans ouvrir le menu', async () => {
    render(<AppShell bootstrap={bootstrap} />);
    const barre = await screen.findByRole('navigation', { name: 'Sections de l’espace de travail' });
    expect(barre).toHaveTextContent('Psychologue');
    expect(barre).toHaveTextContent('Ariane');
    expect(barre).toHaveTextContent('Créateur');
  });
});
