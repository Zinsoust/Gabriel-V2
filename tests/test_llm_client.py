"""Contrats de la couche LLM unifiée — testés sans aucun appel réseau.

Ces tests garantissent que le découplage fournisseur est réel : on doit pouvoir
substituer un fournisseur factice et vérifier les politiques (paliers de
modèle, réessais, troncature) sans dépendre de Mistral ni d'une clé d'API.
"""

import pytest

from core.llm_client import (
    MODEL_TIERS,
    LLMProvider,
    LLMResponse,
    RetryPolicy,
    complete,
    complete_text,
    model_for_tier,
)


class FakeProvider(LLMProvider):
    """Fournisseur factice : enregistre les appels, rejoue des réponses ou
    des erreurs scriptées."""

    name = "fake"

    def __init__(self, responses=None, errors=None):
        self.calls = []
        self._responses = list(responses or [])
        self._errors = list(errors or [])

    def complete(self, prompt, *, model, max_tokens, temperature=None, timeout_ms=300_000, system=None):
        self.calls.append({
            "prompt": prompt, "model": model, "max_tokens": max_tokens,
            "temperature": temperature, "timeout_ms": timeout_ms, "system": system,
        })
        if self._errors:
            error = self._errors.pop(0)
            if error is not None:
                raise error
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(text="ok", model=model, prompt_tokens=10, completion_tokens=5,
                           finish_reason="stop")


class StatusError(Exception):
    """Reproduit la forme d'erreur du SDK : un ``status_code`` porté par l'exception."""

    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def test_model_tiers_map_to_real_model_names():
    assert model_for_tier("fast") == MODEL_TIERS["fast"]
    assert model_for_tier("deep") == MODEL_TIERS["deep"]


def test_model_tiers_default_to_distinct_models_and_follow_the_environment():
    """Sans configuration, deux modèles distincts ; avec MISTRAL_MODEL_FAST/DEEP,
    on bascule quand l'abonnement retire un modèle (13/09/2026)."""
    from core.llm_client import _tiers_from_env
    assert _tiers_from_env({}) == {"fast": "mistral-small-latest", "deep": "mistral-large-latest"}
    assert _tiers_from_env({"MISTRAL_MODEL_FAST": "ministral-14b-latest"})["fast"] == "ministral-14b-latest"


def test_unknown_tier_fails_loudly_rather_than_silently_defaulting():
    """Un palier inconnu doit lever : retomber silencieusement sur le modèle
    profond ferait payer un tarif « large » pour une tâche triviale, sans trace."""
    with pytest.raises(ValueError, match="Palier de modèle inconnu"):
        model_for_tier("turbo")


def test_provider_is_substitutable_without_touching_call_sites():
    """Le découplage fournisseur doit être réel : injecter un autre fournisseur
    suffit, sans modifier ni les agents ni l'orchestrateur."""
    fake = FakeProvider()
    result = complete("prompt", provider=fake, throttled=False, label="test")
    assert result.text == "ok"
    assert fake.calls[0]["model"] == MODEL_TIERS["deep"]


def test_tier_selects_the_fast_model():
    fake = FakeProvider()
    complete("prompt", tier="fast", provider=fake, throttled=False)
    assert fake.calls[0]["model"] == MODEL_TIERS["fast"]


def test_retries_on_rate_limit_then_succeeds():
    fake = FakeProvider(errors=[StatusError(429), None])
    policy = RetryPolicy(max_attempts=2, base_delay=0.0)
    result = complete("prompt", provider=fake, retry=policy, throttled=False)
    assert result.text == "ok"
    assert len(fake.calls) == 2


def test_does_not_retry_on_a_permanent_error():
    """Un 400 (entrée invalide) ne doit jamais être rejoué : le réessai ne peut
    pas le corriger, il ne fait que retarder l'échec et doubler le coût."""
    fake = FakeProvider(errors=[StatusError(400)])
    policy = RetryPolicy(max_attempts=6, base_delay=0.0)
    with pytest.raises(StatusError):
        complete("prompt", provider=fake, retry=policy, throttled=False)
    assert len(fake.calls) == 1


def test_gives_up_after_max_attempts():
    fake = FakeProvider(errors=[StatusError(429), StatusError(429)])
    policy = RetryPolicy(max_attempts=2, base_delay=0.0)
    with pytest.raises(StatusError):
        complete("prompt", provider=fake, retry=policy, throttled=False)
    assert len(fake.calls) == 2


def test_truncation_is_detected_from_finish_reason():
    """Une réponse coupée par la limite de tokens produit presque toujours un
    JSON incomplet : le signal doit remonter explicitement, pas se deviner."""
    truncated = LLMResponse(text="{...", model="m", finish_reason="length")
    assert truncated.truncated is True
    complete_normally = LLMResponse(text="{}", model="m", finish_reason="stop")
    assert complete_normally.truncated is False


def test_temperature_is_passed_through_and_clamped_by_provider_contract():
    fake = FakeProvider()
    complete("prompt", provider=fake, temperature=0.7, throttled=False)
    assert fake.calls[0]["temperature"] == 0.7


def test_complete_text_returns_the_plain_string():
    fake = FakeProvider()
    assert complete_text("prompt", provider=fake, throttled=False) == "ok"


class TestMessageSysteme:
    """Trois appelants (extraction de réponses, rendu de ton, entretien legacy)
    séparent depuis toujours les instructions de rôle de la demande. Les fondre
    dans un seul prompt affaiblirait la frontière que la couche de sécurité pose
    entre consigne et contenu non fiable."""

    def test_le_message_systeme_est_transmis_au_fournisseur(self):
        fake = FakeProvider()
        complete("demande", provider=fake, throttled=False, system="Tu es un extracteur.")
        assert fake.calls[0]["system"] == "Tu es un extracteur."

    def test_son_absence_reste_le_defaut(self):
        fake = FakeProvider()
        complete("demande", provider=fake, throttled=False)
        assert fake.calls[0]["system"] is None

    def test_il_ne_se_melange_pas_au_prompt_utilisateur(self):
        fake = FakeProvider()
        complete("contenu utilisateur", provider=fake, throttled=False, system="consigne")
        assert fake.calls[0]["prompt"] == "contenu utilisateur"
        assert "consigne" not in fake.calls[0]["prompt"]


class TestPolitiqueSansReessai:
    def test_retry_none_n_essaie_qu_une_seule_fois(self):
        """Certains appels (voix, rendu de ton) préfèrent échouer vite et
        basculer sur une réponse de secours plutôt que faire patienter."""
        from core.llm_client import RETRY_NONE
        fake = FakeProvider(errors=[StatusError(429)])
        with pytest.raises(StatusError):
            complete("demande", provider=fake, retry=RETRY_NONE, throttled=False)
        assert len(fake.calls) == 1


class TestFournisseurOpenAI:
    """Le découplage n'a de valeur que si un second fournisseur existe
    réellement. Ces tests l'exercent sans aucun appel réseau."""

    def _fake_post(self, capture, *, status=200, body=None):
        class _Resp:
            status_code = status
            text = 'erreur'
            def json(self_inner):
                return body or {
                    "choices": [{"message": {"content": " réponse "}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                }
        def _post(url, headers=None, json=None, timeout=None):
            capture.update({"url": url, "headers": headers, "payload": json, "timeout": timeout})
            return _Resp()
        return _post

    def test_appelle_le_bon_endpoint_et_normalise_la_reponse(self, monkeypatch):
        import requests
        from core.llm_client import OpenAIProvider
        monkeypatch.setenv("OPENAI_API_KEY", "clé-de-test")
        capture = {}
        monkeypatch.setattr(requests, "post", self._fake_post(capture))

        r = OpenAIProvider().complete("demande", model=MODEL_TIERS["deep"], max_tokens=100)

        assert capture["url"] == "https://api.openai.com/v1/chat/completions"
        assert r.text == "réponse"          # normalisé, sans espaces parasites
        assert r.prompt_tokens == 11
        assert r.finish_reason == "stop"

    def test_traduit_le_palier_vers_un_modele_openai(self, monkeypatch):
        """Envoyer tel quel un nom de modèle Mistral à OpenAI ferait échouer
        l'appel avec une erreur incompréhensible."""
        import requests
        from core.llm_client import OpenAIProvider
        monkeypatch.setenv("OPENAI_API_KEY", "clé-de-test")
        capture = {}
        monkeypatch.setattr(requests, "post", self._fake_post(capture))

        OpenAIProvider().complete("d", model=MODEL_TIERS["fast"], max_tokens=10)
        assert capture["payload"]["model"] == OpenAIProvider.MODELS["fast"]
        assert "mistral" not in capture["payload"]["model"]

    def test_separe_la_consigne_de_la_demande(self, monkeypatch):
        import requests
        from core.llm_client import OpenAIProvider
        monkeypatch.setenv("OPENAI_API_KEY", "clé-de-test")
        capture = {}
        monkeypatch.setattr(requests, "post", self._fake_post(capture))

        OpenAIProvider().complete("demande", model=MODEL_TIERS["deep"], max_tokens=10, system="consigne")
        roles = [m["role"] for m in capture["payload"]["messages"]]
        assert roles == ["system", "user"]

    def test_une_erreur_http_porte_son_statut_pour_la_politique_de_reessai(self, monkeypatch):
        """Sans statut normalisé, un 429 d'OpenAI ne déclencherait aucun
        réessai alors que le même cas en déclenche chez Mistral."""
        import requests
        from core.llm_client import OpenAIProvider, ProviderHTTPError
        monkeypatch.setenv("OPENAI_API_KEY", "clé-de-test")
        monkeypatch.setattr(requests, "post", self._fake_post({}, status=429))

        with pytest.raises(ProviderHTTPError) as err:
            OpenAIProvider().complete("d", model=MODEL_TIERS["deep"], max_tokens=10)
        assert err.value.status_code == 429

    def test_un_429_openai_declenche_bien_un_reessai(self, monkeypatch):
        """Vérifie la chaîne complète : erreur fournisseur → politique commune."""
        import requests
        from core.llm_client import OpenAIProvider
        monkeypatch.setenv("OPENAI_API_KEY", "clé-de-test")
        appels = {"n": 0}

        class _Resp:
            def __init__(self, code): self.status_code = code; self.text = 'x'
            def json(self): return {"choices": [{"message": {"content": "ok"},
                                                 "finish_reason": "stop"}], "usage": {}}
        def _post(url, headers=None, json=None, timeout=None):
            appels["n"] += 1
            return _Resp(429 if appels["n"] == 1 else 200)
        monkeypatch.setattr(requests, "post", _post)

        r = complete("d", provider=OpenAIProvider(), throttled=False,
                     retry=RetryPolicy(max_attempts=2, base_delay=0.0))
        assert r.text == "ok"
        assert appels["n"] == 2

    def test_cle_absente_donne_un_message_clair(self, monkeypatch):
        from core.llm_client import OpenAIProvider
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY manquante"):
            OpenAIProvider().complete("d", model=MODEL_TIERS["deep"], max_tokens=10)


class TestSelectionDuFournisseur:
    def test_mistral_reste_le_defaut(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        from core.llm_client import _provider_from_env
        assert _provider_from_env().name == "mistral"

    def test_on_bascule_par_variable_d_environnement(self, monkeypatch):
        """Changer de fournisseur ne doit demander aucune modification de code
        dans les agents — c'est tout l'objet du découplage."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        from core.llm_client import _provider_from_env
        assert _provider_from_env().name == "openai"

    def test_un_fournisseur_inconnu_echoue_au_demarrage(self, monkeypatch):
        """Mieux vaut refuser de démarrer que retomber silencieusement sur un
        fournisseur que l'exploitant ne croyait pas utiliser."""
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        from core.llm_client import _provider_from_env
        with pytest.raises(ValueError, match="LLM_PROVIDER inconnu"):
            _provider_from_env()


def test_le_journal_annonce_le_modele_reellement_appele(monkeypatch, capsys):
    """Un fournisseur retraduit le palier vers son propre catalogue. Journaliser
    le modèle demandé ferait croire qu'un modèle Mistral a répondu alors
    qu'OpenAI a servi l'appel — un journal qui ment sur ce qui s'est passé."""
    fake = FakeProvider(responses=[LLMResponse(
        text="ok", model="gpt-4o-mini", prompt_tokens=5, completion_tokens=3, finish_reason="stop")])
    complete("demande", provider=fake, throttled=False, label="preuve")
    sortie = capsys.readouterr().out
    assert "model=gpt-4o-mini" in sortie
    assert MODEL_TIERS["deep"] not in sortie


def test_json_mode_is_forwarded_only_when_requested():
    """Le mode JSON natif protège l'analyse des sorties markdown des petits
    modèles ; un fournisseur qui ne le connaît pas ne doit rien voir changer."""
    captured = []

    class Legacy:
        name = "legacy"
        def complete(self, prompt, *, model, max_tokens, temperature=None, timeout_ms=300_000, system=None):
            captured.append("sans json_mode")
            return LLMResponse(text="{}", model=model)

    class Moderne:
        name = "moderne"
        def complete(self, prompt, *, model, max_tokens, temperature=None, timeout_ms=300_000, system=None, json_mode=False):
            captured.append(json_mode)
            return LLMResponse(text="{}", model=model)

    complete("d", provider=Legacy(), throttled=False, json_mode=True)
    complete("d", provider=Moderne(), throttled=False, json_mode=True)
    assert captured == ["sans json_mode", True]


def test_mistral_provider_requests_a_json_object(monkeypatch):
    import sys
    import types
    sent = {}

    class _Chat:
        def complete(self, **kwargs):
            sent.update(kwargs)
            choice = types.SimpleNamespace(message=types.SimpleNamespace(content='{"ok": 1}'), finish_reason="stop")
            return types.SimpleNamespace(choices=[choice], usage=None)

    class _Mistral:
        def __init__(self, **kwargs):
            self.chat = _Chat()

    monkeypatch.setitem(sys.modules, "mistralai", types.SimpleNamespace(Mistral=_Mistral))
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    from core.llm_client import MistralProvider
    MistralProvider().complete("d", model="m", max_tokens=5, json_mode=True)
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["retries"] is None
    sent.clear()
    MistralProvider().complete("d", model="m", max_tokens=5)
    assert "response_format" not in sent
    assert sent["retries"] is None


def test_mistral_provider_reports_the_model_returned_by_the_api(monkeypatch):
    import sys
    import types

    class _Chat:
        def complete(self, **kwargs):
            choice = types.SimpleNamespace(
                message=types.SimpleNamespace(content='ok'), finish_reason='stop'
            )
            return types.SimpleNamespace(
                choices=[choice], usage=None, model='provider-fallback-model'
            )

    class _Mistral:
        def __init__(self, **kwargs):
            self.chat = _Chat()

    monkeypatch.setitem(sys.modules, 'mistralai', types.SimpleNamespace(Mistral=_Mistral))
    monkeypatch.setenv('MISTRAL_API_KEY', 'test-key')
    from core.llm_client import MistralProvider
    result = MistralProvider().complete('d', model='requested-model', max_tokens=5)
    assert result.model == 'provider-fallback-model'


def test_psychologue_analysis_calls_request_json(monkeypatch):
    import core.analyzer as analyzer
    seen = {}
    monkeypatch.setattr(analyzer._llm, "complete_text", lambda prompt, **kw: seen.update(kw) or "{}")
    analyzer.call_llm("prompt", fast=True, label="persona[test]")
    assert seen["json_mode"] is True


def test_persona_keys_written_with_typographic_apostrophes_are_restored():
    from core.analyzer import _normalize_keys
    data = _normalize_keys({"besoin_d’appartenance": "tribu", "desir de legacy": "transmettre", "nom": "A", "rapport_argent": "x"})
    assert data == {"besoin_d_appartenance": "tribu", "desir_de_legacy": "transmettre", "nom": "A", "rapport_argent": "x"}
    # Une clé correcte déjà présente l'emporte sur sa variante mal écrite.
    assert _normalize_keys({"besoin_d_appartenance": "vrai", "besoin_d’appartenance": "doublon"})["besoin_d_appartenance"] == "vrai"


def test_une_coupure_reseau_est_reessayee(monkeypatch):
    """Une erreur DNS passagère ne doit plus faire échouer une création."""
    import httpx
    import core.llm_client as module
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    appels = []

    class Instable:
        name = "instable"
        def complete(self, prompt, *, model, max_tokens, temperature=None, timeout_ms=300_000, system=None):
            appels.append(1)
            if len(appels) == 1:
                try:
                    raise httpx.ConnectError("[Errno 8] nodename nor servname provided")
                except httpx.ConnectError as exc:
                    raise RuntimeError("SDK error") from exc
            return LLMResponse(text="ok", model=model)

    assert complete("d", provider=Instable(), throttled=False, retry=module.RETRY_SIMPLE).text == "ok"
    assert len(appels) == 2


def test_une_erreur_metier_n_est_pas_reessayee_comme_une_coupure(monkeypatch):
    import core.llm_client as module
    appels = []

    class Refus:
        name = "refus"
        def complete(self, prompt, *, model, max_tokens, temperature=None, timeout_ms=300_000, system=None):
            appels.append(1)
            raise ValueError("prompt invalide")

    try:
        complete("d", provider=Refus(), throttled=False, retry=module.RETRY_SIMPLE)
        assert False
    except ValueError:
        pass
    assert len(appels) == 1
