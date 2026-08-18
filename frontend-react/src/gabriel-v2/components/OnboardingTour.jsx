import React, { useEffect, useRef, useState } from 'react';
import { Icon } from '../icons.jsx';

const steps = [
  {
    eyebrow: 'Gabriel.ai · L’IA 100 % business',
    title: 'Bienvenue dans votre espace de décision.',
    body: 'Gabriel réunit vos conversations, vos sources, vos spécialistes et vos décisions au même endroit.',
  },
  {
    eyebrow: '01 · Se repérer',
    title: 'Le Menu organise votre travail.',
    body: 'Vous y retrouvez vos workspaces, les agents disponibles, l’activité et les paramètres. Il peut rester fermé pour vous laisser toute la place nécessaire.',
    action: 'menu',
    actionLabel: 'Afficher le menu',
  },
  {
    eyebrow: '02 · Garder le cap',
    title: 'Les onglets indiquent où vous êtes.',
    body: 'Conversation, Psychologue, Stratège, Créateur, Activité et Mémoire sont toujours accessibles dans la barre supérieure. Le fil d’Ariane confirme la section ouverte.',
  },
  {
    eyebrow: '03 · Avancer',
    title: 'Commencez par la conversation.',
    body: 'Décrivez votre besoin. Gabriel crée le bon espace de travail, conserve le contexte utile et mobilise les spécialistes quand ils apportent une vraie valeur.',
  },
  {
    eyebrow: '04 · Personnaliser',
    title: 'Adaptez l’espace à votre rythme.',
    body: 'Le mode sombre est disponible dans Menu › Paramètres. Vous pouvez également ajuster les panneaux et revenir au guide à tout moment depuis ce même menu.',
  },
];

export function OnboardingTour({ onFinish, onOpenNavigation }) {
  const [index, setIndex] = useState(0);
  const primaryButtonRef = useRef(null);
  const step = steps[index];
  const isLast = index === steps.length - 1;

  useEffect(() => {
    primaryButtonRef.current?.focus();
  }, [index]);

  useEffect(() => {
    const handleKey = event => {
      if (event.key === 'Escape') onFinish();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onFinish]);

  function next() {
    if (isLast) onFinish(); else setIndex(current => current + 1);
  }

  return <div className="gv2-onboarding" role="presentation">
    <section className="gv2-onboarding-card" role="dialog" aria-modal="true" aria-labelledby="gv2-onboarding-title" aria-describedby="gv2-onboarding-copy">
      <header>
        <div className="gv2-onboarding-progress"><span>Guide rapide</span><strong>{index + 1} / {steps.length}</strong></div>
        <button type="button" onClick={onFinish} aria-label="Passer le guide" title="Passer le guide"><Icon name="close" size={17} /></button>
      </header>
      <div className="gv2-onboarding-content">
        <p>{step.eyebrow}</p>
        <h2 id="gv2-onboarding-title">{step.title}</h2>
        <div id="gv2-onboarding-copy">{step.body}</div>
        {step.action === 'menu' && <button className="gv2-onboarding-link" type="button" onClick={onOpenNavigation}><Icon name="menu" size={15} />{step.actionLabel}</button>}
      </div>
      <footer>
        <div className="gv2-onboarding-dots" aria-label={`Étape ${index + 1} sur ${steps.length}`}>{steps.map((item, itemIndex) => <i className={itemIndex === index ? 'is-active' : ''} key={item.title} />)}</div>
        <div className="gv2-onboarding-actions">
          {index > 0 && <button className="gv2-onboarding-back" type="button" onClick={() => setIndex(current => current - 1)}>Précédent</button>}
          <button className="gv2-onboarding-next" type="button" ref={primaryButtonRef} onClick={next}>{isLast ? 'Terminer' : 'Suivant'}<Icon name="chevronRight" size={16} /></button>
        </div>
      </footer>
    </section>
  </div>;
}
