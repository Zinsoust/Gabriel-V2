/* TarifsView — portage natif de templates/tarifs.html pour un utilisateur
   déjà connecté. Contenu (offres, prix, fonctionnalités) recopié tel quel
   de l'ancienne page ; le contrat Stripe (POST /stripe/checkout) est le
   même déjà vérifié pour le panneau Paramètres — ces tests couvrent
   spécifiquement cet écran : les trois offres s'affichent, le plan actif
   est marqué sans bouton pour le reprendre, et le clic ouvre une vraie
   session de paiement. */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TarifsView } from '../TarifsView.jsx';

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
afterEach(() => { delete global.fetch; vi.restoreAllMocks(); });

describe('Les trois offres', () => {
  it('affiche les trois plans avec leurs fonctionnalités', async () => {
    global.fetch = routeFetch([['/usage', () => ({ json: { plan: 'free', used: 0, limit: 0 } })]]);
    render(<TarifsView />);
    await waitFor(() => screen.getByText('Early Access'));
    expect(screen.getByText('Standard')).toBeInTheDocument();
    expect(screen.getByText('PME')).toBeInTheDocument();
    expect(screen.getAllByText('Analyses illimitées').length).toBeGreaterThan(0);
    expect(screen.getByText("Volume d'usage pensé pour une équipe")).toBeInTheDocument();
  });

  it('marque le plan actif sans lui proposer de bouton de paiement', async () => {
    global.fetch = routeFetch([['/usage', () => ({ json: { plan: 'standard', used: 4, limit: 0 } })]]);
    render(<TarifsView />);
    await waitFor(() => screen.getByText('Votre plan actuel'));
    expect(screen.queryByRole('button', { name: 'Commencer — 49 €/mois' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Rejoindre en Early Access — 29 €/mois' })).toBeInTheDocument();
  });
});

describe('Paiement', () => {
  it('ouvre une session Stripe réelle au clic', async () => {
    global.fetch = routeFetch([
      ['/usage', () => ({ json: { plan: 'free' } })],
      ['/stripe/checkout', () => ({ json: { url: 'https://checkout.stripe.com/session-abc' } })],
    ]);
    const assignSpy = vi.fn();
    const ancienLocation = window.location;
    Object.defineProperty(window, 'location', { value: { ...ancienLocation, assign: assignSpy }, writable: true, configurable: true });
    const user = userEvent.setup();
    render(<TarifsView />);
    await waitFor(() => screen.getByText('Early Access'));
    await user.click(screen.getByRole('button', { name: 'Rejoindre en Early Access — 29 €/mois' }));
    await waitFor(() => expect(assignSpy).toHaveBeenCalledWith('https://checkout.stripe.com/session-abc'));
    const appel = global.fetch.mock.calls.find(([url]) => url === '/stripe/checkout');
    expect(JSON.parse(appel[1].body)).toEqual({ plan: 'early_access' });
    Object.defineProperty(window, 'location', { value: ancienLocation, writable: true, configurable: true });
  });

  it('affiche l’erreur du serveur sans planter si Stripe refuse', async () => {
    global.fetch = routeFetch([
      ['/usage', () => ({ json: { plan: 'free' } })],
      ['/stripe/checkout', () => ({ status: 503, json: { error: 'Paiement non encore configuré.' } })],
    ]);
    const user = userEvent.setup();
    render(<TarifsView />);
    await waitFor(() => screen.getByText('Early Access'));
    await user.click(screen.getByRole('button', { name: 'Rejoindre en Early Access — 29 €/mois' }));
    await waitFor(() => expect(screen.getByText('Paiement non encore configuré.')).toBeInTheDocument());
  });
});
