import React from 'react';
import { Icon } from '../icons.jsx';
import { agents } from '../agent-registry.js';

// Hiérarchie produit : le Psychologue d'abord (porte d'entrée), puis ses
// prolongements (stratégie, contenu), puis la conversation et le suivi.
const tabs = [
  { id: 'psychologue', label: 'Psychologue', agent: agents.psychologue, group: 'entree' },
  { id: 'stratege', label: 'Ariane', agent: agents.stratege, group: 'prolongements' },
  { id: 'createur', label: 'Créateur', agent: agents.createur, group: 'prolongements' },
  { id: 'conversation', label: 'Conversation', icon: 'message', group: 'suivi' },
  { id: 'activity', label: 'Activité', icon: 'activity', group: 'suivi' },
  { id: 'memory', label: 'Mémoire', icon: 'archive', group: 'suivi' },
];

export function WorkspaceTabs({ currentTab, onChange }) {
  return <nav className="gv2-tabs" aria-label="Sections de l’espace de travail">
    {tabs.map((tab, index) => <React.Fragment key={tab.id}>
      {/* Un filet sépare les familles : comprendre, prolonger, acquérir, suivre. */}
      {index > 0 && tabs[index - 1].group !== tab.group && <span className="gv2-tabs-divider" aria-hidden="true" />}
      <button type="button" className={currentTab === tab.id ? 'is-active' : ''} onClick={() => onChange(tab.id)} aria-current={currentTab === tab.id ? 'page' : undefined} title={tab.label}>
        {tab.agent ? <img className="gv2-tab-agent-avatar" src={tab.agent.portrait} alt="" /> : <Icon name={tab.icon} size={18} />}<span>{tab.label}</span>
      </button>
    </React.Fragment>)}
  </nav>;
}

export const tabLabels = Object.fromEntries(tabs.map(tab => [tab.id, tab.label]));
