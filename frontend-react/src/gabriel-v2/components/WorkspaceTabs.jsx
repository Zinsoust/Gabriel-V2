import React from 'react';
import { Icon } from '../icons.jsx';
import { agents } from '../agent-registry.js';

const tabs = [
  { id: 'conversation', label: 'Conversation', icon: 'message' },
  { id: 'psychologue', label: 'Psychologue', agent: agents.psychologue },
  { id: 'stratege', label: 'Stratège', agent: agents.stratege },
  { id: 'createur', label: 'Créateur', agent: agents.createur },
  { id: 'activity', label: 'Activité', icon: 'activity' },
  { id: 'memory', label: 'Mémoire', icon: 'archive' },
];

export function WorkspaceTabs({ currentTab, onChange }) {
  return <nav className="gv2-tabs" aria-label="Sections du workspace">
    {tabs.map(tab => {
      return <button key={tab.id} type="button" className={currentTab === tab.id ? 'is-active' : ''} onClick={() => onChange(tab.id)} aria-current={currentTab === tab.id ? 'page' : undefined} title={tab.label}>
        {tab.agent ? <img className="gv2-tab-agent-avatar" src={tab.agent.portrait} alt="" /> : <Icon name={tab.icon} size={18} />}<span>{tab.label}</span>
      </button>;
    })}
  </nav>;
}

export const tabLabels = Object.fromEntries(tabs.map(tab => [tab.id, tab.label]));
