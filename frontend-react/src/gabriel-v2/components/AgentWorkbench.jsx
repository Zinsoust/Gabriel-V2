import React from 'react';
import { ConversationFeed, Composer } from './Conversation.jsx';
import { AgentWorkspace } from './AgentWorkspace.jsx';
import { Icon } from '../icons.jsx';

/**
 * Surface de travail commune aux agents : la discussion ne disparaît jamais
 * quand un outil est ouvert. Seul le contenu de droite change avec l'agent.
 */
export function AgentWorkbench({
  agentId,
  agent,
  workspace,
  items,
  firstName,
  isSubmitting,
  onSend,
  discussionCollapsed,
  onToggleDiscussion,
  onResizeStart,
  onResizeKey,
  onResizeReset,
  onReturnToConversation,
  onNavigateAgent,
  contextCollapsed,
  onShowContext,
  darkMode,
}) {
  return <section className={`gv2-agent-workbench${discussionCollapsed ? ' is-discussion-collapsed' : ''}`} aria-label={`Espace de travail ${agent.name}`}>
    <section className="gv2-discussion-panel" aria-label="Discussion avec Gabriel">
      <header className="gv2-discussion-header">
        <span className="gv2-discussion-mark">G</span>
        <div className="gv2-discussion-heading"><strong>Conversation</strong><span>Gabriel garde le fil de ce travail</span></div>
        <button type="button" className="gv2-discussion-toggle" onClick={onToggleDiscussion} aria-label={discussionCollapsed ? 'Afficher la conversation' : 'Réduire la conversation'} title={discussionCollapsed ? 'Afficher la conversation' : 'Réduire la conversation'}>
          <Icon name="chevronRight" size={16} />
        </button>
      </header>
      <div className="gv2-discussion-content">
        <ConversationFeed items={items} firstName={firstName} isSubmitting={isSubmitting} compact />
        <Composer onSend={onSend} disabled={isSubmitting} compact />
      </div>
    </section>

    <button className="gv2-workbench-resize-handle" type="button" onPointerDown={onResizeStart} onDoubleClick={onResizeReset} onKeyDown={onResizeKey} aria-label="Redimensionner la conversation et l’espace agent" title="Glisser pour redimensionner · double clic pour réinitialiser" />

    <AgentWorkspace agentId={agentId} workspace={workspace} onReturnToConversation={onReturnToConversation} onNavigate={onNavigateAgent} contextCollapsed={contextCollapsed} onShowContext={onShowContext} darkMode={darkMode} />
  </section>;
}
