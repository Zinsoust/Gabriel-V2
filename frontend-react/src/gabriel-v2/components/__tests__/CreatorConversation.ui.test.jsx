import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CreatorConversation } from '../CreatorConversation.jsx';

const settings = {
  contentType: 'script',
  channel: '',
  tone: 'expert',
  emotion: '',
  creativity: 50,
  objective: '',
  generateVariant: false,
};

function renderCreator(overrides = {}) {
  const props = {
    workspace: null,
    settings,
    refinementRequest: null,
    onHasOutputChange: vi.fn(),
    onWorkspaceChange: vi.fn(),
    onSettingsChange: vi.fn(),
    contextCollapsed: true,
    onShowContext: vi.fn(),
    ...overrides,
  };
  render(<CreatorConversation {...props} />);
  return props;
}

beforeEach(() => {
  Element.prototype.scrollTo = vi.fn();
});

describe('Studio du Créateur', () => {
  it('conserve les trois accès rapides de format', () => {
    renderCreator();
    expect(screen.getByRole('tab', { name: 'Post' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Script' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Thread' })).toBeInTheDocument();
  });

  it('branche les formats compacts sur les réglages Gabriel', async () => {
    const user = userEvent.setup();
    const onSettingsChange = vi.fn();
    renderCreator({ onSettingsChange });

    await user.click(screen.getByRole('tab', { name: 'Post' }));
    expect(onSettingsChange).toHaveBeenCalledWith({ contentType: 'linkedin' });
  });

  it('ouvre le véritable panneau Atelier du shell', async () => {
    const user = userEvent.setup();
    const onShowContext = vi.fn();
    renderCreator({ onShowContext });

    await user.click(screen.getAllByRole('button', { name: /Atelier/ })[0]);
    expect(onShowContext).toHaveBeenCalledOnce();
  });

  it('garde une demande accessible et le bouton de création désactivé à vide', () => {
    renderCreator();
    expect(screen.getByLabelText('Demande de création')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Créer le contenu' })).toBeDisabled();
  });

  it('sépare le canvas scrollable du composer stable', () => {
    renderCreator();
    const stream = document.querySelector('.gv2-creator-stream');
    const composer = document.querySelector('.gv2-creator-composer-dock');
    expect(stream).not.toContainElement(composer);
    expect(stream?.parentElement).toContainElement(composer);
  });
});

describe('Sources de contexte du Créateur', () => {
  function espionnerGeneration() {
    const envois = [];
    global.fetch = vi.fn(async (adresse, options = {}) => {
      if (String(adresse).includes('/createur/generate')) {
        envois.push(JSON.parse(options.body));
        return { ok: false, status: 500, redirected: false, url: 'http://x', text: async () => JSON.stringify({ error: 'arrêt du test' }) };
      }
      return { ok: true, status: 200, redirected: false, url: 'http://x', text: async () => JSON.stringify([]) };
    });
    return envois;
  }

  async function demander(user) {
    await user.type(screen.getByRole('textbox', { name: 'Demande de création' }), 'Un script vidéo sur la reconversion');
    await user.click(screen.getByRole('button', { name: /Lancer|Créer|Générer/ }));
  }

  it('utilise l’analyse du Psychologue par défaut, sans imposer la stratégie d’Ariane', async () => {
    const envois = espionnerGeneration();
    const user = userEvent.setup();
    renderCreator({ workspace: { folder_id: 'f1', analysis_id: 'a-1', strategy_id: 's-1' } });

    expect(screen.getByRole('button', { name: /Analyse du Psychologue/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /Stratégie d’Ariane/ })).toHaveAttribute('aria-pressed', 'false');
    await demander(user);
    expect(envois[0]).toMatchObject({ use_psycho: true, analysis_id: 'a-1', use_strategy: false });
    expect(envois[0].strategy_id).toBeUndefined();
  });

  it('ajoute la stratégie d’Ariane seulement quand on l’active', async () => {
    const envois = espionnerGeneration();
    const user = userEvent.setup();
    renderCreator({ workspace: { folder_id: 'f1', analysis_id: 'a-1', strategy_id: 's-1' } });
    await user.click(screen.getByRole('button', { name: /Stratégie d’Ariane/ }));
    await demander(user);
    expect(envois[0]).toMatchObject({ use_strategy: true, strategy_id: 's-1' });
  });

  it('reprend la dernière analyse vue dans le Psychologue, même hors espace', async () => {
    const envois = espionnerGeneration();
    const user = userEvent.setup();
    renderCreator({ lastAnalysis: { id: 'a-9', title: 'Vidéo IA locale' } });
    expect(screen.getByText('Vidéo IA locale')).toBeInTheDocument();
    await demander(user);
    expect(envois[0]).toMatchObject({ use_psycho: true, analysis_id: 'a-9' });
  });

  it('écrit depuis une Cross Analyse ouverte, sans la confondre avec une analyse simple', async () => {
    const envois = espionnerGeneration();
    const user = userEvent.setup();
    renderCreator({ lastAnalysis: { id: 'cross_290be78025464751', cross: true, title: 'Cross Analyse · IA locale × IA débutants' } });
    expect(screen.getByText('Cross Analyse · IA locale × IA débutants')).toBeInTheDocument();
    await demander(user);
    expect(envois[0]).toMatchObject({ use_psycho: true, cross_analysis_id: 'cross_290be78025464751' });
    expect(envois[0].analysis_id).toBeUndefined();
  });

  it('fonctionne seul quand on coupe l’analyse', async () => {
    const envois = espionnerGeneration();
    const user = userEvent.setup();
    renderCreator({ lastAnalysis: { id: 'a-9', title: 'Vidéo IA locale' } });
    await user.click(screen.getByRole('button', { name: /Analyse du Psychologue/ }));
    await demander(user);
    expect(envois[0]).toMatchObject({ use_psycho: false, use_strategy: false });
    expect(envois[0].analysis_id).toBeUndefined();
  });
});

describe('Rendu des créations', () => {
  // Résultat réel d'une génération (script vidéo, avec l'analyse du Psychologue).
  const SCRIPT = JSON.parse(JSON.stringify(require('./fixtures/createur-script-reel.json')));

  async function generer(resultat, workspace = { folder_id: 'f1', analysis_id: 'a-1' }) {
    global.fetch = vi.fn(async (adresse) => {
      const url = String(adresse);
      const corps = url.includes('/createur/generate') ? { job_id: 'job-cr', status: 'running' }
        : url.includes('/jobs/job-cr') ? { status: 'done', data: resultat } : [];
      return { ok: true, status: 200, redirected: false, url: 'http://x', text: async () => JSON.stringify(corps) };
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderCreator({ workspace });
    await user.type(screen.getByRole('textbox', { name: 'Demande de création' }), 'Script vidéo de 60 secondes');
    await user.click(screen.getByRole('button', { name: /Lancer|Créer|Générer/ }));
    await vi.advanceTimersByTimeAsync(2500);
    vi.useRealTimers();
  }

  it('affiche un script comme un document : séquences minutées et notes de réalisation', async () => {
    await generer(SCRIPT);
    const doc = await screen.findByRole('heading', { level: 2, name: /révéler vos trésors cachés/ });
    expect(doc).toBeInTheDocument();
    const temps = [...document.querySelectorAll('.gv2-cdoc-time')].map(n => n.textContent);
    expect(temps).toEqual(SCRIPT.content.sections.map(s => s.secondes));
    expect(document.querySelectorAll('.gv2-cdoc-field.is-note')).toHaveLength(SCRIPT.content.sections.length);
    expect(screen.getByText('Accroche alternative')).toBeInTheDocument();
    expect(screen.getByText('Émotion visée')).toBeInTheDocument();
  });

  it('dit quelles sources ont nourri la création et montre la relecture', async () => {
    await generer(SCRIPT);
    expect(await screen.findByText('Analyse du Psychologue utilisée')).toBeInTheDocument();
    expect(screen.getByText('Sans stratégie d’Ariane')).toBeInTheDocument();
    expect(screen.getByText('Clarté')).toBeInTheDocument();
  });

  it('garde le rendu texte pour une création sans structure, listes comprises', async () => {
    await generer({ full_text: 'Une phrase d’introduction\n- premier point\n- second point', content: 'x', success: true });
    expect(await screen.findByText('premier point')).toBeInTheDocument();
    expect(screen.getByText('premier point').tagName).toBe('LI');
    expect(document.querySelector('.gv2-cdoc')).toBeNull();
  });
});

describe('Garde anti-invention à l’écran', () => {
  it('fait ressortir les emplacements à compléter et explique pourquoi', async () => {
    const resultat = {
      content: { titre_video: 'Votre IA locale en [chiffre à vérifier]', sections: [{ section: 'Preuve', secondes: '45-55', texte: 'Il livre [chiffre à vérifier] plus vite. [pause] Voici la démo.' }] },
      full_text: 'x', success: true, unverified_figures: ['10 min', '3x'],
    };
    global.fetch = vi.fn(async (adresse) => {
      const url = String(adresse);
      const corps = url.includes('/createur/generate') ? { job_id: 'job-g', status: 'running' } : url.includes('/jobs/job-g') ? { status: 'done', data: resultat } : [];
      return { ok: true, status: 200, redirected: false, url: 'http://x', text: async () => JSON.stringify(corps) };
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderCreator({ workspace: { folder_id: 'f1' } });
    await user.type(screen.getByRole('textbox', { name: 'Demande de création' }), 'Script');
    await user.click(screen.getByRole('button', { name: /Lancer|Créer|Générer/ }));
    await vi.advanceTimersByTimeAsync(2500);
    vi.useRealTimers();

    expect(await screen.findByText(/2 chiffres non vérifiables retirés/)).toBeInTheDocument();
    const marques = [...document.querySelectorAll('.gv2-cdoc-placeholder')].map(n => n.textContent);
    expect(marques).toEqual(['chiffre à vérifier', 'chiffre à vérifier']);
    expect(document.body.textContent).toContain('[pause]');
  });
});
