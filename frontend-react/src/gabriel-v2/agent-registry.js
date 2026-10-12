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

/* Le Psychologue est la porte d'entrée de Gabriel (repositionnement du
   13/09/2026) : une adresse sans écran demandé l'ouvre. Les anciennes adresses
   (/psychologue, /stratege, /createur) renvoient vers
   /orchestrateur?agent=… et retombent sur le bon écran. La Conversation reste
   accessible, mais doit désormais être demandée explicitement. */
export const DEFAULT_TAB = 'psychologue';

function isAddressableTab(id) {
  return isAgentTab(id) || id === 'conversation' || id === 'prospect';
}

export function tabFromUrl(href) {
  let demande = null;
  try { demande = new URL(href).searchParams.get('agent'); } catch { return DEFAULT_TAB; }
  return demande && isAddressableTab(demande) ? demande : DEFAULT_TAB;
}

/* L'adresse suit l'onglet ouvert : recharger la page rouvre le même écran et
   le lien reste partageable. Renvoie l'adresse à inscrire dans l'historique. */
export function urlWithTab(href, tab) {
  const url = new URL(href);
  if (tab !== DEFAULT_TAB && isAddressableTab(tab)) url.searchParams.set('agent', tab);
  else url.searchParams.delete('agent');
  return url.toString();
}
