/* L'adresse et l'onglet ouvert doivent rester d'accord : c'est ce qui permet
   aux anciennes adresses de retomber sur le bon écran de la V2. */
import { describe, it, expect } from 'vitest';
import { tabFromUrl, urlWithTab } from '../../agent-registry.js';

describe('L’adresse décide de l’écran ouvert', () => {
  it('ouvre l’agent demandé par l’ancienne adresse', () => {
    expect(tabFromUrl('https://x.fr/orchestrateur?agent=stratege')).toBe('stratege');
    expect(tabFromUrl('https://x.fr/orchestrateur?agent=psychologue')).toBe('psychologue');
    expect(tabFromUrl('https://x.fr/orchestrateur?agent=createur')).toBe('createur');
  });

  it('ouvre la Conversation quand rien n’est demandé', () => {
    expect(tabFromUrl('https://x.fr/orchestrateur')).toBe('conversation');
  });

  it('ignore un agent qui n’existe pas', () => {
    /* Une adresse trafiquée ne doit pas ouvrir un écran vide. */
    expect(tabFromUrl('https://x.fr/orchestrateur?agent=nimportequoi')).toBe('conversation');
    expect(tabFromUrl('pas une adresse')).toBe('conversation');
  });

  it('inscrit l’agent ouvert dans l’adresse', () => {
    expect(urlWithTab('https://x.fr/orchestrateur', 'stratege'))
      .toContain('agent=stratege');
  });

  it('retire l’agent quand on revient sur un écran qui n’en est pas un', () => {
    expect(urlWithTab('https://x.fr/orchestrateur?agent=stratege', 'conversation'))
      .not.toContain('agent=');
  });

  it('ne perd pas le dossier en cours en changeant d’agent', () => {
    /* Sans cela, changer d'agent ferait basculer l'utilisateur sur un autre
       dossier que le sien. */
    const url = urlWithTab('https://x.fr/orchestrateur?folder_id=abc', 'psychologue');
    expect(url).toContain('folder_id=abc');
    expect(url).toContain('agent=psychologue');
  });
});
