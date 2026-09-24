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
    ['YouTube', 'Instagram', 'TikTok'].forEach(label => {
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

  it('n’annonce pas Google tant que sa collecte n’est pas connectée', async () => {
    /* Repositionnement du 13/09/2026 : aucune source affichée sans moteur
       derrière. Google revient dans ce menu le jour où il collecte vraiment. */
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    const menu = await openSourceMenu(user);
    expect(within(menu).queryByRole('option', { name: 'Google' })).toBeNull();
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

describe('Aperçu de la source', () => {
  it('affiche immédiatement la vignette YouTube avant la vérification réseau', async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn();
    render(<PsychologueView workspace={null} />);

    await user.type(screen.getByPlaceholderText(/vidéo YouTube/), 'https://www.youtube.com/watch?v=ud9o4GHHX6k');

    expect(screen.getByText('Vidéo YouTube · ud9o4GHHX6k')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Vignette de Vidéo YouTube/ })).toHaveAttribute('src', 'https://i.ytimg.com/vi/ud9o4GHHX6k/hqdefault.jpg');
    // Seul le chargement des analyses récentes de l'accueil peut partir : aucune
    // vérification du lien avant que l'utilisateur ne la demande.
    const appelsHorsHistorique = global.fetch.mock.calls.filter(([adresse]) => !String(adresse).endsWith('/history'));
    expect(appelsHorsHistorique).toHaveLength(0);
  });
});

describe('Accueil : le Psychologue comme porte d’entrée', () => {
  const HISTORIQUE = [
    { analysis_id: 'a-1', title: 'Lancement produit', source: 'YouTube', nb_commentaires: 115, created_at: '2026-09-13T01:30:00Z' },
  ];

  function fetchAvecHistorique() {
    global.fetch = vi.fn(async (adresse) => ({
      ok: true, status: 200, redirected: false, url: 'http://x',
      text: async () => JSON.stringify(String(adresse).endsWith('/history')
        ? HISTORIQUE
        : { full_result: { analysis_id: 'a-1', meta: { total_commentaires: 115 }, dashboard: {}, brief: { qui: 'Une audience curieuse mais prudente' } } }),
    }));
  }

  it('promet des signaux observables, pas une lecture des pensées', () => {
    render(<PsychologueView workspace={null} />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Psychologie avancée.');
    // Les mots-clés sont animés dans des <em> : on lit la phrase entière.
    expect(document.querySelector('.gv2-psy-landing-subtitle')).toHaveTextContent('Découvrez le marché caché, les peurs et les aspirations de votre audience.');
    expect(screen.getByText(/Aucune pensée devinée/)).toBeInTheDocument();
  });

  it('prépare la bonne source quand on choisit ce qu’on veut comprendre', async () => {
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    const intentions = screen.getByRole('region', { name: 'Que voulez-vous comprendre ?' });

    await user.click(within(intentions).getByRole('button', { name: /Analyser des avis clients/ }));
    expect(screen.getByPlaceholderText(/Collez vos commentaires ici/)).toBeInTheDocument();

    await user.click(within(intentions).getByRole('button', { name: /Importer une enquête/ }));
    expect(screen.getByText(/Ajoutez un fichier de commentaires/)).toBeInTheDocument();

    await user.click(within(intentions).getByRole('button', { name: /Comparer plusieurs audiences/ }));
    expect(screen.getByRole('button', { name: /Cross Analyse — comparer/ })).toHaveAttribute('aria-pressed', 'true');

    await user.click(within(intentions).getByRole('button', { name: /Comprendre une audience/ }));
    expect(screen.getByRole('button', { name: /Cross Analyse — comparer/ })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByPlaceholderText(/vidéo YouTube/)).toBeInTheDocument();
  });

  it('rouvre une analyse récente en un clic', async () => {
    fetchAvecHistorique();
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} />);
    const recents = await screen.findByRole('region', { name: 'Analyses récentes' });
    expect(within(recents).getByText(/115 commentaires/)).toBeInTheDocument();
    await user.click(within(recents).getByRole('button', { name: /Lancement produit/ }));
    expect(await screen.findByText('Une audience curieuse mais prudente')).toBeInTheDocument();
  });

  it('propose de prolonger vers la stratégie et le contenu', async () => {
    const onNavigateAgent = vi.fn();
    const user = userEvent.setup();
    render(<PsychologueView workspace={null} onNavigateAgent={onNavigateAgent} />);
    await user.click(screen.getByRole('button', { name: /Transformer en stratégie/ }));
    await user.click(screen.getByRole('button', { name: /Transformer en contenu/ }));
    expect(onNavigateAgent.mock.calls).toEqual([['stratege'], ['createur']]);
  });
});
