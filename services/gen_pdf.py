# ─── Gabriel — Générateur PDF dynamique ──────────────────────────────────────
#
# Usage:
#   from services.gen_pdf import generate_analysis_pdf, generate_strategy_pdf
#   pdf_bytes = generate_analysis_pdf(entry)
#   pdf_bytes = generate_strategy_pdf(strat_dict, entry_dict)

import io
import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )
    # ── Palette Gabriel champagne / noir ─────────────────────────────────────
    _NOIR       = colors.HexColor('#0D0D10')
    _CHAMPAGNE  = colors.HexColor('#D8B982')
    _CHAMP_DARK = colors.HexColor('#B89650')
    _BLANC      = colors.HexColor('#FAFAF8')
    _GRIS_PALE  = colors.HexColor('#F5F3EF')
    _GRIS_MID   = colors.HexColor('#E0D9CF')
    _GRIS_TEXTE = colors.HexColor('#3A3530')
    _HAS_REPORTLAB = True
except ImportError:
    _HAS_REPORTLAB = False
    # Stubs so module-level references don't crash
    _NOIR = _CHAMPAGNE = _CHAMP_DARK = _BLANC = _GRIS_PALE = _GRIS_MID = _GRIS_TEXTE = None


# ─────────────────────────────────────────────────────────────────────────────
# Styles
# ─────────────────────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()

    def add(name, **kw):
        base.add(ParagraphStyle(name=name, **kw))

    add('GTitle',
        fontName='Helvetica-Bold', fontSize=20, textColor=_BLANC,
        leading=26, spaceAfter=0, alignment=TA_LEFT)
    add('GSubMeta',
        fontName='Helvetica', fontSize=8, textColor=_CHAMPAGNE,
        leading=12, spaceAfter=0, alignment=TA_LEFT)
    add('GSection',
        fontName='Helvetica-Bold', fontSize=9, textColor=_BLANC,
        leading=14, spaceAfter=0, alignment=TA_LEFT)
    add('GLabel',
        fontName='Helvetica-Bold', fontSize=8, textColor=_CHAMP_DARK,
        leading=11, spaceAfter=1)
    add('GBody',
        fontName='Helvetica', fontSize=9, textColor=_GRIS_TEXTE,
        leading=13, spaceAfter=3, alignment=TA_JUSTIFY)
    add('GBodyBold',
        fontName='Helvetica-Bold', fontSize=9, textColor=_NOIR,
        leading=13, spaceAfter=3)
    add('GSmall',
        fontName='Helvetica', fontSize=7.5, textColor=_GRIS_TEXTE,
        leading=11, spaceAfter=2)
    add('GFooter',
        fontName='Helvetica', fontSize=7, textColor=_GRIS_MID,
        leading=10, alignment=TA_CENTER)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Composants
# ─────────────────────────────────────────────────────────────────────────────

_PW = 180 * mm if _HAS_REPORTLAB else 510  # largeur utilisable (pts)


def _header(title, sub, source, date_str, st):
    left  = Paragraph(_safe(title, 'Analyse Gabriel'), st['GTitle'])
    right_txt = f'{_safe(source)}<br/><font size="7">{_safe(date_str)}</font><br/>{_safe(sub)}'
    right = Paragraph(right_txt, st['GSubMeta'])
    t = Table([[left, right]], colWidths=[120*mm, 60*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), _NOIR),
        ('TOPPADDING',   (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 10),
        ('LEFTPADDING',  (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def _section_bar(text, st):
    t = Table([[Paragraph(text.upper(), st['GSection'])]], colWidths=[_PW])
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), _CHAMP_DARK),
        ('TOPPADDING',   (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
        ('LEFTPADDING',  (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    return t


def _kv_table(pairs, st):
    rows = []
    for label, value in pairs:
        if value:
            rows.append([
                Paragraph(_safe(label), st['GLabel']),
                Paragraph(_safe(value), st['GBody']),
            ])
    if not rows:
        return None
    t = Table(rows, colWidths=[52*mm, 128*mm])
    t.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',   (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
        ('LEFTPADDING',  (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS',(0, 0), (-1, -1), [_GRIS_PALE, _BLANC]),
        ('LINEBELOW',    (0, 0), (-1, -1), 0.3, _GRIS_MID),
    ]))
    return t


def _two_col(label_l, items_l, label_r, items_r, st):
    def col(label, items):
        parts = [Paragraph(_safe(label), st['GLabel'])]
        for it in (_as_list(items))[:6]:
            parts.append(Paragraph(f'• {_safe(it)}', st['GBody']))
        return parts

    left, right = col(label_l, items_l), col(label_r, items_r)
    mx = max(len(left), len(right))
    empty = Paragraph('', st['GBody'])
    while len(left)  < mx: left.append(empty)
    while len(right) < mx: right.append(empty)

    t = Table([[l, r] for l, r in zip(left, right)], colWidths=[88*mm, 88*mm])
    t.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',   (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 1),
        ('LEFTPADDING',  (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _kpi_row(kpis, st):
    pairs = [(str(k), str(v)) for k, v in list(kpis.items())[:4] if v]
    if not pairs:
        return None
    cells = [
        Paragraph(
            f'<b><font size="14" color="#0D0D10">{v}</font></b><br/>'
            f'<font size="7" color="#B89650">{k}</font>',
            st['GBody']
        )
        for k, v in pairs
    ]
    w = _PW / len(cells)
    t = Table([cells], colWidths=[w] * len(cells))
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), _GRIS_PALE),
        ('BOX',          (0, 0), (-1, -1), 0.5, _GRIS_MID),
        ('INNERGRID',    (0, 0), (-1, -1), 0.3, _GRIS_MID),
        ('TOPPADDING',   (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 8),
        ('ALIGN',        (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def _footer(st):
    now = datetime.datetime.now().strftime('%d/%m/%Y %H:%M')
    return Paragraph(f'Gabriel IA  ·  {now}  ·  Document confidentiel', st['GFooter'])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe(v, default=''):
    if v is None:
        return default
    if isinstance(v, list):
        return '  ·  '.join(str(x) for x in v if x) or default
    return str(v).strip() or default


def _as_list(v):
    if isinstance(v, list):
        return [x for x in v if x]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: generate_analysis_pdf
# ─────────────────────────────────────────────────────────────────────────────

def generate_analysis_pdf(entry, include_strategy=True):
    """Génère un PDF d'analyse complet. Retourne des bytes PDF."""
    if not _HAS_REPORTLAB:
        raise ImportError('reportlab non installé  →  pip install reportlab')

    st    = _styles()
    buf   = io.BytesIO()
    doc   = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm,  bottomMargin=15*mm,
        title='Rapport Gabriel',
    )
    story = []

    # ── Sources ──────────────────────────────────────────────────────────────
    full        = entry.get('full_result') or {}
    source      = entry.get('source') or entry.get('title') or ''
    date_str    = (entry.get('date') or entry.get('created_at') or '')[:16]
    nb_coms     = entry.get('nb_commentaires') or full.get('nb_commentaires') or ''
    kpis        = entry.get('kpis') or full.get('kpis') or {}
    psycho      = full.get('psychologie_audience') or full.get('psychologie') or {}
    aspirations = full.get('aspirations_profondes') or {}
    personas    = full.get('personas') or []
    synthese    = full.get('synthese') or {}
    emotions    = full.get('emotions') or {}
    strat_r     = entry.get('strategie_result') or {}
    title       = entry.get('video_title') or full.get('video_title') or source or 'Analyse'
    subtitle    = f'{nb_coms} commentaires analysés' if nb_coms else 'Analyse de commentaires'

    # En-tête
    story.append(_header(title, subtitle, source, date_str, st))
    story.append(Spacer(1, 5*mm))

    # KPIs
    if kpis and isinstance(kpis, dict):
        t = _kpi_row(kpis, st)
        if t:
            story.append(t)
            story.append(Spacer(1, 4*mm))

    # Émotions
    if emotions:
        story.append(KeepTogether([_section_bar('Émotions dominantes', st), Spacer(1, 3*mm)]))
        dom = emotions.get('emotion_dominante') or emotions.get('dominante')
        if dom:
            story.append(Paragraph(f'Émotion principale : <b>{_safe(dom)}</b>', st['GBodyBold']))
        dist = emotions.get('distribution') or emotions.get('repartition') or {}
        if isinstance(dist, dict) and dist:
            rows = [
                [Paragraph(k, st['GLabel']), Paragraph(_safe(v), st['GBody'])]
                for k, v in list(dist.items())[:8]
            ]
            t = Table(rows, colWidths=[90*mm, 90*mm])
            t.setStyle(TableStyle([
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [_GRIS_PALE, _BLANC]),
                ('LINEBELOW',      (0, 0), (-1, -1), 0.3, _GRIS_MID),
                ('TOPPADDING',     (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING',  (0, 0), (-1, -1), 2),
                ('LEFTPADDING',    (0, 0), (-1, -1), 4),
            ]))
            story.append(t)
        story.append(Spacer(1, 4*mm))

    # Psychologie d'audience
    if psycho:
        story.append(KeepTogether([_section_bar("Psychologie d'audience", st), Spacer(1, 3*mm)]))
        motivations  = psycho.get('motivations_profondes') or psycho.get('motivations')
        frustrations = psycho.get('frustrations_cles') or psycho.get('frustrations')
        desirs       = psycho.get('desirs_caches') or psycho.get('desirs')
        peurs        = psycho.get('peurs') or psycho.get('fears')
        if motivations or frustrations:
            story.append(_two_col('Motivations profondes', motivations, 'Frustrations clés', frustrations, st))
        if desirs or peurs:
            story.append(_two_col('Désirs cachés', desirs, 'Peurs', peurs, st))
        story.append(Spacer(1, 4*mm))

    # Aspirations
    if aspirations:
        story.append(KeepTogether([_section_bar('Aspirations profondes', st), Spacer(1, 3*mm)]))
        blk = _kv_table([
            ("Ce qu'ils veulent devenir", aspirations.get('ce_qu_ils_veulent_devenir')),
            ('Transformation visée',      aspirations.get('transformation_visee')),
            ('Horizon désiré',            aspirations.get('horizon_desire')),
            ('Récit intérieur',           aspirations.get('recit_interieur')),
        ], st)
        if blk:
            story.append(blk)
        story.append(Spacer(1, 4*mm))

    # Personas
    if personas:
        story.append(_section_bar('Personas', st))
        story.append(Spacer(1, 3*mm))
        for p in personas[:3]:
            if not isinstance(p, dict):
                continue
            nom       = p.get('nom', 'Persona')
            archetype = p.get('archetype_jungien') or p.get('archetype', '')
            age       = p.get('age', '')
            prof      = p.get('profession', '')
            emo       = p.get('emotion_dominante', '')
            vision    = p.get('vision_du_monde', '')
            frus      = _as_list(p.get('frustrations') or p.get('frustrations_cles'))
            story.append(KeepTogether([
                Paragraph(f'<b>{nom}</b>  ·  {archetype}  ·  {age}  ·  {prof}', st['GBodyBold']),
                Paragraph(f'Émotion : {emo}', st['GSmall']),
                Paragraph(_safe(vision), st['GBody']),
                *[Paragraph(f'• {_safe(f)}', st['GBody']) for f in frus[:3]],
                Spacer(1, 3*mm),
            ]))

    # Synthèse
    if synthese:
        story.append(KeepTogether([_section_bar('Brief stratégique', st), Spacer(1, 3*mm)]))
        blk = _kv_table([
            ('Synthèse',             synthese.get('synthese') or synthese.get('resume')),
            ('Insight clé',          synthese.get('insight_cle') or synthese.get('insight')),
            ('Action prioritaire',   synthese.get('action_prioritaire') or synthese.get('action')),
            ('Potentiel identifié',  synthese.get('potentiel_identifie')),
        ], st)
        if blk:
            story.append(blk)
        story.append(Spacer(1, 4*mm))

    # Stratégie (si disponible)
    if include_strategy and strat_r:
        story.extend(_strat_elements(strat_r, st))

    # Footer
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=_GRIS_MID))
    story.append(Spacer(1, 2*mm))
    story.append(_footer(st))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: generate_strategy_pdf
# ─────────────────────────────────────────────────────────────────────────────

def generate_strategy_pdf(strategy_data, analysis_entry=None):
    """Génère un PDF stratégie seule. Retourne des bytes PDF."""
    if not _HAS_REPORTLAB:
        raise ImportError('reportlab non installé  →  pip install reportlab')

    st    = _styles()
    buf   = io.BytesIO()
    entry = analysis_entry or {}
    source   = entry.get('source') or entry.get('title') or ''
    date_str = (entry.get('date') or entry.get('created_at') or '')[:16]
    doc   = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm,  bottomMargin=15*mm,
        title='Stratégie Gabriel',
    )
    story = [
        _header('Brief Stratégique Gabriel', 'Stratégie de croissance', source, date_str, st),
        Spacer(1, 5*mm),
    ]
    story.extend(_strat_elements(strategy_data, st))
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=_GRIS_MID))
    story.append(Spacer(1, 2*mm))
    story.append(_footer(st))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# INTERNE : éléments stratégie communs
# ─────────────────────────────────────────────────────────────────────────────

def _strat_elements(strat, st):
    els = [_section_bar('Stratégie Gabriel', st), Spacer(1, 4*mm)]

    # ── Décision centrale ────────────────────────────────────────────────────
    decision = strat.get('decision_centrale') or strat.get('angle_positionnel')
    if decision:
        els.append(Paragraph(f'<b>Décision centrale :</b> {_safe(decision)}', st['GBodyBold']))
        els.append(Spacer(1, 2*mm))

    obj_ref = strat.get('objectif_utilisateur_reformule')
    if obj_ref:
        els.append(Paragraph(f'<i>Objectif : {_safe(obj_ref)}</i>', st['GSmall']))
        els.append(Spacer(1, 3*mm))

    msg = strat.get('message_central')
    if msg:
        els.append(Paragraph('Message central', st['GLabel']))
        els.append(Paragraph(f'« {_safe(msg)} »', st['GBody']))
        els.append(Spacer(1, 3*mm))

    # ── Opportunités de marché ───────────────────────────────────────────────
    opps = strat.get('opportunites_marche') or []
    if opps:
        els.append(KeepTogether([_section_bar('Opportunités de marché', st), Spacer(1, 3*mm)]))
        for opp in opps[:3]:
            if not isinstance(opp, dict):
                continue
            signal = opp.get('signal', '')
            reco   = opp.get('recommandation', '')
            action = opp.get('action_concrete', '')
            mesure = opp.get('mesure_succes', '')
            if signal:
                els.append(Paragraph(f'<b>Signal :</b> {_safe(signal)}', st['GBodyBold']))
            if reco:
                els.append(Paragraph(f'→ {_safe(reco)}', st['GBody']))
            if action or mesure:
                row = []
                if action: row.append([Paragraph('Action', st['GLabel']), Paragraph(_safe(action), st['GBody'])])
                if mesure: row.append([Paragraph('Mesure', st['GLabel']), Paragraph(_safe(mesure), st['GBody'])])
                if row:
                    t = Table(row, colWidths=[30*mm, 148*mm])
                    t.setStyle(TableStyle([
                        ('TOPPADDING', (0, 0), (-1, -1), 1),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                        ('LEFTPADDING', (0, 0), (-1, -1), 3),
                        ('BACKGROUND', (0, 0), (-1, -1), _GRIS_PALE),
                        ('LINEBELOW', (0, 0), (-1, -1), 0.3, _GRIS_MID),
                    ]))
                    els.append(t)
            els.append(Spacer(1, 3*mm))

    def _bullet_section(label, items_raw, limit=6, key_fn=None):
        items = _as_list(items_raw)
        if not items:
            return []
        out = [Paragraph(label, st['GLabel'])]
        for item in items[:limit]:
            if isinstance(item, str):
                txt = item
            elif isinstance(item, dict):
                txt = key_fn(item) if key_fn else (
                    item.get('action') or item.get('titre') or item.get('risque') or str(item))
            else:
                txt = str(item)
            out.append(Paragraph(f'• {_safe(txt)}', st['GBody']))
        out.append(Spacer(1, 2*mm))
        return out

    # ── Recommandations ──────────────────────────────────────────────────────
    def _reco_text(r):
        action = r.get('action', '')
        impact = r.get('impact', '')
        delai  = r.get('delai', '')
        parts  = [action]
        if impact: parts.append(f'Impact : {impact}')
        if delai:  parts.append(f'Délai : {delai}')
        return '  ·  '.join(p for p in parts if p)

    els.extend(_bullet_section(
        'Recommandations prioritaires',
        strat.get('recommandations_prioritaires'),
        key_fn=_reco_text,
    ))

    # ── Offre recommandée ────────────────────────────────────────────────────
    offre = strat.get('offre_recommandee')
    if offre and isinstance(offre, dict):
        els.append(KeepTogether([_section_bar('Offre recommandée', st), Spacer(1, 3*mm)]))
        nom    = offre.get('nom', '')
        cible  = offre.get('cible_precise', '')
        if nom:
            els.append(Paragraph(f'<b>{_safe(nom)}</b>', st['GBodyBold']))
        if cible:
            els.append(Paragraph(f'Cible : {_safe(cible)}', st['GSmall']))
        pairs = [
            ('Problème traité',   offre.get('probleme_traite')),
            ('Promesse',          offre.get('promesse')),
            ('Résultat attendu',  offre.get('resultat_attendu')),
            ('Format',            offre.get('format')),
            ('Prix recommandé',   offre.get('prix_recommande')),
            ('Justification prix',offre.get('justification_prix')),
            ('Message de vente',  offre.get('message_de_vente')),
        ]
        t = _kv_table([(l, v) for l, v in pairs if v], st)
        if t: els.append(t)
        livr = _as_list(offre.get('livrables'))
        if livr:
            els.append(Paragraph('Livrables', st['GLabel']))
            for l in livr[:5]: els.append(Paragraph(f'• {_safe(l)}', st['GBody']))
        canaux = _as_list(offre.get('canaux_acquisition'))
        if canaux:
            els.append(Paragraph(f"Canaux : {', '.join(_safe(c) for c in canaux)}", st['GSmall']))
        objecs = _as_list(offre.get('objections_a_traiter'))
        if objecs:
            els.append(Paragraph('Objections à traiter', st['GLabel']))
            for o in objecs[:3]: els.append(Paragraph(f'⚠ {_safe(o)}', st['GBody']))
        els.append(Spacer(1, 3*mm))

    # ── Pricing ──────────────────────────────────────────────────────────────
    pricing = strat.get('pricing_logic')
    if pricing and isinstance(pricing, dict):
        els.append(KeepTogether([_section_bar('Logique de prix', st), Spacer(1, 3*mm)]))
        fourchette = pricing.get('fourchette')
        position   = pricing.get('positionnement')
        if fourchette:
            els.append(Paragraph(f'<b>Fourchette recommandée : {_safe(fourchette)}</b>'
                                  + (f'  ·  {_safe(position)}' if position else ''), st['GBodyBold']))
        just = pricing.get('justification')
        if just:
            els.append(Paragraph(_safe(just), st['GBody']))
        els.append(Spacer(1, 3*mm))

    # ── Plan 90 jours ────────────────────────────────────────────────────────
    plan = strat.get('plan_90_jours')
    if plan and isinstance(plan, dict):
        els.append(KeepTogether([_section_bar('Plan d\'action 90 jours', st), Spacer(1, 3*mm)]))
        for phase_key in ['phase_1', 'phase_2', 'phase_3']:
            ph = plan.get(phase_key)
            if not ph or not isinstance(ph, dict):
                continue
            titre  = ph.get('titre', phase_key)
            period = ph.get('periode', '')
            els.append(Paragraph(f'<b>{_safe(titre)}</b>  ·  {_safe(period)}', st['GBodyBold']))
            for sub_key, label in [('objectifs','Objectifs'), ('taches','Tâches'), ('livrables','Livrables')]:
                items = _as_list(ph.get(sub_key))
                if items:
                    els.append(Paragraph(label, st['GLabel']))
                    for it in items[:4]: els.append(Paragraph(f'— {_safe(it)}', st['GBody']))
            kpis = _as_list(ph.get('kpis'))
            if kpis:
                els.append(Paragraph(f"KPIs : {', '.join(_safe(k) for k in kpis[:3])}", st['GSmall']))
            decs = _as_list(ph.get('decisions_cles'))
            if decs:
                els.append(Paragraph(f"Décision clé : {_safe(decs[0])}", st['GSmall']))
            els.append(Spacer(1, 3*mm))

    # ── Risques ──────────────────────────────────────────────────────────────
    def _risque_text(r): return f"{r.get('risque','')}  →  {r.get('mitigation','')}"
    els.extend(_bullet_section('Risques identifiés', strat.get('risques'), limit=3, key_fn=_risque_text))

    # ── Indicateurs ──────────────────────────────────────────────────────────
    els.extend(_bullet_section('Indicateurs de succès',
                               strat.get('indicateurs_succes') or strat.get('kpis')))

    return els
