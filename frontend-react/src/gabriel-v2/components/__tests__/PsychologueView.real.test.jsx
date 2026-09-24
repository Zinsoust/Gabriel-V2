/**
 * Le Psychologue face à une vraie analyse.
 *
 * La fixture est la réponse exacte d'une analyse sauvegardée par le backend
 * (GET /history/<id>/load). Les tests de PsychologueView.result utilisent des
 * formes écrites à la main : plusieurs ne correspondaient pas au backend
 * (groupes, lexique, champs lexicaux, KPI, commentaires likés) et masquaient
 * des blocs qui restaient vides à l'écran. Ici, on ne peut pas tricher.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PsychologueView } from '../PsychologueView.jsx';
import REEL from './fixtures/psychologue-analyse-reelle.json';
import YOUTUBE from './fixtures/psychologue-analyse-youtube.json';

async function analyser(resultat = REEL, props = {}) {
  global.fetch = vi.fn(async (url) => ({
    ok: true, status: 200, redirected: false, url: 'http://x',
    text: async () => JSON.stringify(
      String(url).includes('/status/')
        ? { status: 'done', data: resultat }
        : { job_id: 'job-1' }),
  }));
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(<PsychologueView workspace={null} {...props} />);
  await user.click(screen.getByRole('button', { name: /Changer de source/ }));
  const menu = screen.getByRole('listbox', { name: 'Choisir une source' });
  await user.click(within(menu).getByRole('option', { name: 'Commentaires' }));
  await user.type(screen.getByPlaceholderText(/Collez vos commentaires ici/), 'un\ndeux\ntrois');
  await user.click(screen.getByRole('button', { name: /Lancer l'analyse/ }));
  await vi.advanceTimersByTimeAsync(3500);
  await waitFor(() => expect(screen.getByText('Résultats')).toBeInTheDocument());
  return user;
}

async function onglet(user, nom) {
  await user.click(screen.getByRole('tab', { name: new RegExp(`^${nom}`) }));
}

const normaliser = (t) => String(t).replace(/\s+/g, ' ').trim();

/* Clés techniques volontairement non affichées : identifiants, doublons
   internes d'un bloc déjà rendu autrement, ou signaux bruts de calcul. */
const IGNORES = [
  /^analysis_id$/, /^nlp_signals\./, /^distribution\./, /^meta\./,
  /^video_(context|description)$/, /\.(genre|cluster_source|cluster_grounded|dominant)$/,
  /^dashboard\.(dominant_|signal_distribution|stance_distribution|emotion_distribution)/,
  /^livrables_statistiques\.[a-z_]+\.(distribution|clusters|camps|top_tokens|top_bigrams)/,
  /^dashboard\.groupes\.\d+\.exemples\.[1-9]/,           // une citation par groupe suffit
  /^dashboard\.lexical_fields\.\d+\.examples\.[1-9]/,    // idem par champ lexical
  /^dashboard\.signaux_frequents\.[a-z]+\.\d+\.examples\.[1-9]/,
  /\.(label|level|stance_dominante|emotion_dominante|signal)$/,
  /^kpis\.[a-z_]+\.(formule|label)$/,                    // vérifiés à part (texte court)
  /^personas\.\d+\.poids$/,
  /\.(comment_id|external_comment_id)$/,                   // identifiants techniques
  /(^|\.)[^.]*[^a-z0-9_.][^.]*$/i,                         // clé cassée par un JSON invalide
];

/* Toutes les phrases (au moins 25 caractères) que produit l'analyse. */
function phrases(valeur, chemin = '', sortie = []) {
  if (typeof valeur === 'string') {
    if (valeur.trim().length >= 25 && !IGNORES.some((r) => r.test(chemin))) sortie.push([chemin, valeur]);
  } else if (Array.isArray(valeur)) {
    valeur.forEach((v, i) => phrases(v, chemin ? `${chemin}.${i}` : String(i), sortie));
  } else if (valeur && typeof valeur === 'object') {
    Object.entries(valeur).forEach(([k, v]) => phrases(v, chemin ? `${chemin}.${k}` : k, sortie));
  }
  return sortie;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  window.localStorage.clear();
  window.sessionStorage.clear();
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); cleanup(); });

describe.each([
  ['texte libre, mistral-small', REEL],
  ['vidéo YouTube de 115 commentaires, ministral-14b', YOUTUBE],
])('Une vraie analyse (%s), lue en entier', (_nom, ANALYSE) => {
  it('affiche chaque phrase produite par le backend dans un des onglets', async () => {
    /* Le test qui garantit « toutes les informations » : on parcourt la
       réponse réelle, et chaque phrase doit se retrouver à l'écran. */
    const user = await analyser(ANALYSE);
    let texte = '';
    for (const tab of screen.getAllByRole('tab').map((t) => t.textContent)) {
      await user.click(screen.getByRole('tab', { name: tab }));
      // Les méthodes de calcul sont repliées mais présentes dans le DOM.
      texte += ' ' + normaliser(document.querySelector('.gv2-psy-result').textContent);
    }
    // « Cette semaine : Lancer… » s'affiche en deux morceaux (horizon, action).
    // Le gras markdown (**mot**) est rendu en <strong> : on compare sans les astérisques.
    // Les guillemets autour d'une citation sont remplacés par « » à l'affichage.
    const present = (v) => normaliser(v.replace(/\*/g, '').replace(/^[«"“\s]+|[»"”\s]+$/g, '')).split(' : ').every((morceau) => texte.includes(morceau));
    const manquantes = phrases(ANALYSE).filter(([, v]) => !present(v));
    expect(manquantes.map(([chemin]) => chemin)).toEqual([]);
    // Et jamais d'astérisques markdown bruts ni de guillemets doublés à l'écran.
    expect(texte).not.toMatch(/\*\*/);
    expect(texte).not.toMatch(/«\s*«|»\s*»/);
  }, 30000);
});

describe('Corrections de lecture sur la forme réelle', () => {
  it('montre le verdict et la lecture de chaque indicateur, et sa méthode', async () => {
    const user = await analyser();
    await onglet(user, 'Tableau de bord');
    expect(screen.getByText(REEL.kpis.alignement.description)).toBeInTheDocument();
    expect(screen.getByText(REEL.kpis.alignement.formule)).toBeInTheDocument();
    expect(screen.getAllByText('Méthode de calcul').length).toBe(Object.keys(REEL.kpis).length);
  });

  it('lit la tension principale dans resume_tendances', async () => {
    const user = await analyser();
    await onglet(user, 'Tableau de bord');
    expect(screen.getByText(REEL.dashboard.resume_tendances.tension_principale)).toBeInTheDocument();
  });

  it('montre les commentaires amplifiés, rangés à la racine du résultat', async () => {
    const user = await analyser();
    await onglet(user, 'Tableau de bord');
    expect(screen.getByText('Commentaires les plus amplifiés')).toBeInTheDocument();
    // likes à 0 et auteur « inconnu » : rien d'inventé ni de trompeur.
    expect(screen.queryByText(/♥ 0/)).toBeNull();
    expect(screen.queryByText(/inconnu/)).toBeNull();
  });

  it('affiche les mots du lexique sans leur score brut', async () => {
    const user = await analyser();
    await onglet(user, 'Tableau de bord');
    const carte = screen.getByText('Mots les plus significatifs').closest('.gv2-psy-card');
    const affiches = [...carte.querySelectorAll('.gv2-psy-tokens span')].map((n) => n.textContent);
    expect(affiches.slice(0, 3)).toEqual(REEL.dashboard.lexique.top_mots.slice(0, 3).map(([m]) => m));
  });

  it('montre les mots des champs lexicaux', async () => {
    const user = await analyser();
    await onglet(user, 'Tableau de bord');
    const champ = REEL.dashboard.lexical_fields[0];
    const carte = document.querySelectorAll('.gv2-psy-field')[0];
    expect(within(carte).getByText(champ.words[1])).toBeInTheDocument();
  });

  it('masque les positions vides et écrit les camps en clair', async () => {
    const user = await analyser();
    await onglet(user, 'Tableau de bord');
    const barres = [...document.querySelectorAll('.gv2-psy-bar-label')].map((n) => n.textContent);
    expect(barres).toContain('Opposé');
    expect(barres).toContain('Nuancé');
    expect(barres).not.toContain('Hors sujet');
    expect(barres).not.toContain('Ironique');
    expect(barres).not.toContain('oppose');
  });

  it('ne dessine pas de barres de résonance à 0 % quand personne n’a liké', async () => {
    const user = await analyser();
    await onglet(user, 'Tableau de bord');
    expect(screen.getByText('Densité argumentative par camp')).toBeInTheDocument();
    expect(document.querySelector('.gv2-psy-resonance .gv2-psy-bar-track')).toBeNull();
    expect(screen.getAllByText(/mots · /).length).toBeGreaterThan(0);
  });

  it('montre la couche sens & potentiel de la psychologie', async () => {
    const user = await analyser();
    await onglet(user, 'Psychologie');
    expect(screen.getByText('Sens & potentiel')).toBeInTheDocument();
    expect(screen.getByText(REEL.psychologie.potentiel_bloque)).toBeInTheDocument();
    expect(screen.getByText(REEL.psychologie.rapport_famille)).toBeInTheDocument();
  });

  it('montre les six preuves statistiques calculées sans IA', async () => {
    const user = await analyser();
    await onglet(user, 'Tableau de bord');
    expect(screen.getByText('Preuves statistiques')).toBeInTheDocument();
    expect(screen.getByText(REEL.livrables_statistiques.repartition_camps.conclusion)).toBeInTheDocument();
  });
});

describe('Parcours : chaque onglet mène quelque part', () => {
  it('propose l’onglet suivant en bas de chaque onglet, jusqu’aux personas', async () => {
    const user = await analyser();
    const ordre = ['Tableau de bord', 'Psychologie', 'Stratégie', 'Personas'];
    for (const suivant of ordre) {
      await user.click(screen.getByRole('button', { name: new RegExp(`Suite : ${suivant}`) }));
      expect(screen.getByRole('tab', { name: new RegExp(`^${suivant}`) })).toHaveAttribute('aria-selected', 'true');
    }
    expect(screen.getByText(/Lecture terminée/)).toBeInTheDocument();
  });

  it('transmet au Stratège un brief rempli, pas vide', async () => {
    /* Le brief était construit avec d'anciens noms de champs : le Stratège
       recevait une chaîne vide. */
    const onNavigateAgent = vi.fn();
    const user = await analyser(REEL, { onNavigateAgent });
    await user.click(screen.getAllByRole('button', { name: /Construire la stratégie/ })[0]);
    expect(onNavigateAgent).toHaveBeenCalledWith('stratege');
    const transmis = JSON.parse(window.sessionStorage.getItem('gabriel_for_stratege'));
    expect(transmis.psycho_brief).toContain(REEL.brief.qui);
    expect(transmis.psycho_brief).toContain(REEL.brief.insight);
    expect(transmis.psycho_brief).toContain(REEL.recommandations.message_central);
    expect(transmis.psycho_data.recommandations.message_central).toBe(REEL.recommandations.message_central);
  });

  it('mène au Créateur depuis la fin du parcours', async () => {
    const onNavigateAgent = vi.fn();
    const user = await analyser(REEL, { onNavigateAgent });
    await onglet(user, 'Personas');
    await user.click(screen.getByRole('button', { name: /Passer au Créateur/ }));
    expect(onNavigateAgent).toHaveBeenCalledWith('createur');
  });

  it('exporte le rapport en PDF depuis l’analyse sauvegardée', async () => {
    await analyser();
    expect(screen.getByRole('link', { name: 'Exporter en PDF' }))
      .toHaveAttribute('href', `/export/pdf/${REEL.analysis_id}`);
  });

  it('copie une synthèse prête à coller', async () => {
    // userEvent installe son propre presse-papiers : on relit celui-là.
    const user = await analyser();
    await user.click(screen.getByRole('button', { name: 'Copier la synthèse' }));
    expect(await navigator.clipboard.readText()).toContain(REEL.recommandations.message_central);
    expect(await screen.findByText('Copié ✓')).toBeInTheDocument();
  });

  it('copie la fiche d’un persona', async () => {
    const user = await analyser();
    await onglet(user, 'Personas');
    await user.click(screen.getAllByRole('button', { name: 'Copier la fiche' })[0]);
    expect(await navigator.clipboard.readText()).toContain(REEL.personas[0].nom);
  });
});
