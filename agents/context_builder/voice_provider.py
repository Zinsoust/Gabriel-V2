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


# ─── Configuration vocale centralisée ─────────────────────────────────────
#
# Une seule source de vérité pour tout ce qui touche à la voix de Gabriel —
# avant cette centralisation, la voix par défaut vivait dans une constante
# et les réglages ElevenLabs (stability/style...) étaient codés en dur au
# milieu de synthesize(), à deux endroits différents à faire évoluer en
# même temps si jamais l'un changeait sans l'autre.
#
# "speed" a été vérifié en conditions réelles (pas supposé depuis la doc
# ElevenLabs) : à texte identique, speed=0.7 produit un fichier ~45% plus
# gros que speed=1.2 à bitrate constant — donc une durée réellement plus
# longue, l'effet est réel, pas silencieusement ignoré par l'API.
#
# "Adam" reste la voix principale — vérifiée compatible avec le plan
# ElevenLabs actuel (gratuit). "Arnold" sert de secours : si la voix
# principale échoue (compte, quota, voix retirée du catalogue...), Gabriel
# bascule dessus en un seul appel de plus plutôt que de couper le son.
GABRIEL_VOICE_CONFIG = {
    "provider":           "elevenlabs",
    "voice_id":           "pNInz6obpgDQGcFmaJgB",   # Adam — grave, posée
    "fallback_voice_id":  "VR6AewLTigWG4xSOukaG",   # Arnold — secours si Adam échoue
    "model_id":           "eleven_multilingual_v2",
    "stability":          0.38,
    "similarity_boost":   0.8,
    "style":              0.45,
    # Débit légèrement posé par défaut — "il ne se précipite pas" (brief
    # §2). 1.0 = débit natif ElevenLabs ; en dessous = plus lent.
    "speed":              0.95,
    "speaker_boost":      True,
    "timeout_s":          30,
}

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

# Débit par posture — tone_renderer.py classe chaque réponse en pace
# slow/measured/standard (brief §2 : "il ne se précipite pas" sur une
# contradiction, mais reste naturel sur une simple reconnaissance). Valeurs
# resserrées autour du réglage par défaut vérifié (0.95) : l'effet doit rester
# perceptible sans jamais sonner artificiel ou ralenti au point de gêner.
_SPEED_BY_PACE = {
    "slow":     0.85,
    "measured": 0.92,
    "standard": GABRIEL_VOICE_CONFIG["speed"],
}


def speed_for_pace(pace: str) -> float:
    return _SPEED_BY_PACE.get(pace, GABRIEL_VOICE_CONFIG["speed"])


def is_allowed_voice_id(voice_id: str) -> bool:
    """Barrière de sécurité autant que de coût : n'accepter au clic dans
    l'interface que des voix déjà vérifiées contre le compte réel — jamais
    un identifiant arbitraire transmis par le client, qui pourrait tomber
    sur une voix payante et faire échouer chaque appel en silence."""
    return voice_id in _VOICE_CATALOG_IDS


def check_voice_compatibility(voice_id: str, api_key: str = None) -> dict:
    """Teste une voix contre le compte ElevenLabs réel avec un texte minimal
    — jamais supposer qu'une voix listée dans la bibliothèque ElevenLabs est
    utilisable par le plan actuel (brief §7). À utiliser au moment d'ajouter
    une voix au catalogue, pas à chaque requête (coût + latence). Retourne
    {"ok": bool, "status_code": int|None, "error": str|None}."""
    import requests
    key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return {"ok": False, "status_code": None, "error": "ELEVENLABS_API_KEY manquante."}
    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
            json={"text": "Test.", "model_id": GABRIEL_VOICE_CONFIG["model_id"]},
            timeout=15,
        )
    except requests.RequestException as e:
        return {"ok": False, "status_code": None, "error": str(e)}
    return {"ok": resp.status_code == 200, "status_code": resp.status_code,
            "error": None if resp.status_code == 200 else resp.text[:200]}


class ElevenLabsVoiceProvider(VoiceProvider):
    _BASE = "https://api.elevenlabs.io/v1"

    def __init__(self, api_key: str, voice_id: str = None, tts_model_id: str = None):
        self._key = api_key
        self._voice_id = voice_id or GABRIEL_VOICE_CONFIG["voice_id"]
        self._fallback_voice_id = GABRIEL_VOICE_CONFIG["fallback_voice_id"]
        self._tts_model_id = tts_model_id or GABRIEL_VOICE_CONFIG["model_id"]

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

    def _synthesize_once(self, text: str, voice_id: str, speed: float) -> bytes:
        import requests
        cfg = GABRIEL_VOICE_CONFIG
        try:
            resp = requests.post(
                f"{self._BASE}/text-to-speech/{voice_id}",
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
                    # speed vérifié en conditions réelles (voir GABRIEL_VOICE_CONFIG) ;
                    # dérivé de la posture de la réponse (voir speed_for_pace).
                    "voice_settings": {
                        "stability": cfg["stability"],
                        "similarity_boost": cfg["similarity_boost"],
                        "style": cfg["style"],
                        "speed": speed,
                        "use_speaker_boost": cfg["speaker_boost"],
                    },
                },
                timeout=cfg["timeout_s"],
            )
        except requests.RequestException as e:
            raise VoiceProviderError(f"Connexion à ElevenLabs impossible : {e}") from e
        if resp.status_code != 200:
            raise VoiceProviderError(f"ElevenLabs TTS a répondu {resp.status_code} : {resp.text[:300]}")
        return resp.content

    def synthesize(self, text: str, voice_id: str = None, pace: str = None) -> bytes:
        """Bascule sur la voix de secours si la voix demandée échoue — un
        compte gratuit peut perdre l'accès à une voix du jour au lendemain
        (changement de plan ElevenLabs, retrait du catalogue...) ; mieux
        vaut une voix différente qu'un silence total côté utilisateur.
        "pace" (slow/measured/standard, voir tone_renderer.speech_profile)
        module le débit ElevenLabs pour CETTE réponse précise — absent ou
        inconnu, on retombe sur le débit par défaut du compte."""
        primary = voice_id or self._voice_id
        speed = speed_for_pace(pace)
        try:
            audio = self._synthesize_once(text, primary, speed)
            print(f"[VOICE] elevenlabs voice={primary} pace={pace or 'standard'} ok")
            return audio
        except VoiceProviderError as primary_error:
            if primary == self._fallback_voice_id:
                raise  # déjà la voix de secours — rien de plus à tenter
            print(f"[VOICE] elevenlabs voice={primary} échec ({primary_error}) — repli sur {self._fallback_voice_id}")
            try:
                audio = self._synthesize_once(text, self._fallback_voice_id, speed)
                print(f"[VOICE] elevenlabs voice={self._fallback_voice_id} (secours) ok")
                return audio
            except VoiceProviderError:
                raise primary_error from None  # l'erreur d'origine est la plus utile à journaliser


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
