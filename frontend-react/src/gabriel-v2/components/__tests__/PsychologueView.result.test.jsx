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
    // Formes relevées en exécutant réellement audience.compute_dashboard.
    weighted_sentiment: { score: 0.115, score_raw: 0.098, total_likes: 149,
                          interpretation: 'positif pondéré' },
    weighted_polarization: { score: 30.8, label: 'Modérément partagée' },
    fiabilite: { commentaires_analyses: 105, commentaires_hors_sujet: 8,
                 pct_hors_sujet: 7.6, label_confiance: 'Élevée' },
    resonance_by_stance: { favorable: { likes: 11, pct: 7.4, count: 33 },
                           neutre: { likes: 113, pct: 75.8, count: 54 } },
    argument_density: { favorable: { avg_words: 23, label: 'argumenté' },
                        neutre: { avg_words: 15.2, label: 'argumenté' } },
    groupes: [{ pct: 43.8, size: 46, likes_pct: 48.3, stance: 'neutre',
                emotion: 'admiration', top_tokens: ['vidéo', 'merci', 'claude'],
                samples: ["Faudrait mettre cette vidéo devant une éolienne"] }],
    sujets_recurrents: [{ theme: 'Vidéo', pct: 33.3, count: 35,
                          exemple: 'Faudrait mettre cette vidéo devant une éolienne' }],
    signaux_frequents: {
      frustrations: [{ signal: 'frustration', pct: 3.8, count: 4,
                       examples: ['Attention au RGPD : sécurité critique'] }],
      attentes: [{ signal: 'question', pct: 50.5, count: 53,
                   examples: ['Ou est la database ?'] }],
      objections: [{ signal: 'objection', pct: 1, count: 1,
                     examples: ['tu utilises Opus, ce modèle est cher'] }],
    },
    mockery_signals: { count: 0, pct: 0, level: 'absent' },
    irony_signals: { count: 0, pct: 0, level: 'absent' },
    lexique: { top_mots: [{ mot: 'merci' }, { mot: 'claude' }],
               top_bigrams: [{ bigram: 'claude code', count: 14 }] },
    lexical_fields: [{ field: 'Merci', pct: 49.5, count: 52,
                       tokens: ['merci', 'vidéo'],
                       exemple: 'Faudrait mettre cette vidéo devant une éolienne' }],
    polarisation_detail: { phrase: "L'audience penche favorablement : 31.4% favorables, 7.6% opposés.",
                           label: 'Plutôt favorable', score: 16.9 },
    top_comments: [{ text: "Faudrait mettre cette vidéo devant une éolienne", likes: 48, author: 'jsevdev' }],
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
  livrables_statistiques: {
    lecture_sujet: {
      conclusion: "L'audience a reçu ce sujet comme une bouffée d'oxygène technique",
      indicateur_statistique: 'CRS moyen : 0.274 (faible) | 80% de commentaires neutres',
      signaux: ['merci vidéo', 'base données'],
      interpretation: "Le faible CRS révèle une dissonance entre l'attente et la réalité",
      score_confiance: 0.85,
    },
    ce_qui_rassemble: {
      conclusion: "L'audience est unie par un désir de maîtrise technique sans effort",
      indicateur_statistique: 'Cluster 0 et Cluster 1 partagent 67.6% des commentaires',
      signaux: ['claude code'],
      interpretation: "Ces tokens révèlent une tribu en quête d'un Guide",
      score_confiance: 0.9,
    },
  },
  grille_psychologique: {
    ce_qu_ils_ressentent: {
      observation: '34.3% des commentaires montrent des marqueurs de confusion',
      interpretation: "L'audience est en phase d'exploration active mais manque de repères",
      implication: "Créer des contenus qui structurent l'information progressivement",
    },
    ce_qui_les_bloque: {
      observation: "3.8% de frustration + 1% d'objection",
      interpretation: "La peur de s'engager dans un outil qui ne répondra pas",
      implication: 'Proposer des solutions concrètes pour contourner les limitations',
    },
  },
  recommandations: {
    verite_de_l_audience: 'Ils veulent devenir des créateurs autonomes et respectés',
    message_central: 'Devenez le créateur que vous aspirez à être',
    prochaines_etapes: ["Cette semaine : Lancer le défi '30 Jours'",
                        'Ce mois : Publier la première série de tutoriels'],
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
    expect(screen.getByText(/♥ 42/)).toBeInTheDocument();
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


describe('Blocs mesurés du tableau de bord', () => {
  /* Ces quatorze blocs sont calculés par le backend depuis toujours. Aucun
     n'atteignait l'écran : c'est le cœur de ce que l'analyse produit. */

  it('montre les métriques pondérées par engagement', async () => {
    /* Un commentaire très liké pèse plus qu'un commentaire isolé — sans
       cette pondération, une minorité bruyante passe pour la majorité. */
    await analyser();
    expect(screen.getByText('0.115')).toBeInTheDocument();
    expect(screen.getByText('positif pondéré')).toBeInTheDocument();
    expect(screen.getByText('30.8')).toBeInTheDocument();
    expect(screen.getByText('149')).toBeInTheDocument();
  });

  it('montre la fiabilité et ce qui a été écarté', async () => {
    /* Savoir combien de commentaires ont été jugés hors sujet est ce qui
       permet de juger la solidité du reste. */
    await analyser();
    expect(screen.getByText('Élevée')).toBeInTheDocument();
    expect(screen.getByText('7.6%')).toBeInTheDocument();
  });

  it('montre la résonance par camp et la densité argumentative', async () => {
    await analyser();
    expect(screen.getByText('75.8%')).toBeInTheDocument();
    expect(screen.getByText(/15.2 mots/)).toBeInTheDocument();
  });

  it('montre les groupes détectés avec leurs mots et leurs citations', async () => {
    await analyser();
    expect(screen.getByText('43.8%')).toBeInTheDocument();
    expect(screen.getByText('46 commentaires')).toBeInTheDocument();
    // Le groupe est le seul bloc qui cite en blockquote.
    const citations = screen.getAllByText(/devant une éolienne/);
    expect(citations.some((n) => n.tagName === 'BLOCKQUOTE')).toBe(true);
  });

  it('montre les sujets récurrents', async () => {
    await analyser();
    expect(screen.getByText('Vidéo')).toBeInTheDocument();
    expect(screen.getByText(/35 occurrences/)).toBeInTheDocument();
  });

  it('montre frustrations, attentes et objections séparément', async () => {
    /* Les confondre ferait perdre la distinction la plus utile : ce qui
       bloque n'est pas ce qui est espéré. */
    await analyser();
    expect(screen.getByText('Frustrations')).toBeInTheDocument();
    expect(screen.getByText('Attentes & désirs')).toBeInTheDocument();
    expect(screen.getByText('Objections')).toBeInTheDocument();
    expect(screen.getByText(/Attention au RGPD/)).toBeInTheDocument();
    expect(screen.getByText(/tu utilises Opus/)).toBeInTheDocument();
  });

  it('montre les signaux de moquerie et d’ironie', async () => {
    /* Un enthousiasme ironique n'est pas de l'adhésion : ne pas le mesurer
       fausserait la lecture du sentiment. */
    await analyser();
    expect(screen.getByText('Moquerie')).toBeInTheDocument();
    expect(screen.getByText('Ironie')).toBeInTheDocument();
  });

  it('montre les mots et expressions fréquents', async () => {
    await analyser();
    expect(screen.getAllByText('merci').length).toBeGreaterThan(0);
    expect(screen.getByText(/claude code · 14/)).toBeInTheDocument();
  });

  it('montre les champs lexicaux détectés', async () => {
    await analyser();
    expect(screen.getByText('Merci')).toBeInTheDocument();
    expect(screen.getByText(/49.5% des commentaires/)).toBeInTheDocument();
  });

  it('montre la lecture de polarisation en clair', async () => {
    await analyser();
    expect(screen.getByText(/penche favorablement/)).toBeInTheDocument();
  });
});

describe('Insights fondés sur données', () => {
  async function ouvrirInterpretation() {
    const user = await analyser();
    await user.click(screen.getByRole('tab', { name: /Interprétation/ }));
    return user;
  }

  it('montre chaque livrable avec sa donnée, ses signaux et son sens', async () => {
    /* La forme qui distingue une analyse d'une opinion : chaque conclusion
       est adossée à un chiffre mesuré. */
    await ouvrirInterpretation();
    expect(screen.getByText('Lecture du sujet')).toBeInTheDocument();
    expect(screen.getByText(/bouffée d'oxygène technique/)).toBeInTheDocument();
    expect(screen.getByText(/CRS moyen : 0.274/)).toBeInTheDocument();
    expect(screen.getByText(/dissonance entre l'attente/)).toBeInTheDocument();
  });

  it('montre le niveau de confiance de chaque livrable', async () => {
    await ouvrirInterpretation();
    expect(screen.getByText('0.85')).toBeInTheDocument();
    expect(screen.getByText('0.90')).toBeInTheDocument();
  });

  it('montre les recommandations stratégiques et les prochaines étapes', async () => {
    await ouvrirInterpretation();
    expect(screen.getByText(/créateurs autonomes et respectés/)).toBeInTheDocument();
    expect(screen.getByText(/Devenez le créateur/)).toBeInTheDocument();
    expect(screen.getByText(/Lancer le défi/)).toBeInTheDocument();
  });

  it('montre la grille psychologique de l’observation jusqu’à l’action', async () => {
    /* Les trois niveaux comptent : une observation sans action reste un
       constat, une action sans observation reste une opinion. */
    await ouvrirInterpretation();
    expect(screen.getByText("Ce qu'ils ressentent")).toBeInTheDocument();
    expect(screen.getByText(/34.3% des commentaires montrent/)).toBeInTheDocument();
    expect(screen.getByText(/phase d'exploration active/)).toBeInTheDocument();
    expect(screen.getByText(/structurent l'information/)).toBeInTheDocument();
  });

  it('n’affiche pas les entrées de grille absentes du rapport', async () => {
    await ouvrirInterpretation();
    expect(screen.queryByText("Ce qu'ils valorisent")).toBeNull();
  });
});
