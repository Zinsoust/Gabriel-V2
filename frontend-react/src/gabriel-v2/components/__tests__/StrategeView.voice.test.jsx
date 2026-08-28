/* Tranche C du Stratège natif : la couche vocale.

   Ce fichier teste STRICTEMENT ce que jsdom peut honnêtement vérifier :
   les bascules d'état (mode vocal activé/désactivé, voix choisie), leur
   persistance en localStorage, le choix entre reconnaissance navigateur et
   repli serveur selon les API disponibles, et la gestion d'erreur réseau.

   Ce que jsdom NE PEUT PAS vérifier — micro réel, précision de la
   reconnaissance vocale, lecture audio ElevenLabs réelle — n'est testé
   nulle part ici, et ce n'est pas une lacune propre à ce fichier :
   Conversation.jsx expose la même dictée en production aujourd'hui sans
   aucun test dessus (aucun mock de SpeechRecognition/getUserMedia dans
   __tests__/ avant celui-ci). Cette couche est vérifiée à la main dans un
   vrai navigateur — autorisation micro accordée/refusée, cycle complet
   enregistrement → transcription → lecture, thèmes clair et sombre. */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrategeView } from '../StrategeView.jsx';

const WORKSPACE = { folder_id: 'f-1', analysis_id: '', strategy_id: '' };
const OUVERTURE = { messages: [{ role: 'assistant', content: 'Parlez-moi de votre entreprise.' }],
  context_progress: { understood: [], remaining: ['Identité'] }, is_ready: false, updated_context: {} };

function routeFetch(routes) {
  return vi.fn((url, options = {}) => {
    for (const [pattern, handler] of routes) {
      if (typeof pattern === 'string' ? url === pattern : pattern.test(url)) {
        const body = handler(url, options);
        if (body.blob) {
          return Promise.resolve({ status: body.status || 200, ok: (body.status || 200) < 400, redirected: false, url, blob: () => Promise.resolve(body.blob) });
        }
        return Promise.resolve({ status: body.status || 200, ok: (body.status || 200) < 400, redirected: false, url,
          text: () => Promise.resolve(JSON.stringify(body.json)) });
      }
    }
    throw new Error(`Route non simulée : ${url}`);
  });
}

beforeEach(() => {
  cleanup();
  window.localStorage.clear();
  window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  window.HTMLMediaElement.prototype.pause = vi.fn();
  if (!window.URL.createObjectURL) window.URL.createObjectURL = vi.fn(() => 'blob:mock');
});
afterEach(() => { delete global.fetch; vi.restoreAllMocks(); delete window.SpeechRecognition; delete window.webkitSpeechRecognition; delete navigator.mediaDevices; delete window.MediaRecorder; });

describe('Mode vocal : bascule et persistance', () => {
  it('est désactivé par défaut, sans rien lire dans localStorage à tort', async () => {
    global.fetch = routeFetch([[/^\/business-context/, () => ({ json: OUVERTURE })]]);
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByRole('button', { name: /Mode vocal/ }));
    expect(screen.getByRole('button', { name: /Mode vocal/ })).toHaveAttribute('aria-pressed', 'false');
  });

  it('active le mode vocal au clic et le mémorise', async () => {
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: OUVERTURE })],
      [/^\/voice\/voices/, () => ({ json: { voices: [{ id: 'v1', label: 'Adam' }], available: true } })],
    ]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByRole('button', { name: /Mode vocal/ }));
    await user.click(screen.getByRole('button', { name: /Mode vocal/ }));
    expect(screen.getByRole('button', { name: /Mode vocal/ })).toHaveAttribute('aria-pressed', 'true');
    expect(window.localStorage.getItem('gabriel_voice_mode')).toBe('1');
  });

  it('reprend le mode vocal déjà activé lors d’une session précédente', async () => {
    window.localStorage.setItem('gabriel_voice_mode', '1');
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: OUVERTURE })],
      [/^\/voice\/voices/, () => ({ json: { voices: [], available: true } })],
    ]);
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => expect(screen.getByRole('button', { name: /Mode vocal/ })).toHaveAttribute('aria-pressed', 'true'));
  });

  it('charge le catalogue des voix dès l’ouverture si le mode vocal était déjà actif', async () => {
    /* Un mode vocal repris de la session précédente (localStorage) ne doit
       pas laisser le sélecteur invisible faute d'avoir été rebasculé — trouvé
       en testant une session reprise dans un vrai navigateur : la lecture
       fonctionnait déjà (elle ne dépend que du mode, pas du catalogue), mais
       le sélecteur restait vide indéfiniment. */
    window.localStorage.setItem('gabriel_voice_mode', '1');
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: OUVERTURE })],
      [/^\/voice\/voices/, () => ({ json: { voices: [{ id: 'v1', label: 'Adam' }], available: true } })],
    ]);
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => expect(screen.getByLabelText('Voix de Gabriel')).toBeInTheDocument());
  });

  it('mémorise la voix choisie', async () => {
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: OUVERTURE })],
      [/^\/voice\/voices/, () => ({ json: { voices: [{ id: 'v1', label: 'Adam' }, { id: 'v2', label: 'Arnold' }], available: true } })],
    ]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByRole('button', { name: /Mode vocal/ }));
    await user.click(screen.getByRole('button', { name: /Mode vocal/ }));
    await waitFor(() => screen.getByLabelText('Voix de Gabriel'));
    await userEvent.selectOptions(screen.getByLabelText('Voix de Gabriel'), 'v2');
    expect(window.localStorage.getItem('gabriel_voice_id')).toBe('v2');
  });
});

describe('Lecture à voix haute des réponses', () => {
  it('lit la réponse du serveur quand le mode vocal est actif', async () => {
    window.localStorage.setItem('gabriel_voice_mode', '1');
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: OUVERTURE })],
      [/^\/voice\/voices/, () => ({ json: { voices: [], available: true } })],
      [/^\/context-chat$/, () => ({ json: { reply: { display_text: 'Et votre cible ?', speech_text: 'Votre cible ?' },
        context_progress: null, is_ready: false, updated_context: {} } })],
      [/^\/voice\/speak$/, () => ({ blob: new Blob(['audio']) })],
    ]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByPlaceholderText('Écrivez votre réponse…'));
    await user.type(screen.getByPlaceholderText('Écrivez votre réponse…'), 'Coaching{Enter}');
    await waitFor(() => {
      const appel = global.fetch.mock.calls.find(([url]) => url === '/voice/speak');
      expect(appel).toBeTruthy();
      expect(JSON.parse(appel[1].body).text).toBe('Votre cible ?');
    });
  });

  it('ne demande aucune lecture quand le mode vocal est désactivé', async () => {
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: OUVERTURE })],
      [/^\/context-chat$/, () => ({ json: { reply: { display_text: 'Et votre cible ?' }, context_progress: null, is_ready: false, updated_context: {} } })],
    ]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByPlaceholderText('Écrivez votre réponse…'));
    await user.type(screen.getByPlaceholderText('Écrivez votre réponse…'), 'Coaching{Enter}');
    await waitFor(() => expect(screen.getByText('Et votre cible ?')).toBeInTheDocument());
    expect(global.fetch.mock.calls.some(([url]) => url === '/voice/speak')).toBe(false);
  });

  it('reste silencieux sans planter si la synthèse échoue', async () => {
    window.localStorage.setItem('gabriel_voice_mode', '1');
    global.fetch = routeFetch([
      [/^\/business-context/, () => ({ json: OUVERTURE })],
      [/^\/voice\/voices/, () => ({ json: { voices: [], available: true } })],
      [/^\/context-chat$/, () => ({ json: { reply: { display_text: 'Et votre cible ?' }, context_progress: null, is_ready: false, updated_context: {} } })],
      [/^\/voice\/speak$/, () => ({ status: 502, json: { error: 'Erreur de synthèse vocale.' } })],
    ]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByPlaceholderText('Écrivez votre réponse…'));
    await user.type(screen.getByPlaceholderText('Écrivez votre réponse…'), 'Coaching{Enter}');
    await waitFor(() => expect(screen.getByText('Et votre cible ?')).toBeInTheDocument());
  });
});

describe('Dictée : choix de l’API selon ce que le navigateur expose', () => {
  it('propose le micro quand SpeechRecognition est disponible', async () => {
    window.SpeechRecognition = vi.fn();
    global.fetch = routeFetch([[/^\/business-context/, () => ({ json: OUVERTURE })]]);
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Répondre à la voix' })).toBeInTheDocument());
  });

  it('utilise la reconnaissance du navigateur en priorité quand elle existe', async () => {
    const start = vi.fn();
    class FakeRecognition { start = start; abort = vi.fn(); }
    window.SpeechRecognition = FakeRecognition;
    global.fetch = routeFetch([[/^\/business-context/, () => ({ json: OUVERTURE })]]);
    const user = userEvent.setup();
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByRole('button', { name: 'Répondre à la voix' }));
    await user.click(screen.getByRole('button', { name: 'Répondre à la voix' }));
    expect(start).toHaveBeenCalledTimes(1);
    expect(global.fetch.mock.calls.some(([url]) => url === '/voice/transcribe')).toBe(false);
  });

  it('n’affiche pas le micro quand aucune API vocale n’est disponible', async () => {
    global.fetch = routeFetch([[/^\/business-context/, () => ({ json: OUVERTURE })]]);
    render(<StrategeView workspace={WORKSPACE} />);
    await waitFor(() => screen.getByPlaceholderText('Écrivez votre réponse…'));
    expect(screen.queryByRole('button', { name: 'Répondre à la voix' })).toBeNull();
  });
});
