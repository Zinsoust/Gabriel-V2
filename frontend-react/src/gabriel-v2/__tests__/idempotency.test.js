import { describe, expect, it, vi } from 'vitest';

import {
  createGabrielFetch,
  isProtectedPaidRequest,
} from '../../../../static/js/gabriel-idempotency.js';

const BASE_URL = 'https://gabriel.example/app';

function response(body = { success: true }, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function idempotencyKey(call) {
  return new Headers(call[1].headers).get('Idempotency-Key');
}

describe('transport idempotent des actions IA facturables', () => {
  it.each([
    '/analyze',
    '/api/v2/agents/psychologue/analyze',
    '/api/v2/agents/psychologue/cross-analyses',
    '/strategize',
    '/api/v2/agents/stratege/generate',
    '/creator/generate',
    '/api/v2/agents/createur/generate',
    '/creator/refine',
    '/api/v2/agents/createur/refine',
    '/context-chat',
    '/voice/transcribe',
    '/voice/speak',
    '/strategy-session/step',
    '/strategy_chat',
    '/orchestrator_chat',
    '/api/v2/conversations/messages',
  ])('reconnaît la route protégée %s', path => {
    expect(isProtectedPaidRequest(path, { method: 'POST' }, BASE_URL)).toBe(true);
  });

  it('ajoute une clé opaque à toute action protégée', async () => {
    const nativeFetch = vi.fn().mockResolvedValue(response());
    const protectedFetch = createGabrielFetch(nativeFetch, {
      baseUrl: BASE_URL,
      keyFactory: () => 'gabriel-random-only',
    });

    await protectedFetch('/analyze', { method: 'POST', body: '{"source":"fictive"}' });

    expect(nativeFetch).toHaveBeenCalledOnce();
    expect(idempotencyKey(nativeFetch.mock.calls[0])).toBe('gabriel-random-only');
  });

  it('réutilise exactement la même clé lors du retry réseau borné', async () => {
    const nativeFetch = vi.fn()
      .mockRejectedValueOnce(new TypeError('network interrupted'))
      .mockResolvedValueOnce(response());
    const protectedFetch = createGabrielFetch(nativeFetch, {
      baseUrl: BASE_URL,
      keyFactory: () => 'gabriel-stable-retry',
    });

    await protectedFetch('/strategize', { method: 'POST', body: '{}' });

    expect(nativeFetch).toHaveBeenCalledTimes(2);
    expect(idempotencyKey(nativeFetch.mock.calls[0])).toBe('gabriel-stable-retry');
    expect(idempotencyKey(nativeFetch.mock.calls[1])).toBe('gabriel-stable-retry');
  });

  it('conserve la clé pour une reprise après deux échecs réseau incertains', async () => {
    const nativeFetch = vi.fn()
      .mockRejectedValueOnce(new TypeError('network interrupted'))
      .mockRejectedValueOnce(new TypeError('network still interrupted'))
      .mockResolvedValueOnce(response());
    const keys = ['gabriel-uncertain-operation', 'gabriel-must-not-be-used'];
    const protectedFetch = createGabrielFetch(nativeFetch, {
      baseUrl: BASE_URL,
      keyFactory: () => keys.shift(),
    });
    const options = { method: 'POST', body: '{"message":"même opération"}' };

    await expect(protectedFetch('/context-chat', options)).rejects.toThrow('network still interrupted');
    await protectedFetch('/context-chat', options);

    expect(nativeFetch).toHaveBeenCalledTimes(3);
    expect(idempotencyKey(nativeFetch.mock.calls[0])).toBe('gabriel-uncertain-operation');
    expect(idempotencyKey(nativeFetch.mock.calls[1])).toBe('gabriel-uncertain-operation');
    expect(idempotencyKey(nativeFetch.mock.calls[2])).toBe('gabriel-uncertain-operation');
  });

  it('donne une nouvelle clé à une nouvelle action terminée', async () => {
    const nativeFetch = vi.fn().mockImplementation(() => Promise.resolve(response()));
    const keys = ['gabriel-action-1', 'gabriel-action-2'];
    const protectedFetch = createGabrielFetch(nativeFetch, {
      baseUrl: BASE_URL,
      keyFactory: () => keys.shift(),
    });

    await protectedFetch('/creator/generate', { method: 'POST', body: '{"brief":"A"}' });
    await protectedFetch('/creator/generate', { method: 'POST', body: '{"brief":"A"}' });

    expect(idempotencyKey(nativeFetch.mock.calls[0])).toBe('gabriel-action-1');
    expect(idempotencyKey(nativeFetch.mock.calls[1])).toBe('gabriel-action-2');
  });

  it('fusionne un double-clic en un appel réseau et fournit deux réponses lisibles', async () => {
    let release;
    const nativeFetch = vi.fn().mockImplementation(() => new Promise(resolve => { release = resolve; }));
    const protectedFetch = createGabrielFetch(nativeFetch, {
      baseUrl: BASE_URL,
      keyFactory: () => 'gabriel-double-click',
    });
    const options = { method: 'POST', body: '{"message":"bonjour"}' };

    const first = protectedFetch('/api/v2/conversations/messages', options);
    const second = protectedFetch('/api/v2/conversations/messages', options);
    expect(nativeFetch).toHaveBeenCalledOnce();

    release(response({ reply: 'ok' }));
    const [firstResponse, secondResponse] = await Promise.all([first, second]);
    await expect(firstResponse.json()).resolves.toEqual({ reply: 'ok' });
    await expect(secondResponse.json()).resolves.toEqual({ reply: 'ok' });
  });

  it('préserve le fonctionnement historique des routes non protégées', async () => {
    const nativeFetch = vi.fn().mockResolvedValue(response());
    const protectedFetch = createGabrielFetch(nativeFetch, { baseUrl: BASE_URL });

    await protectedFetch('/history', { method: 'GET' });

    expect(nativeFetch).toHaveBeenCalledOnce();
    expect(new Headers(nativeFetch.mock.calls[0][1].headers).has('Idempotency-Key')).toBe(false);
  });

  it('ne propage jamais la clé à une autre origine', async () => {
    const nativeFetch = vi.fn().mockResolvedValue(response());
    const protectedFetch = createGabrielFetch(nativeFetch, { baseUrl: BASE_URL });

    await protectedFetch('https://external.example/analyze', { method: 'POST', body: '{}' });

    expect(new Headers(nativeFetch.mock.calls[0][1].headers).has('Idempotency-Key')).toBe(false);
  });
});
