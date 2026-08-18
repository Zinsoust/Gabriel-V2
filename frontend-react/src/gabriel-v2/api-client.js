/**
 * Contrat de transport commun à Gabriel V2.
 *
 * Le front et Flask sont toujours servis sur la même origine. Cette couche
 * évite qu'une redirection de connexion ou une page HTML de secours soit lue
 * comme du JSON (l'erreur historique « Unexpected token '<' »).
 */
export function isLoginResponse(response) {
  if (response.status === 401) return true;
  try {
    return response.redirected && new URL(response.url, window.location.origin).pathname === '/login';
  } catch (_) {
    return false;
  }
}

export async function readApiPayload(response, service) {
  const raw = await response.text();
  try {
    return raw ? JSON.parse(raw) : {};
  } catch (_) {
    const status = response.status ? ` (HTTP ${response.status})` : '';
    throw new Error(`${service} a renvoyé une réponse invalide${status}. Vérifiez que Gabriel est lancé avec son backend.`);
  }
}

export function fetchV2(url, options = {}) {
  const { headers, ...requestOptions } = options;
  return fetch(url, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json', ...(headers || {}) },
    ...requestOptions,
  });
}
