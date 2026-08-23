/**
 * Restitution complète du résultat Psychologue.
 *
 * Le backend produit une dizaine de blocs — interprétations psychologique et
 * socio-culturelle, réalité intérieure, aspirations, signaux marketing,
 * personas détaillés. L'écran n'en montrait que quatre. Tout arrivait déjà
 * dans la réponse : seul l'affichage manquait.
 *
 * Ces tests vérifient que chaque bloc atteint l'écran, et qu'un rapport
 * incomplet reste lisible au lieu d'afficher des sections vides.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PsychologueView } from '../PsychologueView.jsx';

const RESULTAT = {
  analysis_id: 'analyse-1',
  meta: { total_commentaires: 150, commentaires_analyses: 128 },
  brief: {
    synthese: "Audience compétente mais épuisée par le manque de temps",
    insight_cle: "Le prix est un proxy de la peur de mal choisir",
    action_prioritaire: "Rassurer avant de vendre",
  },
  kpis: {
    engagement: { score: 72, lecture: "Audience réactive" },
    opportunite: { score: 65 },
  },
  dashboard: {
    positions: {
      favorable: { pct: 60, count: 90 },
      oppose: { pct: 15, count: 22 },
      neutre: { pct: 25, count: 38 },
    },
    emotion_distribution: { Espoir: 38, Frustration: 22 },
    tension_principale: "Vouloir avancer sans savoir par où commencer",
    tendance_dominante: "Recherche de méthode",
    top_comments: [
      { text: "Le prix me freine mais je comprends la valeur", likes: 42 },
    ],
  },
  interpretation: {
    psychologique: {
      main_insight: "L'audience confond prudence et immobilisme",
      confidence_score: 0.82,
      detected_mechanisms: [
        { mechanism: "Aversion à la perte", confidence: 0.9,
          evidence: "Les commentaires évoquent le risque avant le gain" },
      ],
      fears: ["se tromper d'investissement"],
      desires: ["une méthode claire"],
      beliefs: ["il faut être prêt avant de commencer"],
      decision_drivers: ["preuve concrète"],
    },
    socio_culturelle: {
      main_insight: "Une génération qui valorise l'autonomie mais craint l'isolement",
      confidence_score: 0.71,
      fears: ["être jugé par ses pairs"],
    },
  },
  psychologie: {
    frustrations: ["manque de temps", "trop d'informations"],
    peurs_implicites: ["ne pas être légitime"],
    desirs_caches: ["être reconnu comme expert"],
    motivations_profondes: ["bâtir quelque chose qui dure"],
    croyances_limitantes: ["il faut tout maîtriser avant de lancer"],
    valeurs_dominantes: ["liberté", "intégrité"],
    mecanismes_psychologiques: "Biais de statu quo dominant",
    tensions_internes: "Entre l'envie d'avancer et la peur d'échouer",
    rapport_argent: "L'argent est vu comme une validation, pas un moyen",
  },
  aspirations: {
    ce_qu_ils_veulent_devenir: "un référent dans leur domaine",
    ce_qu_ils_veulent_eviter: "recommencer à zéro",
    appel_interieur: "transmettre ce qu'ils ont appris",
    ambitions: ["vivre de leur expertise"],
    freins_aux_aspirations: ["le syndrome de l'imposteur"],
  },
  marketing: {
    positionnement_recommande: "Accompagnement premium, pas formation de masse",
    objections_visibles: ["c'est cher"],
    objections_invisibles: ["je n'y arriverai pas"],
    declencheurs_emotionnels: ["preuve par les pairs"],
    opportunites_offre: ["offre intermédiaire à 490 €"],
    hooks_performants: ["Le vrai frein n'est pas le prix"],
  },
  personas: [
    {
      nom: "Le Pragmatique", poids: "40%", age: 38, genre: "F", metier: "Consultante",
      emotion_dominante_mesuree: "Espoir prudent",
      histoire_interieure: "Elle sait qu'elle est bonne, mais doute d'être vue",
      etat_esprit: "Prête à investir si le risque est cadré",
      vision_monde: "Le travail bien fait finit par payer",
      frustrations: ["perdre du temps"],
      desirs: ["une méthode éprouvée"],
      objection_principale: "Et si ça ne marchait pas pour moi ?",
      ce_qui_le_ferait_acheter: "Un cas concret proche du sien",
      message_a_lui_dire: "Vous n'avez pas besoin d'être prête, juste de commencer",
    },
  ],
};

/** Lance une vraie analyse manuelle et attend le résultat — même chemin que
 *  l'utilisateur, plutôt qu'un montage artificiel du composant. */
async function analyser(resultat = RESULTAT) {
  global.fetch = vi.fn(async (url) => ({
    ok: true, status: 200, redirected: false, url: 'http://x',
    text: async () => JSON.stringify(
      String(url).includes('/status/')
        ? { status: 'done', data: resultat }
        : { job_id: 'job-1' }),
  }));

  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(<PsychologueView workspace={null} />);

  await user.click(screen.getByRole('button', { name: /Changer de source/ }));
  const menu = screen.getByRole('listbox', { name: 'Choisir une source' });
  await user.click(within(menu).getByRole('option', { name: 'Commentaires' }));
  await user.type(screen.getByPlaceholderText(/Collez vos commentaires ici/),
                  'un commentaire\ndeux commentaires\ntrois commentaires');
  await user.click(screen.getByRole('button', { name: /Lancer l'analyse/ }));
  await vi.advanceTimersByTimeAsync(3500);
  await waitFor(() => expect(screen.getByText('Résultats')).toBeInTheDocument());
  return user;
}

beforeEach(() => {
  // shouldAdvanceTime : sans lui, userEvent attend un temps qui n'avance
  // jamais et le test expire avant d'avoir cliqué.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  window.localStorage.clear();
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); cleanup(); });

describe('Onglets de résultat', () => {
  it('propose les trois onglets du livrable d’origine', async () => {
    await analyser();
    expect(screen.getByRole('tab', { name: /Tableau de bord/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Interprétation/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Personas/ })).toBeInTheDocument();
  });

  it('n’affiche pas un onglet qui serait vide', async () => {
    /* Mieux vaut deux onglets pleins que trois dont un déçoit. */
    await analyser({ ...RESULTAT, personas: [], interpretation: {},
             psychologie: {}, aspirations: {}, marketing: {} });
    screen.getByText(/Audience compétente/);
    expect(screen.queryByRole('tab', { name: /Personas/ })).toBeNull();
    expect(screen.queryByRole('tab', { name: /Interprétation/ })).toBeNull();
  });
});

describe('Tableau de bord', () => {
  it('montre les indicateurs chiffrés', async () => {
    await analyser();
    expect(screen.getByText('72')).toBeInTheDocument();
    expect(screen.getByText('Audience réactive')).toBeInTheDocument();
  });

  it('montre la lecture d’ensemble, absente de l’écran précédent', async () => {
    await analyser();
    expect(screen.getByText(/Vouloir avancer sans savoir/)).toBeInTheDocument();
  });

  it('montre les commentaires réellement amplifiés', async () => {
    await analyser();
    expect(screen.getByText(/Le prix me freine/)).toBeInTheDocument();
    expect(screen.getByText(/42 j'aime/)).toBeInTheDocument();
  });
});

describe('Interprétation', () => {
  async function ouvrir() {
    const user = await analyser();
    await user.click(screen.getByRole('tab', { name: /Interprétation/ }));
    return user;
  }

  it('montre les deux lectures, psychologique et socio-culturelle', async () => {
    await ouvrir();
    expect(screen.getByText('Lecture psychologique')).toBeInTheDocument();
    expect(screen.getByText('Lecture socio-culturelle')).toBeInTheDocument();
    expect(screen.getByText(/confond prudence et immobilisme/)).toBeInTheDocument();
    expect(screen.getByText(/valorise l'autonomie/)).toBeInTheDocument();
  });

  it('montre les mécanismes détectés avec leur preuve', async () => {
    /* Un mécanisme sans preuve serait une affirmation gratuite. */
    await ouvrir();
    expect(screen.getByText('Aversion à la perte')).toBeInTheDocument();
    expect(screen.getByText(/évoquent le risque avant le gain/)).toBeInTheDocument();
  });

  it('montre la confiance de chaque lecture', async () => {
    await ouvrir();
    expect(screen.getByText('confiance 82%')).toBeInTheDocument();
  });

  it('montre la réalité intérieure de l’audience', async () => {
    await ouvrir();
    expect(screen.getByText('manque de temps')).toBeInTheDocument();
    expect(screen.getByText('ne pas être légitime')).toBeInTheDocument();
    expect(screen.getByText(/Biais de statu quo/)).toBeInTheDocument();
  });

  it('montre les aspirations', async () => {
    await ouvrir();
    expect(screen.getByText('un référent dans leur domaine')).toBeInTheDocument();
    expect(screen.getByText('transmettre ce qu’ils ont appris'.replace('’', "'"))).toBeInTheDocument();
  });

  it('montre les signaux exploitables', async () => {
    await ouvrir();
    expect(screen.getByText(/Accompagnement premium/)).toBeInTheDocument();
    expect(screen.getByText('je n’y arriverai pas'.replace('’', "'"))).toBeInTheDocument();
  });
});

describe('Personas', () => {
  it('montre un persona complet, pas seulement son nom', async () => {
    const user = await analyser();
    await user.click(screen.getByRole('tab', { name: /Personas/ }));

    expect(screen.getByText('Le Pragmatique')).toBeInTheDocument();
    expect(screen.getByText('40%')).toBeInTheDocument();
    expect(screen.getByText('Espoir prudent')).toBeInTheDocument();
    expect(screen.getByText(/doute d'être vue/)).toBeInTheDocument();
    expect(screen.getByText(/Et si ça ne marchait pas/)).toBeInTheDocument();
    expect(screen.getByText(/juste de commencer/)).toBeInTheDocument();
  });
});

describe('Rapport incomplet', () => {
  it('reste lisible quand des blocs manquent', async () => {
    /* Un rapport pauvre doit produire un écran pauvre mais propre — jamais
       une section à trous ni un plantage. */
    await analyser({ meta: { total_commentaires: 3 }, dashboard: {}, brief: {} });
    expect(screen.getByText('Résultats')).toBeInTheDocument();
    expect(screen.queryByRole('tab')).toBeNull();
  });
});
