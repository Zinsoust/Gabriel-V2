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
    assert model_for_tier("fast") != model_for_tier("deep")


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
