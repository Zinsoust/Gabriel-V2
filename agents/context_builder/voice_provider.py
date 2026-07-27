# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDER ARCHITECTURE — Voice Provider
#
# Rôle unique : parler à la place de Gabriel (texte → audio) et l'écouter
# (audio → texte). Abstraction volontairement minimale pour rester
# interchangeable (brief : "VoiceProvider swappable ElevenLabs/OpenAI") —
# l'orchestrateur et les routes Flask ne connaissent que cette interface,
# jamais les détails d'un fournisseur précis.
# ═══════════════════════════════════════════════════════════════════════════

import os


class VoiceProvider:
    """Interface commune — toute implémentation doit fournir ces deux
    opérations. Ne jamais appeler un SDK/fournisseur externe en dehors
    d'une classe qui hérite de celle-ci."""

    def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        raise NotImplementedError

    def synthesize(self, text: str, voice_id: str = None) -> bytes:
        raise NotImplementedError


class VoiceProviderError(Exception):
    """Erreur fournisseur normalisée — les routes Flask n'ont pas besoin de
    connaître la forme exacte des erreurs ElevenLabs (ou d'un futur
    fournisseur) pour répondre proprement à l'utilisateur."""


# Voix ElevenLabs pré-enregistrée "Adam" — grave, posée. "Josh" avait été
# essayée pour se rapprocher du registre "avocat d'affaires sûr de lui"
# (ton défini dans tone_renderer.py), mais mesuré en conditions réelles :
# ElevenLabs la classe comme voix de bibliothèque réservée aux comptes
# payants (402 payment_required sur un compte gratuit) — elle coupait la
# voix de Gabriel en silence côté serveur. Adam, elle, fonctionne sur le
# compte gratuit actuel (vérifié). Le jugement sur "est-ce que ça sonne
# juste" appartient à l'oreille humaine, pas au code — changeable sans
# toucher au code via ELEVENLABS_VOICE_ID, mais vérifier d'abord que la
# voix choisie est bien utilisable par le plan ElevenLabs actif avant de
# changer la valeur par défaut ici.
_DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"

# Catalogue restreint proposé au choix dans l'interface — chaque voix a été
# testée une par une contre le compte ElevenLabs réel (voir conversation) :
# certaines voix de bibliothèque premade renvoient 402 payment_required sur
# un compte gratuit (Sam, Josh notamment) et coupent la voix de Gabriel en
# silence si on les propose sans vérification. N'ajouter une voix ici
# qu'après l'avoir testée avec succès contre le compte réel — jamais à
# l'aveugle depuis la documentation ElevenLabs seule.
VOICE_CATALOG = [
    {"id": "pNInz6obpgDQGcFmaJgB", "label": "Adam — grave, posée (défaut)"},
    {"id": "VR6AewLTigWG4xSOukaG", "label": "Arnold — nette, incisive"},
    {"id": "pqHfZKP75CvOlQylNhV4", "label": "Bill — posée, mature"},
    {"id": "ErXwobaYiN019PkySvjV", "label": "Antoni — chaleureuse, ronde"},
    {"id": "N2lVS1w4EtoT3dr4eOWO", "label": "Callum — jeune, dynamique"},
]
_VOICE_CATALOG_IDS = {v["id"] for v in VOICE_CATALOG}


def is_allowed_voice_id(voice_id: str) -> bool:
    """Barrière de sécurité autant que de coût : n'accepter au clic dans
    l'interface que des voix déjà vérifiées contre le compte réel — jamais
    un identifiant arbitraire transmis par le client, qui pourrait tomber
    sur une voix payante et faire échouer chaque appel en silence."""
    return voice_id in _VOICE_CATALOG_IDS


class ElevenLabsVoiceProvider(VoiceProvider):
    _BASE = "https://api.elevenlabs.io/v1"

    def __init__(self, api_key: str, voice_id: str = None, tts_model_id: str = None):
        self._key = api_key
        self._voice_id = voice_id or _DEFAULT_VOICE_ID
        self._tts_model_id = tts_model_id or "eleven_multilingual_v2"

    def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        import requests
        try:
            resp = requests.post(
                f"{self._BASE}/speech-to-text",
                headers={"xi-api-key": self._key},
                files={"file": ("audio", audio_bytes, mime_type or "audio/webm")},
                data={"model_id": "scribe_v1"},
                timeout=60,
            )
        except requests.RequestException as e:
            raise VoiceProviderError(f"Connexion à ElevenLabs impossible : {e}") from e
        if resp.status_code != 200:
            raise VoiceProviderError(f"ElevenLabs STT a répondu {resp.status_code} : {resp.text[:300]}")
        data = resp.json()
        return (data.get("text") or "").strip()

    def synthesize(self, text: str, voice_id: str = None) -> bytes:
        import requests
        try:
            resp = requests.post(
                f"{self._BASE}/text-to-speech/{voice_id or self._voice_id}",
                headers={
                    "xi-api-key": self._key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": self._tts_model_id,
                    # stability plus basse + style > 0 : délivery plus affirmée,
                    # moins monocorde/plate qu'un réglage "narrateur neutre" —
                    # cohérent avec le ton assuré défini dans tone_renderer.py.
                    "voice_settings": {
                        "stability": 0.38,
                        "similarity_boost": 0.8,
                        "style": 0.45,
                        "use_speaker_boost": True,
                    },
                },
                timeout=30,
            )
        except requests.RequestException as e:
            raise VoiceProviderError(f"Connexion à ElevenLabs impossible : {e}") from e
        if resp.status_code != 200:
            raise VoiceProviderError(f"ElevenLabs TTS a répondu {resp.status_code} : {resp.text[:300]}")
        return resp.content


def get_voice_provider():
    """Point d'entrée unique utilisé par les routes Flask. Retourne None si
    aucune clé n'est configurée — les routes doivent alors répondre 503
    plutôt que planter, pour que le mode texte reste toujours utilisable."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return None
    return ElevenLabsVoiceProvider(
        api_key=key,
        voice_id=os.environ.get("ELEVENLABS_VOICE_ID"),
        tts_model_id=os.environ.get("ELEVENLABS_TTS_MODEL_ID"),
    )
