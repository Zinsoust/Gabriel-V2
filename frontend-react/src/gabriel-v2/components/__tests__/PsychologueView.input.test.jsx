/**
 * Parité des entrées du Psychologue.
 *
 * Ces tests existent parce qu'une bascule vers la vue React native a fait
 * disparaître, sans que personne ne s'en aperçoive, l'import de fichier et
 * quatre des cinq plateformes de collecte. Le backend n'avait rien perdu :
 * seules les entrées de l'interface manquaient. Chaque test ci-dessous
 * échouerait si l'une de ces entrées disparaissait à nouveau.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PsychologueView } from '../PsychologueView.jsx';

function mockFetchOnce(payload, ok = true) {
  return vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 400,
    redirected: false,
    url: 'http://localhost/analyze',
    text: async () => JSON.stringify(payload),
  });
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function openSourceMenu(user) {
  await user.click(screen.getByRole('button', { name: /Changer de source/ }));
  return screen.getByRole('listbox', { name: 'Choisir une source' });
}

async function chooseSource(user, label) {
  const menu = await openSourceMenu(user);
  await user.click(within(menu).getByRole('option', { name: label }));
}

describe('Entrées disponibles', () => {
  it('réunit les modes de saisie dans le sélecteur de la barre', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    const menu = await openSourceMenu(user);
    expect(within(menu).getByRole('option', { name: 'Commentaires' })).toBeInTheDocument();
    expect(within(menu).getByRole('option', { name: 'Fichier' })).toBeInTheDocument();
  });

  it('expose les plateformes de collecte dans le sélecteur', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    const menu = await openSourceMenu(user);
    ['YouTube', 'Instagram', 'TikTok', 'Google'].forEach(label => {
      expect(within(menu).getByRole('option', { name: label })).toBeInTheDocument();
    });
  });

  it('ouvre le sélecteur de fichier quand on choisit Fichier', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await chooseSource(user, 'Fichier');
    expect(screen.getByText(/Ajoutez un fichier de commentaires/)).toBeInTheDocument();
    expect(screen.getByText(/CSV, Excel, JSON ou TXT/)).toBeInTheDocument();
  });
});

describe('Changement de plateforme', () => {
  it('adapte le champ de saisie à la plateforme choisie', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);

    await chooseSource(user, 'Instagram');
    expect(screen.getByPlaceholderText(/publication Instagram/)).toBeInTheDocument();

    await chooseSource(user, 'TikTok');
    expect(screen.getByPlaceholderText(/vidéo TikTok/)).toBeInTheDocument();
  });

  it('désactive la saisie pour Google et dit pourquoi', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await chooseSource(user, 'Google');

    // Annoncer une source non connectée sans bloquer la saisie laisserait
    // l'utilisateur coller un lien qui ne sera jamais traité.
    expect(screen.getByPlaceholderText(/arrive prochainement/)).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent(/Google sera connecté/);
  });

  it('bascule vers la saisie manuelle depuis le sélecteur', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await chooseSource(user, 'Commentaires');
    expect(screen.getByPlaceholderText(/Collez vos commentaires ici/)).toBeInTheDocument();
  });

  it('ne laisse pas le message d’une plateforme fuiter dans l’onglet Fichier', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await chooseSource(user, 'Instagram');
    expect(screen.getByRole('status')).toHaveTextContent(/Instagram/);

    await chooseSource(user, 'Fichier');
    // Le statut est un état partagé : sans nettoyage il restait affiché sous
    // la zone de dépôt, en parlant d'un lien qu'on ne saisit plus.
    expect(screen.getByRole('status')).not.toHaveTextContent(/Instagram/);
  });
});

describe('Conditions de lancement', () => {
  it('refuse de lancer tant qu’aucune source n’est prête', () => {
    render(<PsychologueView workspace={null} />);
    expect(screen.getByRole('button', { name: /Vérifier le lien/ })).toBeDisabled();
  });

  it('refuse de lancer avec moins de trois commentaires manuels', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await chooseSource(user, 'Commentaires');
    await user.type(screen.getByPlaceholderText(/Collez vos commentaires ici/), 'un\ndeux');
    expect(screen.getByRole('button', { name: /Lancer l'analyse/ })).toBeDisabled();
  });

  it('autorise le lancement à partir de trois commentaires manuels', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await chooseSource(user, 'Commentaires');
    await user.type(screen.getByPlaceholderText(/Collez vos commentaires ici/), 'un\ndeux\ntrois');
    expect(screen.getByRole('button', { name: /Lancer l'analyse/ })).toBeEnabled();
  });

  it('autorise le lancement une fois un lien vérifié', async () => {
    const user = userEvent.setup();
    global.fetch = mockFetchOnce({ comments_preview: ['a'], comments_count: 150 });
    render(<PsychologueView workspace={null} />);

    await user.type(screen.getByPlaceholderText(/vidéo YouTube/), 'https://youtube.com/watch?v=abc');
    await user.click(screen.getByRole('button', { name: /Vérifier le lien/ }));

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/150 commentaires détectés/);
    });
    expect(screen.getByRole('button', { name: /Lancer l'analyse/ })).toBeEnabled();
  });

  it('remonte l’erreur du serveur quand le lien est refusé', async () => {
    const user = userEvent.setup();
    global.fetch = mockFetchOnce({ error: 'Vidéo introuvable ou commentaires désactivés.' });
    render(<PsychologueView workspace={null} />);

    await user.type(screen.getByPlaceholderText(/vidéo YouTube/), 'https://youtube.com/watch?v=zzz');
    await user.click(screen.getByRole('button', { name: /Vérifier le lien/ }));

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/Vidéo introuvable/);
    });
    // Un lien refusé ne doit ouvrir aucun chemin vers l'analyse : le composer
    // reste sur la vérification tant que la source n'est pas validée.
    expect(screen.queryByRole('button', { name: /Lancer l'analyse/ })).toBeNull();
    expect(screen.getByRole('button', { name: /Vérifier le lien/ })).toBeInTheDocument();

    // Et surtout : aucune analyse réelle n'a été lancée. La vérification passe
    // elle aussi par /analyze, mais en `preview_only` — c'est l'absence de ce
    // drapeau qui signe un vrai lancement, facturé et long.
    const lancements = global.fetch.mock.calls.filter(([url, init]) =>
      String(url).includes('/analyze') && !JSON.parse(init?.body || '{}').preview_only);
    expect(lancements).toHaveLength(0);
  });
});
