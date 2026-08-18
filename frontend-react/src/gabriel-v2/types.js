/**
 * Contrats de présentation de Gabriel V2.
 *
 * Ces structures restent volontairement indépendantes du backend actuel :
 * l'adaptateur transforme une réponse de l'orchestrateur en état d'interface,
 * sans prendre de décision métier dans les composants React.
 */

/** @typedef {'pending'|'selected'|'running'|'completed'|'failed'} AgentStatus */
/** @typedef {'draft'|'awaiting_input'|'ready'|'running'|'completed'|'failed'} MissionStatus */

/**
 * @typedef {Object} Workspace
 * @property {string} folder_id
 * @property {string} title
 * @property {string=} objective
 * @property {string=} folder_type
 */

/**
 * @typedef {Object} AgentAssignment
 * @property {string} id
 * @property {string} name
 * @property {AgentStatus} status
 * @property {string=} description
 */

/**
 * @typedef {Object} MissionView
 * @property {string} id
 * @property {string} title
 * @property {MissionStatus} status
 * @property {string=} objective
 * @property {AgentAssignment[]} agents
 * @property {{title: string, type?: string}[]} deliverables
 * @property {string=} panelType
 * @property {{id: string, label: string, value?: string, help?: string}[]} inputs
 * @property {{endpoint: string, method: string, label: string, payload: object}|null} execution
 * @property {string|null} jobId
 * @property {number} progress
 * @property {string} error
 */

/** @typedef {{id: string, role: 'user'|'assistant'|'event'|'error', content: string, createdAt: string, mission?: MissionView}} ConversationItem */

export {};
