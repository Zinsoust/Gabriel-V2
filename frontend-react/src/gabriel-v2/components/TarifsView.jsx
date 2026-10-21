import React, { useEffect, useState } from 'react';
import { fetchV2, isLoginResponse, readApiPayload } from '../api-client.js';

/* ── TarifsView ────────────────────────────────────────────────────────
   Portage natif de templates/tarifs.html pour un utilisateur déjà connecté
   dans le shell V2 — jusqu'ici le bouton « Tarifs » de la barre latérale et
   de l'en-tête menait à cette page servie telle quelle : thème forcé sombre,
   mise en page différente du reste de l'app, aucun lien visuel avec la V2.

   /tarifs (la route Flask) reste inchangée et continue de servir les
   visiteurs non connectés — décision prise plus tôt dans ce chantier, le
   shell V2 ne peut pas les servir. Cet écran est ce que voit uniquement un
   utilisateur déjà dans l'app : mêmes trois offres, mêmes prix, mêmes
   fonctionnalités listées, même contrat Stripe (POST /stripe/checkout,
   _STRIPE_PLANS dans app.py) — recopiées du HTML existant, rien inventé.

   Le paiement lui-même reprend exactement le mécanisme déjà bâti et
   vérifié dans Sidebar.jsx (panneau Paramètres → Changer d'offre) : un
   clic ouvre une session Stripe réelle, c'est la personne qui clique qui
   déclenche l'ouverture. */

const PLANS = { free: 'Gratuit', early_access: 'Early Access', standard: 'Standard', pme: 'PME' };

const OFFRES = [
  {
    id: 'early_access', badge: '🚀 Offre de lancement', nom: 'Early Access', prix: '29 €',
    desc: "Tarif verrouillé tant que l'offre de lancement est ouverte", accent: 'featured',
    cta: 'Rejoindre en Early Access — 29 €/mois',
    fonctionnalites: [
      'Analyses illimitées', 'Dashboard psychologique complet',
      'Personas détaillés (Jung · Frankl · Munroe)', 'Agent Stratège complet + entretien vocal',
      'Agent Créateur — scripts & posts', 'Mémoire stratégique',
      'Export PDF professionnel', 'Historique illimité',
    ],
  },
  {
    id: 'standard', nom: 'Standard', prix: '49 €',
    desc: 'Tarif permanent pour les nouveaux clients', cta: 'Commencer — 49 €/mois',
    fonctionnalites: [
      'Analyses illimitées', 'Dashboard psychologique complet',
      'Personas détaillés (Jung · Frankl · Munroe)', 'Agent Stratège complet + entretien vocal',
      'Agent Créateur — scripts & posts', 'Mémoire stratégique',
      'Export PDF professionnel', 'Historique illimité',
    ],
  },
  {
    id: 'pme', badge: '🏢 Équipe & besoins avancés', nom: 'PME', prix: '99 €',
    desc: 'Pour un usage équipe ou des besoins avancés', accent: 'premium', cta: 'Commencer — 99 €/mois',
    fonctionnalites: [
      'Tout de Standard', "Volume d'usage pensé pour une équipe",
      "Audit stratégique personnalisé à l'onboarding", 'Support prioritaire',
    ],
  },
];

function PlanCard({ offre, actif, enCours, onChoisir }) {
  return <div className={`gv2-tarifs-card${offre.accent ? ` is-${offre.accent}` : ''}${actif ? ' is-active' : ''}`}>
    {offre.badge && <div className="gv2-tarifs-badge">{offre.badge}</div>}
    <div className="gv2-tarifs-tier">Gabriel</div>
    <div className="gv2-tarifs-name">{offre.nom}</div>
    <div className="gv2-tarifs-price">{offre.prix}<span>/mois</span></div>
    <p className="gv2-tarifs-desc">{offre.desc}</p>
    <ul className="gv2-tarifs-features">
      {offre.fonctionnalites.map(f => <li key={f}><span aria-hidden="true">✓</span>{f}</li>)}
    </ul>
    {actif
      ? <div className="gv2-tarifs-current">Votre plan actuel</div>
      : <button type="button" className="gv2-tarifs-cta" disabled={enCours} onClick={() => onChoisir(offre.id)}>{enCours ? 'Redirection…' : offre.cta}</button>}
  </div>;
}

export function TarifsView() {
  const [usage, setUsage] = useState(null);
  const [enCours, setEnCours] = useState('');
  const [erreur, setErreur] = useState('');

  useEffect(() => {
    let vivant = true;
    fetchV2('/usage').then(async response => {
      const payload = await readApiPayload(response, 'Votre consommation').catch(() => null);
      if (vivant) setUsage(payload || {});
    }).catch(() => { if (vivant) setUsage({}); });
    return () => { vivant = false; };
  }, []);

  const plan = usage?.plan || 'free';

  async function choisir(offreId) {
    setEnCours(offreId);
    setErreur('');
    try {
      const response = await fetchV2('/stripe/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan: offreId }),
      });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const payload = await readApiPayload(response, 'Le paiement').catch(() => null);
      if (response.ok && payload?.url) { window.location.assign(payload.url); return; }
      setErreur(payload?.error || 'Erreur lors du paiement. Réessayez.');
    } catch (_) {
      setErreur('Erreur réseau. Réessayez.');
    }
    setEnCours('');
  }

  return <div className="gv2-tarifs">
    <header className="gv2-tarifs-hero">
      <h1>Une offre simple, sans version gratuite permanente</h1>
      <p>Trois plans, un seul principe : Gabriel doit vous faire gagner du temps dès le premier jour, pas dans six mois.</p>
      {plan !== 'free' && <div className="gv2-tarifs-current-badge">Plan actuel : {PLANS[plan] || plan}</div>}
    </header>

    <div className="gv2-tarifs-grid">
      {OFFRES.map(offre => <PlanCard key={offre.id} offre={offre} actif={offre.id === plan}
        enCours={enCours === offre.id} onChoisir={choisir} />)}
    </div>

    {erreur && <p className="gv2-tarifs-error" role="alert">{erreur}</p>}

    <p className="gv2-tarifs-note">
      Paiement sécurisé par Stripe · Annulable à tout moment · Sans engagement<br />
      Vous hésitez encore ? <a href="mailto:gabrielaigithub@gmail.com?subject=Demande%20d'audit%20Gabriel">Demandez une démo gratuite ou un audit personnalisé</a>.
    </p>
  </div>;
}
