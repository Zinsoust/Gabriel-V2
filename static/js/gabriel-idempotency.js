const PROTECTED_POST_PATHS = new Set([
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
]);

const INSTALLATION_MARKER = Symbol.for('gabriel.idempotent-fetch');
const UNCERTAIN_KEY_TTL_MS = 5 * 60 * 1000;

function requestMethod(input, options) {
  return String(options?.method || input?.method || 'GET').toUpperCase();
}

function requestPath(input, baseUrl) {
  const rawUrl = typeof input === 'string' || input instanceof URL ? input : input?.url;
  try {
    return new URL(rawUrl, baseUrl).pathname;
  } catch (_) {
    return '';
  }
}

export function isProtectedPaidRequest(input, options = {}, baseUrl = 'http://localhost/') {
  const rawUrl = typeof input === 'string' || input instanceof URL ? input : input?.url;
  try {
    const requestUrl = new URL(rawUrl, baseUrl);
    const applicationUrl = new URL(baseUrl);
    return requestMethod(input, options) === 'POST'
      && requestUrl.origin === applicationUrl.origin
      && PROTECTED_POST_PATHS.has(requestUrl.pathname);
  } catch (_) {
    return false;
  }
}

function randomHex(byteLength = 16) {
  const bytes = new Uint8Array(byteLength);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
}

export function createIdempotencyKey() {
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error('La génération sécurisée de la clé d\'idempotence est indisponible.');
  }
  const randomPart = typeof globalThis.crypto.randomUUID === 'function'
    ? globalThis.crypto.randomUUID().replaceAll('-', '')
    : randomHex();
  return `gabriel-${randomPart}`;
}

function hashText(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function bodyFingerprint(body) {
  if (body == null) return 'none';
  if (typeof body === 'string') return `text:${body.length}:${hashText(body)}`;
  if (body instanceof URLSearchParams) {
    const text = body.toString();
    return `params:${text.length}:${hashText(text)}`;
  }
  if (typeof FormData !== 'undefined' && body instanceof FormData) {
    const fields = [];
    for (const [name, value] of body.entries()) {
      if (typeof value === 'string') {
        fields.push(`${name}:text:${value.length}:${hashText(value)}`);
      } else {
        fields.push(`${name}:blob:${value.size}:${value.type || '-'}`);
      }
    }
    return `form:${hashText(fields.join('|'))}`;
  }
  if (typeof Blob !== 'undefined' && body instanceof Blob) {
    return `blob:${body.size}:${body.type || '-'}`;
  }
  return `object:${Object.prototype.toString.call(body)}`;
}

function requestFingerprint(input, options, baseUrl) {
  const path = requestPath(input, baseUrl);
  return `${requestMethod(input, options)}:${path}:${bodyFingerprint(options?.body)}`;
}

function mergedHeaders(input, options) {
  const headers = new Headers(input instanceof Request ? input.headers : undefined);
  new Headers(options?.headers || undefined).forEach((value, name) => headers.set(name, value));
  return headers;
}

function isRetryableNetworkFailure(error) {
  return error instanceof TypeError && error?.name !== 'AbortError';
}

function responseForCaller(response) {
  return typeof response?.clone === 'function' ? response.clone() : response;
}

export function createGabrielFetch(nativeFetch, {
  baseUrl = globalThis.location?.href || 'http://localhost/',
  keyFactory = createIdempotencyKey,
} = {}) {
  if (typeof nativeFetch !== 'function') throw new TypeError('nativeFetch doit être une fonction.');
  const inFlight = new Map();
  const uncertainKeys = new Map();

  return function gabrielFetch(input, options = {}) {
    if (!isProtectedPaidRequest(input, options, baseUrl)) {
      return nativeFetch(input, options);
    }

    const fingerprint = requestFingerprint(input, options, baseUrl);
    const existing = inFlight.get(fingerprint);
    if (existing) return existing.then(responseForCaller);

    const headers = mergedHeaders(input, options);
    const uncertain = uncertainKeys.get(fingerprint);
    if (uncertain && uncertain.expiresAt <= Date.now()) uncertainKeys.delete(fingerprint);
    if (!headers.has('Idempotency-Key')) {
      headers.set(
        'Idempotency-Key',
        uncertainKeys.get(fingerprint)?.key || keyFactory(),
      );
    }
    const operationKey = headers.get('Idempotency-Key');
    const protectedOptions = { ...options, headers };

    const operation = (async () => {
      try {
        const response = await nativeFetch(input, protectedOptions);
        uncertainKeys.delete(fingerprint);
        return response;
      } catch (error) {
        if (!isRetryableNetworkFailure(error)) throw error;
        try {
          const response = await nativeFetch(input, protectedOptions);
          uncertainKeys.delete(fingerprint);
          return response;
        } catch (retryError) {
          if (isRetryableNetworkFailure(retryError)) {
            uncertainKeys.set(fingerprint, {
              key: operationKey,
              expiresAt: Date.now() + UNCERTAIN_KEY_TTL_MS,
            });
          }
          throw retryError;
        }
      }
    })();

    inFlight.set(fingerprint, operation);
    operation.then(
      () => inFlight.delete(fingerprint),
      () => inFlight.delete(fingerprint),
    );
    return operation.then(responseForCaller);
  };
}

export function installGabrielIdempotency(target = globalThis) {
  if (target[INSTALLATION_MARKER]) return target[INSTALLATION_MARKER];
  const originalFetch = target.fetch.bind(target);
  const protectedFetch = createGabrielFetch(originalFetch, {
    baseUrl: target.location?.href || 'http://localhost/',
  });
  Object.defineProperty(target, INSTALLATION_MARKER, {
    configurable: false,
    enumerable: false,
    value: { originalFetch, protectedFetch },
  });
  target.fetch = protectedFetch;
  return target[INSTALLATION_MARKER];
}
