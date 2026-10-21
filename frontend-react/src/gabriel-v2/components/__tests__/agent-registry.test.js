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

  it('ouvre le Psychologue quand rien n’est demandé : c’est la porte d’entrée', () => {
    expect(tabFromUrl('https://x.fr/orchestrateur')).toBe('psychologue');
  });

  it('garde la Conversation accessible par son adresse', () => {
    expect(tabFromUrl('https://x.fr/orchestrateur?agent=conversation')).toBe('conversation');
    expect(urlWithTab('https://x.fr/orchestrateur', 'conversation')).toContain('agent=conversation');
  });

  it('redirige une ancienne adresse Prospect vers le Psychologue', () => {
    expect(tabFromUrl('https://x.fr/orchestrateur?agent=prospect')).toBe('psychologue');
    expect(urlWithTab('https://x.fr/orchestrateur', 'prospect')).not.toContain('agent=');
  });

  it('ignore un agent qui n’existe pas', () => {
    /* Une adresse trafiquée ne doit pas ouvrir un écran vide. */
    expect(tabFromUrl('https://x.fr/orchestrateur?agent=nimportequoi')).toBe('psychologue');
    expect(tabFromUrl('pas une adresse')).toBe('psychologue');
  });

  it('inscrit l’agent ouvert dans l’adresse', () => {
    expect(urlWithTab('https://x.fr/orchestrateur', 'stratege'))
      .toContain('agent=stratege');
  });

  it('garde une adresse nue pour l’écran d’entrée', () => {
    expect(urlWithTab('https://x.fr/orchestrateur?agent=stratege', 'psychologue'))
      .not.toContain('agent=');
  });

  it('retire le paramètre pour un écran qui ne se partage pas', () => {
    expect(urlWithTab('https://x.fr/orchestrateur?agent=stratege', 'memory'))
      .not.toContain('agent=');
  });

  it('ne perd pas le dossier en cours en changeant d’agent', () => {
    /* Sans cela, changer d'agent ferait basculer l'utilisateur sur un autre
       dossier que le sien. */
    const url = urlWithTab('https://x.fr/orchestrateur?folder_id=abc', 'stratege');
    expect(url).toContain('folder_id=abc');
    expect(url).toContain('agent=stratege');
  });
});
