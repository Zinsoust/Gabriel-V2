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

/* Les anciennes adresses (/psychologue, /stratege, /createur) renvoient vers
   la V2 en indiquant l'agent visé : /orchestrateur?agent=stratege. Sans cette
   lecture, toutes ces redirections atterriraient sur la Conversation. */
export function tabFromUrl(href) {
  let demande = null;
  try { demande = new URL(href).searchParams.get('agent'); } catch { return 'conversation'; }
  return demande && isAgentTab(demande) ? demande : 'conversation';
}

/* L'adresse suit l'onglet ouvert : recharger la page rouvre le même écran et
   le lien reste partageable. Renvoie l'adresse à inscrire dans l'historique. */
export function urlWithTab(href, tab) {
  const url = new URL(href);
  if (isAgentTab(tab)) url.searchParams.set('agent', tab);
  else url.searchParams.delete('agent');
  return url.toString();
}
