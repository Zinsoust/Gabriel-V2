import React from 'react';
import { createRoot } from 'react-dom/client';
import { AppShell } from './components/AppShell.jsx';
import './styles.css';

const bootstrap = window.__GABRIEL_V2__ || { workspaces: [], selectedWorkspaceId: null, user: {} };
createRoot(document.getElementById('gabriel-v2-root')).render(<AppShell bootstrap={bootstrap} />);
