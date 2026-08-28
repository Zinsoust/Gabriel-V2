/* Le profil est la mémoire la plus ancienne de Gabriel : dernier recours de
   la cascade business_context quand ni la requête ni l'entretien stratégique
   ne fournissent le contexte (voir core/business_context.py). L'ancienne
   page V1 n'avait aucun équivalent en V2 — sans ce port, cette mémoire
   restait à jamais vide pour tout compte créé depuis la V2. Ces tests
   couvrent le formulaire, le plan/consommation, et la suppression de
   compte — pas l'affichage général déjà couvert ailleurs. */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Sidebar } from '../Sidebar.jsx';

const USER = { name: 'Nalay', email: 'nalay@exemple.fr' };
const PROFIL = {
  role_utilisateur: 'Coach business', activite: '', offre: '', cible: '',
  modele_economique: '', resultats_actuels: '', objectif_principal: '',
};

function afficherPanneau({ profil = PROFIL, usage = { plan: 'standard', used: 4, limit: 20 }, workspaces = [{ folder_id: 'f1' }, { folder_id: 'f2' }] } = {}) {
  global.fetch = vi.fn((url, options = {}) => {
    if (url === '/profil/data') return Promise.resolve({ status: 200, redirected: false, url, text: () => Promise.resolve(JSON.stringify(profil)) });
    if (url === '/usage') return Promise.resolve({ status: 200, redirected: false, url, text: () => Promise.resolve(JSON.stringify(usage)) });
    if (url === '/profil') return Promise.resolve({ status: 200, redirected: false, url, text: () => Promise.resolve(JSON.stringify({ success: true })) });
    if (url === '/account/delete') return Promise.resolve({ status: 200, redirected: false, url, text: () => Promise.resolve(JSON.stringify({ success: true })) });
    return Promise.resolve({ status: 200, redirected: false, url, text: () => Promise.resolve('{}') });
  });
  render(<Sidebar workspaces={workspaces} activeTab="conversation" collapsed={false} user={USER} onToggleCollapsed={vi.fn()} onSelectWorkspace={vi.fn()} onCreateWorkspace={vi.fn()} onDeleteWorkspace={vi.fn()} onSelectConversation={vi.fn()} onStartNewConversation={vi.fn()} onSelectAgent={vi.fn()} onToggleDarkMode={vi.fn()} onStartGuide={vi.fn()} />);
  return userEvent.setup();
}

async function ouvrirParametres(user) {
  await user.click(screen.getByRole('button', { name: 'Votre compte' }));
  await waitFor(() => expect(screen.getByLabelText('Votre rôle')).toBeInTheDocument());
}

beforeEach(() => cleanup());
afterEach(() => { delete global.fetch; delete window.confirm; });

describe('Profil : le formulaire business', () => {
  it('charge les valeurs déjà enregistrées', async () => {
    const user = await afficherPanneau();
    await ouvrirParametres(user);
    expect(screen.getByLabelText('Votre rôle')).toHaveValue('Coach business');
  });

  it('affiche l’avancement de complétion, pas un compte figé', async () => {
    /* Un seul champs rempli sur sept : le profil doit se dire "vide", pas
       "complet" — sinon l'indicateur ne dit plus rien d'utile. */
    const user = await afficherPanneau();
    await ouvrirParametres(user);
    expect(screen.getByText(/Profil vide/)).toBeInTheDocument();
    expect(screen.getByText('1 / 7')).toBeInTheDocument();
  });

  it('se dit complet seulement quand les sept champs essentiels le sont', async () => {
    const complet = { role_utilisateur: 'a', activite: 'b', offre: 'c', cible: 'd',
      modele_economique: 'e', resultats_actuels: 'f', objectif_principal: 'g' };
    const user = await afficherPanneau({ profil: complet });
    await ouvrirParametres(user);
    expect(screen.getByText(/Profil complet/)).toBeInTheDocument();
  });

  it('enregistre le formulaire modifié', async () => {
    const user = await afficherPanneau();
    await ouvrirParametres(user);
    await user.clear(screen.getByLabelText('Votre rôle'));
    await user.type(screen.getByLabelText('Votre rôle'), 'Consultante SaaS');
    await user.click(screen.getByRole('button', { name: /Enregistrer/ }));
    await waitFor(() => {
      const appel = global.fetch.mock.calls.find(([url]) => url === '/profil');
      expect(appel).toBeTruthy();
      expect(JSON.parse(appel[1].body).role_utilisateur).toBe('Consultante SaaS');
    });
  });
});

describe('Profil : plan et consommation', () => {
  it('affiche le plan et le nombre de dossiers réellement ouverts', async () => {
    /* Le nombre de dossiers vient des workspaces déjà chargés par le shell,
       pas d'un second appel réseau — la barre latérale connaît déjà cette
       liste. */
    const user = await afficherPanneau();
    await ouvrirParametres(user);
    await waitFor(() => expect(document.querySelector('.gv2-plan-badge')).not.toBeNull());
    expect(document.querySelector('.gv2-plan-badge').textContent).toBe('Standard');
    expect(screen.getByText('4 / 20')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('marque le plan actif parmi les offres, sans bouton pour le reprendre', async () => {
    const user = await afficherPanneau();
    await ouvrirParametres(user);
    await waitFor(() => expect(document.querySelector('.gv2-plan-badge')).not.toBeNull());
    expect(screen.getByText('Votre plan actuel')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Passer en Standard' })).toBeNull();
  });

  it('ouvre une session Stripe au clic sur une autre offre', async () => {
    const user = await afficherPanneau();
    await ouvrirParametres(user);
    await waitFor(() => expect(document.querySelector('.gv2-plan-badge')).not.toBeNull());
    const assignSpy = vi.fn();
    const ancienLocation = window.location;
    Object.defineProperty(window, 'location', { value: { ...ancienLocation, assign: assignSpy }, writable: true, configurable: true });
    global.fetch.mockImplementation((url) => {
      if (url === '/stripe/checkout') return Promise.resolve({ status: 200, ok: true, redirected: false, url, text: () => Promise.resolve(JSON.stringify({ url: 'https://checkout.stripe.com/session-123' })) });
      return Promise.resolve({ status: 200, redirected: false, url, text: () => Promise.resolve('{}') });
    });
    await user.click(screen.getByRole('button', { name: 'Passer en PME' }));
    await waitFor(() => expect(assignSpy).toHaveBeenCalledWith('https://checkout.stripe.com/session-123'));
    Object.defineProperty(window, 'location', { value: ancienLocation, writable: true, configurable: true });
  });

  it('affiche l’erreur du serveur sans planter si Stripe refuse', async () => {
    const user = await afficherPanneau();
    await ouvrirParametres(user);
    await waitFor(() => expect(document.querySelector('.gv2-plan-badge')).not.toBeNull());
    global.fetch.mockImplementation((url) => {
      if (url === '/stripe/checkout') return Promise.resolve({ status: 503, ok: false, redirected: false, url, text: () => Promise.resolve(JSON.stringify({ error: 'Paiement non encore configuré.' })) });
      return Promise.resolve({ status: 200, redirected: false, url, text: () => Promise.resolve('{}') });
    });
    await user.click(screen.getByRole('button', { name: 'Passer en PME' }));
    await waitFor(() => expect(screen.getByText('Paiement non encore configuré.')).toBeInTheDocument());
  });
});

describe('Profil : suppression de compte', () => {
  it('exige l’email exact avant d’activer la suppression', async () => {
    const user = await afficherPanneau();
    await ouvrirParametres(user);
    await user.click(screen.getByRole('button', { name: /Supprimer définitivement mon compte/ }));
    const bouton = screen.getByRole('button', { name: 'Supprimer définitivement' });
    expect(bouton).toBeDisabled();
    await user.type(screen.getByLabelText(/Confirmez votre email/), 'mauvais@email.fr');
    expect(bouton).toBeDisabled();
    await user.clear(screen.getByLabelText(/Confirmez votre email/));
    await user.type(screen.getByLabelText(/Confirmez votre email/), USER.email);
    expect(bouton).toBeEnabled();
  });

  it('supprime uniquement une fois l’email confirmé', async () => {
    const user = await afficherPanneau();
    await ouvrirParametres(user);
    await user.click(screen.getByRole('button', { name: /Supprimer définitivement mon compte/ }));
    await user.type(screen.getByLabelText(/Confirmez votre email/), USER.email);
    await user.click(screen.getByRole('button', { name: 'Supprimer définitivement' }));
    await waitFor(() => {
      const appel = global.fetch.mock.calls.find(([url]) => url === '/account/delete');
      expect(appel).toBeTruthy();
      expect(JSON.parse(appel[1].body)).toEqual({ confirm_email: USER.email });
    });
  });

  it('annuler referme la confirmation sans rien envoyer', async () => {
    const user = await afficherPanneau();
    await ouvrirParametres(user);
    await user.click(screen.getByRole('button', { name: /Supprimer définitivement mon compte/ }));
    await user.click(screen.getByRole('button', { name: 'Annuler' }));
    expect(screen.getByRole('button', { name: /Supprimer définitivement mon compte/ })).toBeInTheDocument();
    expect(global.fetch.mock.calls.some(([url]) => url === '/account/delete')).toBe(false);
  });
});
