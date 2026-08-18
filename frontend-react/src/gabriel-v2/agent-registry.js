export const agents = {
  psychologue: {
    id: 'psychologue',
    name: 'Le Psychologue',
    shortName: 'Psychologue',
    role: 'Comprendre les émotions, motivations et freins de votre audience.',
    path: '/psychologue',
    portrait: '/static/images/psychologue-agent.jpeg',
    contextLabel: 'Analyse d’audience',
  },
  stratege: {
    id: 'stratege',
    name: 'Ariane',
    shortName: 'Ariane',
    role: 'Votre stratège de conseil.',
    path: '/stratege',
    portrait: '/static/images/personas/p2.jpeg',
    contextLabel: 'Décision stratégique',
  },
  createur: {
    id: 'createur',
    name: 'Le Créateur',
    shortName: 'Créateur',
    role: 'Faire vivre la stratégie dans des contenus prêts à produire.',
    path: '/createur',
    portrait: '/static/images/createur-agent.jpeg',
    contextLabel: 'Production de contenus',
  },
};

export function getAgent(id) {
  return agents[id] || null;
}

export function isAgentTab(id) {
  return Boolean(getAgent(id));
}
