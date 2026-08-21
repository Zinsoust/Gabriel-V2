"""Tests sans réseau du pipeline Cross et de sa persistance locale."""

from core.cross_analysis import normalize_cross_options, normalize_cross_sources
from core.cross_pipeline import CrossAnalysisPipeline
import api.db as db


class _FakeYouTubeProvider:
    def collect(self, source, *, max_comments, include_replies=False):
        assert include_replies is False
        video_id = source['video_id']
        return [
            {'id': f'{video_id}-1', 'text': 'Je cherche une solution claire.', 'likes': 8},
            {'id': f'{video_id}-2', 'text': 'Je cherche une solution claire.', 'likes': 2},
            {'id': f'{video_id}-3', 'text': 'Le prix reste une inquiétude.', 'likes': 4},
        ][:max_comments], {'title': f'Vidéo {video_id}', 'channel': 'Gabriel'}


def _legacy_result(source_id):
    return {
        'analysis_id': f'analysis-{source_id[-4:]}',
        'meta': {'total_commentaires': 2, 'commentaires_analyses': 2},
        'dashboard': {
            'confidence_score': 72,
            'noise_ratio': 3,
            'emotion_distribution': {'Espoir': 64, 'Frustration': 24},
            'sujets_recurrents': [{'theme': 'Clarté de l’offre', 'score': 8}],
        },
        'psychologie': {
            'peurs_implicites': ['Faire le mauvais choix'],
            'motivations_profondes': ['Retrouver de la simplicité'],
        },
        'aspirations': {'ambitions': ['Avancer avec confiance']},
        'personas': [{'nom': 'Pragmatique'}],
        'interpretation': {'synthese_psychologique': 'Lecture source.'},
    }


def test_cross_pipeline_keeps_source_corpora_separate_and_compares_results():
    sources = normalize_cross_sources([
        {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
        {'url': 'https://youtu.be/9bZkp7q19f0'},
    ])
    statuses = []
    pipeline = CrossAnalysisPipeline(youtube_provider=_FakeYouTubeProvider(), cache_ttl_seconds=120)

    result = pipeline.run(
        sources,
        normalize_cross_options({'max_comments_per_source': 20}),
        lambda source, comments, cached_result=None: _legacy_result(source['source_id']),
        source_status_cb=lambda source, status, payload=None: statuses.append((source, status, payload or {})),
    )

    assert result['status'] == 'completed'
    assert len(result['source_analyses']) == 2
    assert result['cross_summary']['comments_count'] == 4
    assert result['shared_emotions'][0]['label'] == 'Espoir'
    assert result['shared_emotions'][0]['sources_count'] == 2
    collected = [payload for _, status, payload in statuses if status == 'collected']
    assert len(collected) == 2
    assert all(len(payload['raw_comments']) == 3 for payload in collected)
    assert all(item['source_id'] for payload in collected for item in payload['raw_comments'])
    evidence = next(iter(result['evidence_index'].values()))
    assert evidence['representative_source_evidence']
    assert evidence['representative_source_evidence'][0]['comments'][0]['comment_id']


def test_cross_pipeline_offers_a_cached_result_but_always_lets_the_caller_decide():
    """Le pipeline ne doit jamais court-circuiter ``analyze_source`` : lui seul
    connaît l'identité et la persistance propres à la Cross Analyse en cours
    (voir le docstring du module). Un précédent comportement renvoyait le
    résultat en cache tel quel, ce qui faisait hériter une nouvelle Cross de
    l'``analysis_id`` d'une session antérieure."""
    pipeline = CrossAnalysisPipeline(youtube_provider=_FakeYouTubeProvider(), cache_ttl_seconds=120)
    calls = []
    llm_calls = []

    def analyze(source, _comments, cached_result=None):
        calls.append(source['source_id'])
        # Comme _analyze_one_source en production : ne relancer le "LLM" que
        # si aucun résultat récent n'a été proposé, mais toujours attribuer
        # une identité fraîche, propre à CETTE Cross Analyse.
        if cached_result is not None:
            result = dict(cached_result)
        else:
            llm_calls.append(source['source_id'])
            result = _legacy_result(source['source_id'])
        result = dict(result)
        result['analysis_id'] = f"fresh-{source['source_id']}"
        result['reused_from_cache'] = cached_result is not None
        return result

    options = {**normalize_cross_options({}), '_cache_scope': 'user-a'}
    first_sources = normalize_cross_sources([
        {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
        {'url': 'https://youtu.be/9bZkp7q19f0'},
    ])
    first = pipeline.run(first_sources, options, analyze)
    assert len(calls) == 2
    assert len(llm_calls) == 2
    assert not any(source['analysis_cache_hit'] for source in first['source_analyses'])

    # Nouveaux source_id, mêmes vidéos, même utilisateur : le pipeline appelle
    # quand même ``analyze_source`` (pas de court-circuit), mais ne relance
    # aucun "LLM" — le résultat en cache lui a été transmis.
    second_sources = normalize_cross_sources([
        {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
        {'url': 'https://youtu.be/9bZkp7q19f0'},
    ])
    second = pipeline.run(second_sources, options, analyze)
    assert len(calls) == 4
    assert len(llm_calls) == 2
    assert all(source['analysis_cache_hit'] for source in second['source_analyses'])
    # Chaque session obtient sa PROPRE identité, jamais celle de la précédente
    # (les source_id diffèrent d'une session à l'autre : on compare par vidéo).
    first_ids = {item['metadata']['video_id']: item['analysis_id'] for item in first['source_analyses']}
    second_ids = {item['metadata']['video_id']: item['analysis_id'] for item in second['source_analyses']}
    assert set(first_ids) == set(second_ids)
    for video_id, second_analysis_id in second_ids.items():
        assert second_analysis_id != first_ids[video_id]

    # refresh=true force volontairement une analyse fraîche : aucun résultat
    # en cache n'est proposé, donc "llm_calls" grandit à nouveau.
    pipeline.run(second_sources, {**options, 'refresh': True}, analyze)
    assert len(llm_calls) == 4


class _FakeSupabaseTable:
    """Simule .table(name).insert/upsert/delete().eq()...execute() de postgrest-py,
    assez fidèlement pour tester le nettoyage de compensation sans réseau."""

    def __init__(self, parent, name):
        self._parent = parent
        self._name = name
        self._op = None
        self._payload = None
        self._filters = {}

    def insert(self, row):
        self._op, self._payload = 'insert', dict(row)
        return self

    def upsert(self, row, on_conflict=None):
        self._op, self._payload = 'upsert', dict(row)
        return self

    def delete(self):
        self._op = 'delete'
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def execute(self):
        key = f'{self._op}:{self._name}'
        self._parent.call_counts[key] = self._parent.call_counts.get(key, 0) + 1
        if self._parent.call_counts[key] in self._parent.fail_on_call.get(key, set()):
            raise RuntimeError(f'panne simulée : {key} (appel n°{self._parent.call_counts[key]})')
        rows = self._parent.store.setdefault(self._name, [])
        if self._op in ('insert', 'upsert'):
            rows.append(self._payload)
        elif self._op == 'delete':
            self._parent.store[self._name] = [
                row for row in rows if not all(row.get(k) == v for k, v in self._filters.items())
            ]
        return self


class _FakeSupabase:
    """``fail_on_call`` : {"upsert:table_name": {2}} → la 2e exécution de cette
    opération sur cette table échoue ; les autres réussissent normalement."""

    def __init__(self, fail_on_call=None):
        self.store = {}
        self.call_counts = {}
        self.fail_on_call = fail_on_call or {}

    def table(self, name):
        return _FakeSupabaseTable(self, name)


def test_create_cross_analysis_cleans_up_partial_writes_on_mid_write_failure(tmp_path, monkeypatch):
    """Deux sources, la deuxième échoue en cours d'écriture (crash simulé
    après que la première ait déjà été écrite). Sans compensation, la ligne
    maître et le lien de la première source restaient orphelins dans
    Supabase — une Cross visible mais incomplète pour aucune lecture fiable."""
    storage = tmp_path / 'cross_analyses.json'
    monkeypatch.setattr(db, '_CROSS_ANALYSES_FILE', str(storage))
    fake = _FakeSupabase(fail_on_call={f'upsert:{db._T_CROSS_SOURCES}': {2}})
    monkeypatch.setattr(db, '_supabase', fake)

    sources = normalize_cross_sources([
        {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
        {'url': 'https://youtu.be/9bZkp7q19f0'},
    ])
    result = db.create_cross_analysis('cross-partial', 'user-a', sources)

    assert result is False  # retombé sur le JSON local après l'échec Supabase
    # Rien ne doit rester en base pour cette session : ni la ligne maître, ni
    # le lien de la première source écrit avant l'échec de la deuxième.
    assert fake.store.get(db._T_CROSS_ANALYSES, []) == []
    assert fake.store.get(db._T_CROSS_SOURCES, []) == []
    # Le repli JSON local a bien pris le relais (comportement existant conservé).
    assert db._load_json_cross_analyses()[0]['cross_analysis_id'] == 'cross-partial'


def test_cross_json_fallback_write_is_atomic_and_survives_a_crash_mid_write(tmp_path, monkeypatch):
    """Une écriture qui plante en plein milieu (crash, disque plein...) ne
    doit jamais laisser le fichier cible dans un état tronqué — sinon
    _load_json_cross_analyses() perd tout l'historique Cross d'un coup."""
    storage = tmp_path / 'cross_analyses.json'
    monkeypatch.setattr(db, '_CROSS_ANALYSES_FILE', str(storage))

    original_rows = [{'cross_analysis_id': 'cross-original', 'user_id': 'user-a'}]
    db._write_json_cross_analyses(original_rows)
    assert db._load_json_cross_analyses() == original_rows

    def failing_dump(*_args, **_kwargs):
        raise RuntimeError("disque plein (simulé)")

    real_dump = db.json.dump
    db.json.dump = failing_dump
    try:
        try:
            db._write_json_cross_analyses([{'cross_analysis_id': 'cross-new', 'user_id': 'user-b'}])
            assert False, "l'échec simulé aurait dû se propager"
        except RuntimeError:
            pass
    finally:
        db.json.dump = real_dump

    # Le fichier cible n'a jamais été touché : toujours les données d'origine.
    assert db._load_json_cross_analyses() == original_rows
    # Aucun fichier temporaire abandonné dans le dossier de données.
    leftovers = [p for p in tmp_path.iterdir() if p.name != 'cross_analyses.json']
    assert leftovers == []


def test_cross_persistence_fallback_keeps_result_and_primary_comments(tmp_path, monkeypatch):
    storage = tmp_path / 'cross_analyses.json'
    monkeypatch.setattr(db, '_CROSS_ANALYSES_FILE', str(storage))
    monkeypatch.setattr(db, '_supabase', None)
    sources = normalize_cross_sources([
        {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
        {'url': 'https://youtu.be/9bZkp7q19f0'},
    ])
    cross_id = 'cross-local-test'
    assert db.create_cross_analysis(cross_id, 'user-a', sources, options={'refresh': False}) is False
    source = sources[0]
    comments = [{
        'comment_id': f"{source['source_id']}:comment-1",
        'source_id': source['source_id'],
        'video_id': source['video_id'],
        'text': 'Commentaire source.',
    }]
    assert db.save_cross_source_comments('user-a', source, comments, cross_analysis_id=cross_id)
    assert db.update_cross_analysis_source(
        cross_id, 'user-a', source['source_id'], status='completed', analysis_id='analysis-a',
        source_analysis={'source_id': source['source_id'], 'analysis_id': 'analysis-a'},
    )
    assert db.update_cross_analysis(cross_id, 'user-a', status='completed', result_data={
        'evidence_index': {'cross:emotions:hope': {'label': 'Espoir'}},
    })

    restored = db.get_cross_analysis(cross_id, 'user-a')
    restored_source = db.get_cross_analysis_source(cross_id, source['source_id'], 'user-a')
    assert restored['status'] == 'completed'
    assert restored_source['analysis_id'] == 'analysis-a'
    assert db.get_cross_source_comments(cross_id, source['source_id'], 'user-a') == comments
    assert db.get_cross_analysis_evidence(cross_id, 'cross:emotions:hope', 'user-a')['label'] == 'Espoir'
