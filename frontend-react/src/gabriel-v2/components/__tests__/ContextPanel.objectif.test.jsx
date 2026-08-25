/* L'objectif du dossier est lu par Gabriel au début de chaque conversation
   (« Objectif déclaré : … » côté serveur). L'ancienne interface le demandait
   à la création ; la V2 ne le demandait nulle part. Ces tests verrouillent
   le fait qu'on puisse enfin le renseigner — et sans étape supplémentaire. */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContextPanel } from '../ContextPanel.jsx';

const DOSSIER = { folder_id: 'f-1', title: 'Lancement formation', objective: '' };

function afficher(workspace = DOSSIER, onUpdateWorkspace = vi.fn()) {
  render(<ContextPanel workspace={workspace} onUpdateWorkspace={onUpdateWorkspace} />);
  return { onUpdateWorkspace, user: userEvent.setup() };
}

beforeEach(() => cleanup());

describe('Objectif du dossier', () => {
  it('invite à le renseigner quand il est vide', () => {
    afficher();
    expect(screen.getByRole('button', { name: /objectif/i })).toBeInTheDocument();
  });

  it('affiche l’objectif existant', () => {
    afficher({ ...DOSSIER, objective: 'Remplir ma prochaine session' });
    expect(screen.getByText('Remplir ma prochaine session')).toBeInTheDocument();
  });

  it('s’écrit sur place, sans écran intermédiaire', async () => {
    /* Un clic suffit : le texte devient un champ. Pas de bouton « Modifier »,
       pas de fenêtre — c'est ce qui permet de l'ajouter au parcours sans
       l'alourdir. */
    const { user, onUpdateWorkspace } = afficher();
    await user.click(screen.getByRole('button', { name: /objectif/i }));
    const champ = screen.getByRole('textbox', { name: /objectif de ce dossier/i });
    await user.type(champ, 'Remplir ma prochaine session');
    await user.tab();
    expect(onUpdateWorkspace).toHaveBeenCalledWith('f-1', { objective: 'Remplir ma prochaine session' });
  });

  it('n’enregistre rien si le texte n’a pas changé', async () => {
    /* Sans ce garde-fou, ouvrir puis refermer le champ écrirait en base à
       chaque fois. */
    const { user, onUpdateWorkspace } = afficher({ ...DOSSIER, objective: 'Inchangé' });
    await user.click(screen.getByRole('button', { name: /Inchangé/ }));
    await user.tab();
    expect(onUpdateWorkspace).not.toHaveBeenCalled();
  });

  it('abandonne la saisie sur Échap', async () => {
    const { user, onUpdateWorkspace } = afficher({ ...DOSSIER, objective: 'Avant' });
    await user.click(screen.getByRole('button', { name: /Avant/ }));
    await user.type(screen.getByRole('textbox', { name: /objectif de ce dossier/i }), ' modifié');
    await user.keyboard('{Escape}');
    expect(onUpdateWorkspace).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /Avant/ })).toBeInTheDocument();
  });

  it('valide sur Entrée', async () => {
    const { user, onUpdateWorkspace } = afficher();
    await user.click(screen.getByRole('button', { name: /objectif/i }));
    await user.type(screen.getByRole('textbox', { name: /objectif de ce dossier/i }), 'Vendre plus{Enter}');
    expect(onUpdateWorkspace).toHaveBeenCalledWith('f-1', { objective: 'Vendre plus' });
  });

  it('ne propose pas d’objectif quand aucun dossier n’est ouvert', () => {
    /* Sans dossier, il n'y a rien à enregistrer : proposer le champ mènerait
       à une saisie perdue. */
    render(<ContextPanel workspace={null} onUpdateWorkspace={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /objectif/i })).toBeNull();
  });
});
