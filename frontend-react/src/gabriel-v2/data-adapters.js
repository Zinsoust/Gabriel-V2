/** @typedef {import('./types.js').MissionView} MissionView */

const statusMap = {
  draft: 'draft', awaiting_input: 'awaiting_input', ready: 'ready',
  running: 'running', completed: 'completed', failed: 'failed',
};

function agentName(agent) {
  return agent?.name || agent?.label || agent?.id || 'Expert Gabriel';
}

/**
 * Adaptation temporaire de l'API actuelle et support du contrat V2 décrit
 * dans le brief. Les composants ne connaissent ni les recommandations
 * historiques ni la forme du futur orchestrateur.
 *
 * @param {Record<string, unknown>} payload
 * @returns {MissionView|null}
 */
export function missionFromConversationResponse(payload) {
  if (payload?.mission && typeof payload.mission === 'object') {
    const source = payload.mission;
    const agents = Array.isArray(payload.agents) ? payload.agents : source.selectedAgents || [];
    return {
      id: source.id || `mission-${Date.now()}`,
      title: source.title || 'Mission Gabriel',
      status: statusMap[source.status] || 'ready',
      objective: source.objective || '',
      agents: agents.map(agent => ({
        id: agent.id || agent.agentId || agentName(agent).toLowerCase().replace(/\s+/g, '-'),
        name: agentName(agent),
        status: agent.status || 'selected',
        description: agent.description || agent.role || '',
      })),
      deliverables: Array.isArray(payload.deliverables) ? payload.deliverables : [],
      panelType: payload.panel?.type || 'mission_summary',
      inputs: Array.isArray(source.inputs) ? source.inputs : [],
      execution: source.execution && typeof source.execution === 'object' ? {
        endpoint: source.execution.endpoint,
        method: source.execution.method || 'POST',
        label: source.execution.label || 'Lancer la mission',
        payload: source.execution.payload || {},
      } : null,
      jobId: source.job_id || null,
      progress: Number.isFinite(source.progress) ? source.progress : 0,
      error: source.error || '',
    };
  }

  // Compatibilité avec l'orchestrateur en place : il retourne une recommandation
  // décidée côté serveur. Le front l'affiche sans choisir lui-même un agent.
  if (payload?.recommendation?.agent) {
    const recommendation = payload.recommendation;
    return {
      id: `directive-${Date.now()}`,
      title: recommendation.label || 'Prochaine étape recommandée',
      status: 'ready',
      objective: recommendation.reason || 'Gabriel a analysé votre demande et vous indique la suite.',
      agents: [{
        id: recommendation.agent,
        name: recommendation.label || recommendation.agent,
        status: 'selected',
        description: 'Sélectionné par Gabriel',
      }],
      deliverables: [],
      panelType: 'mission_summary',
    };
  }
  return null;
}

export function workspaceInitial(title = '') {
  const pieces = title.trim().split(/\s+/).filter(Boolean);
  return (pieces.length ? pieces.slice(0, 2).map(piece => piece[0]) : ['G']).join('').toUpperCase();
}
