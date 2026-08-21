"""Contrats purs de la Cross Analyse (sans LLM, réseau ni base de données)."""

import copy

import pytest

from core.cross_analysis import (
    CrossAnalysisValidationError,
    attach_source_metadata,
    build_cross_analysis,
    build_source_analysis,
    clean_and_deduplicate_source_comments,
    normalize_cross_sources,
    with_comment_provenance,
)


def _sources():
    return normalize_cross_sources([
        {'platform': 'youtube', 'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'label': 'Audience A'},
        {'platform': 'youtube', 'url': 'https://youtu.be/9bZkp7q19f0', 'label': 'Audience B'},
    ])


def test_normalize_cross_sources_keeps_two_distinct_youtube_sources():
    sources = _sources()

    assert len(sources) == 2
    assert sources[0]['platform'] == 'youtube'
    assert sources[0]['video_id'] == 'dQw4w9WgXcQ'
    assert sources[0]['canonical_url'] == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    assert sources[0]['source_id'].startswith('src_')
    assert sources[0]['source_id'] != sources[1]['source_id']


def test_normalize_cross_sources_rejects_duplicate_videos():
    with pytest.raises(CrossAnalysisValidationError, match='même vidéo'):
        normalize_cross_sources([
            {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
            {'url': 'https://youtu.be/dQw4w9WgXcQ'},
        ])


def test_cross_analysis_requires_multiple_sources():
    with pytest.raises(CrossAnalysisValidationError, match='entre 2 et 5'):
        normalize_cross_sources([{'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}])


def test_attach_source_metadata_carries_through_view_like_comment_counts_and_duration():
    """Avant ce correctif, vues/likes/nb commentaires/durée étaient collectés
    par le scraper mais jamais transmis jusqu'aux métadonnées de la source
    Cross — silencieusement perdus entre la collecte et le résultat."""
    source = _sources()[0]

    resolved = attach_source_metadata(source, {
        'title': 'Titre', 'view_count': 12345, 'like_count': 678,
        'comment_count': 90, 'duration': 'PT4M13S',
    })

    assert resolved['metadata']['view_count'] == 12345
    assert resolved['metadata']['like_count'] == 678
    assert resolved['metadata']['comment_count'] == 90
    assert resolved['metadata']['duration'] == 'PT4M13S'


def test_attach_source_metadata_preserves_none_when_creator_hides_the_like_count():
    """Le scraper renvoie explicitement like_count=None (pas une absence de
    clé) quand le créateur masque le compteur — la distinction avec 0 like
    réel doit survivre jusqu'aux métadonnées de la source Cross."""
    source = _sources()[0]

    resolved = attach_source_metadata(source, {'title': 'Titre', 'view_count': 100, 'like_count': None})

    assert resolved['metadata']['like_count'] is None
    assert resolved['metadata']['view_count'] == 100


def test_attach_source_metadata_omits_like_count_entirely_when_not_provided_at_all():
    source = _sources()[0]

    resolved = attach_source_metadata(source, {'title': 'Titre', 'view_count': 100})

    assert 'like_count' not in resolved['metadata']


def test_comment_provenance_is_attached_without_losing_legacy_fields():
    source = _sources()[0]
    comments = [{
        'id': 'youtube-comment-42',
        'text': 'Le prix semble juste et le service est clair.',
        'likes': 12,
        'author': 'Marie',
        'published_at': '2026-08-01T12:00:00Z',
    }]

    rows = with_comment_provenance(comments, source)

    assert rows[0]['text'] == comments[0]['text']
    assert rows[0]['likes'] == 12
    assert rows[0]['source_id'] == source['source_id']
    assert rows[0]['video_id'] == source['video_id']
    assert rows[0]['external_comment_id'] == 'youtube-comment-42'
    assert rows[0]['comment_id'] == f"{source['source_id']}:youtube-comment-42"
    assert rows[0]['metadata']['published_at'] == '2026-08-01T12:00:00Z'


def test_source_analysis_adapts_existing_result_without_mutating_it():
    source = _sources()[0]
    comments = with_comment_provenance([{'text': 'Je veux gagner du temps.', 'likes': 3}], source)
    legacy_result = {
        'analysis_id': 'analysis-a',
        'meta': {'total_commentaires': 1, 'commentaires_analyses': 1},
        'dashboard': {
            'confidence_score': 75,
            'noise_ratio': 4,
            'emotion_distribution': {'Espoir': 65},
            'dominant_emotion': 'Espoir',
            'sujets_recurrents': [{'theme': 'Gain de temps', 'score': 8}],
        },
        'personas': [{'nom': 'Pragmatique'}],
        'interpretation': {'summary': 'Une audience sensible à l’efficacité.'},
    }
    before = copy.deepcopy(legacy_result)

    source_analysis = build_source_analysis(source, legacy_result, comments)

    assert legacy_result == before
    assert source_analysis['analysis_id'] == 'analysis-a'
    assert source_analysis['comment_stats']['total_comments'] == 1
    assert source_analysis['emotions'][0]['label'] == 'Espoir'
    assert source_analysis['themes'][0]['label'] == 'Gain de temps'
    assert source_analysis['evidence'][0]['source_id'] == source['source_id']


def test_source_analysis_extracts_emotion_repartition_from_current_rich_result_shape():
    """Le résultat individuel actuel expose ``emotions`` comme un objet riche
    (repartition, dominante, intensite, commentaires_revelateurs, ...) — pas
    une distribution plate. Avant ce correctif, _signal_values traitait les
    noms de ces champs eux-mêmes comme des émotions détectées."""
    source = _sources()[0]
    comments = with_comment_provenance([{'text': 'Je suis admiratif.', 'likes': 2}], source)
    current_result = {
        'analysis_id': 'analysis-a',
        'meta': {'total_commentaires': 1, 'commentaires_analyses': 1},
        'dashboard': {'confidence_score': 80, 'noise_ratio': 3},
        'emotions': {
            'repartition': [
                {'emotion': 'Admiration', 'pourcentage': 38, 'couleur': '#F59E0B'},
                {'emotion': 'Espoir', 'pourcentage': 22, 'couleur': '#10B981'},
            ],
            'dominante': 'Admiration',
            'intensite': 'Chaleur collective sans engagement profond',
            'commentaires_revelateurs': ['citation 1'],
            'signaux_authenticite': 'phrase',
            'signaux_artificialite': 'phrase',
            'besoins_sous_jacents': 'phrase',
            'espoir_decu': 'phrase',
            'aspiration_nourrie': 'phrase',
        },
        'personas': [],
        'interpretation': {},
    }

    source_analysis = build_source_analysis(source, current_result, comments)

    labels = {item['label'] for item in source_analysis['emotions']}
    assert labels == {'Admiration', 'Espoir'}
    admiration = next(item for item in source_analysis['emotions'] if item['label'] == 'Admiration')
    assert admiration['weight'] == 38.0
    # Les noms de champs techniques ne doivent jamais apparaître comme émotions.
    assert 'dominante' not in labels
    assert 'repartition' not in labels
    assert 'intensite' not in labels
    assert 'commentaires_revelateurs' not in labels


def test_cross_comparison_is_source_balanced_not_comment_volume_balanced():
    source_a, source_b = _sources()
    source_analyses = [
        {
            'source_id': source_a['source_id'],
            'comment_stats': {'total_comments': 150, 'confidence_score': 90},
            # Le même signal est volontairement répété : il ne doit compter
            # qu'une fois pour cette audience.
            'emotions': [{'label': 'Espoir', 'weight': 100}] * 150,
        },
        {
            'source_id': source_b['source_id'],
            'comment_stats': {'total_comments': 3, 'confidence_score': 70},
            'emotions': [{'label': 'Espoir', 'weight': 2}],
        },
    ]

    cross = build_cross_analysis(source_analyses)
    hope = cross['shared_emotions'][0]

    assert hope['label'] == 'Espoir'
    assert hope['sources_count'] == 2
    assert hope['source_coverage'] == 1.0
    assert len(hope['sources']) == 2
    assert cross['confidence']['method'] == 'source_balanced_deterministic'
    assert cross['cross_summary']['status'] == 'measured_pending_interpretation'


# ─── Cas B du brief : audiences opposées ──────────────────────────────────
# Aucune fixture permanente n'existait pour _detect_stance_oppositions avant
# ce correctif — seulement une vérification manuelle ponctuelle en audit.

def test_cross_analysis_detects_a_stance_opposition_between_sources():
    source_a, source_b = _sources()
    source_analyses = [
        {
            'source_id': source_a['source_id'],
            'comment_stats': {'total_comments': 40, 'confidence_score': 80},
            'dashboard': {'stance_distribution': {'favorable': 70, 'oppose': 10, 'neutre': 20}},
        },
        {
            'source_id': source_b['source_id'],
            'comment_stats': {'total_comments': 35, 'confidence_score': 75},
            'dashboard': {'stance_distribution': {'favorable': 15, 'oppose': 65, 'neutre': 20}},
        },
    ]

    cross = build_cross_analysis(source_analyses)

    assert len(cross['oppositions']) == 1
    opposition = cross['oppositions'][0]
    assert opposition['type'] == 'stance_opposition'
    positions = {row['source_id']: row['position'] for row in opposition['source_positions']}
    assert positions[source_a['source_id']] == 'favorable'
    assert positions[source_b['source_id']] == 'oppose'
    # La détection reste une mesure, pas une interprétation psychologique.
    assert opposition['interpretation_status'] == 'pending_llm'


def test_cross_analysis_reports_no_opposition_when_sources_broadly_agree():
    source_a, source_b = _sources()
    source_analyses = [
        {
            'source_id': source_a['source_id'],
            'comment_stats': {'total_comments': 40, 'confidence_score': 80},
            'dashboard': {'stance_distribution': {'favorable': 70, 'oppose': 10}},
        },
        {
            'source_id': source_b['source_id'],
            'comment_stats': {'total_comments': 35, 'confidence_score': 75},
            'dashboard': {'stance_distribution': {'favorable': 60, 'oppose': 15}},
        },
    ]

    cross = build_cross_analysis(source_analyses)

    assert cross['oppositions'] == []


# ─── Cas E du brief : signal rare mais fort ────────────────────────────────
# "Vérifier qu'il n'est pas automatiquement perdu" — un signal qui n'apparaît
# que dans une seule source doit rester visible en source_specific_signals,
# pas disparaître silencieusement faute de convergence.

def test_cross_analysis_keeps_a_rare_but_intense_source_specific_signal():
    source_a, source_b = _sources()
    source_analyses = [
        {
            'source_id': source_a['source_id'],
            'comment_stats': {'total_comments': 40, 'confidence_score': 80},
            'fears': [{'label': 'Peur de perdre le contrôle financier', 'score': 95}],
        },
        {
            'source_id': source_b['source_id'],
            'comment_stats': {'total_comments': 35, 'confidence_score': 75},
            'fears': [],
        },
    ]

    cross = build_cross_analysis(source_analyses)

    specific = {item['label']: item for item in cross['source_specific_signals']}
    assert 'Peur de perdre le contrôle financier' in specific
    signal = specific['Peur de perdre le contrôle financier']
    assert signal['category'] == 'fears'
    assert signal['sources_count'] == 1
    # Traçable jusqu'à sa preuve, pas juste un libellé flottant.
    assert signal['insight_id'] in cross['evidence_index']


# ─── Cas D du brief : bruit (doublons, texte vide, spam) ──────────────────
# La préparation du corpus doit résister au bruit sans planter et sans
# perdre les commentaires uniques et exploitables.

def test_clean_and_deduplicate_resists_spam_empty_and_duplicate_comments():
    source = _sources()[0]
    comments = [
        {'text': 'Super vidéo, merci !', 'likes': 5},
        {'text': 'Super vidéo, merci !', 'likes': 2},  # doublon exact
        {'text': '   '},                                # vide après trim
        {'text': ''},                                    # vide
        {'text': '🔥🔥🔥'},                                 # emoji seul — pas vide, conservé
        {'text': 'PREMIER ! ! !', 'likes': 0},            # bruit, mais du vrai texte
    ]

    prepared = clean_and_deduplicate_source_comments(comments, source)

    assert prepared['dataset']['comments_collected'] == 4  # 2 textes vides exclus dès la provenance
    assert prepared['dataset']['duplicates_removed'] == 1
    assert prepared['dataset']['comments_retained'] == 3
    retained_texts = {row['text'] for row in prepared['retained_comments']}
    assert retained_texts == {'Super vidéo, merci !', '🔥🔥🔥', 'PREMIER ! ! !'}
