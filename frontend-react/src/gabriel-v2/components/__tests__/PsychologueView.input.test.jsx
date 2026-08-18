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
import { render, screen, waitFor } from '@testing-library/react';
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

describe('Entrées disponibles', () => {
  it('expose les trois onglets de saisie', () => {
    render(<PsychologueView workspace={null} />);
    expect(screen.getByRole('tab', { name: 'Sources' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Commentaires' })).toBeInTheDocument();
    // L'onglet Fichier avait purement disparu lors de la bascule.
    expect(screen.getByRole('tab', { name: 'Fichier' })).toBeInTheDocument();
  });

  it('expose les cinq plateformes de collecte', () => {
    render(<PsychologueView workspace={null} />);
    // Seul YouTube avait survécu à la bascule.
    ['YouTube', 'Instagram', 'TikTok', 'Google', 'Autre source'].forEach(label => {
      expect(screen.getByText(label)).toBeInTheDocument();
    });
  });

  it('ouvre la zone de dépôt quand on choisit l’onglet Fichier', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByRole('tab', { name: 'Fichier' }));
    expect(screen.getByText(/Choisir un fichier de commentaires/)).toBeInTheDocument();
    expect(screen.getByText(/CSV, Excel, JSON ou TXT/)).toBeInTheDocument();
  });
});

describe('Changement de plateforme', () => {
  it('adapte le champ de saisie à la plateforme choisie', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);

    await user.click(screen.getByText('Instagram'));
    expect(screen.getByPlaceholderText(/publication Instagram/)).toBeInTheDocument();

    await user.click(screen.getByText('TikTok'));
    expect(screen.getByPlaceholderText(/vidéo TikTok/)).toBeInTheDocument();
  });

  it('désactive la saisie pour Google et dit pourquoi', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByText('Google'));

    // Annoncer une source non connectée sans bloquer la saisie laisserait
    // l'utilisateur coller un lien qui ne sera jamais traité.
    expect(screen.getByPlaceholderText(/arrive prochainement/)).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent(/Google sera connecté/);
  });

  it('bascule vers la saisie manuelle depuis « Autre source »', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByText('Autre source'));
    expect(screen.getByPlaceholderText(/Collez vos commentaires ici/)).toBeInTheDocument();
  });

  it('ne laisse pas le message d’une plateforme fuiter dans l’onglet Fichier', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByText('Instagram'));
    expect(screen.getByRole('status')).toHaveTextContent(/Instagram/);

    await user.click(screen.getByRole('tab', { name: 'Fichier' }));
    // Le statut est un état partagé : sans nettoyage il restait affiché sous
    // la zone de dépôt, en parlant d'un lien qu'on ne saisit plus.
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

describe('Conditions de lancement', () => {
  it('refuse de lancer tant qu’aucune source n’est prête', () => {
    render(<PsychologueView workspace={null} />);
    expect(screen.getByRole('button', { name: /Lancer l'analyse/ })).toBeDisabled();
  });

  it('refuse de lancer avec moins de trois commentaires manuels', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByRole('tab', { name: 'Commentaires' }));
    await user.type(screen.getByPlaceholderText(/Collez vos commentaires ici/), 'un\ndeux');
    expect(screen.getByRole('button', { name: /Lancer l'analyse/ })).toBeDisabled();
  });

  it('autorise le lancement à partir de trois commentaires manuels', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    await user.click(screen.getByRole('tab', { name: 'Commentaires' }));
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
    expect(screen.getByRole('button', { name: /Lancer l'analyse/ })).toBeDisabled();
  });
});
