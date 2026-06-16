# ─── Objet de contexte partagé entre les agents ──────────────────────────────
#
# AnalysisContext est le "bus" du pipeline.
# Il part de app.py avec les données brutes,
# traverse chaque agent qui y dépose sa contribution,
# et finit par produire le rapport final pour l'API.
#
# Structure :
#   context.input        → données brutes (commentaires, brain, video, title)
#   context.contributions → {agent_id: rapport} — rempli par chaque agent
#   context.errors        → {agent_id: message}  — erreurs non fatales
#   context.to_response() → rapport final fusionné pour le frontend


class AnalysisContext:

    def __init__(self, comments, brain_context="", video_context="", title="", memory_context=""):
        # ── Données d'entrée — immuables pendant le pipeline
        self.input = {
            'comments':       comments,
            'brain_context':  brain_context,
            'video_context':  video_context,
            'title':          title,
            'memory_context': memory_context,
        }

        # ── Contributions des agents — remplies au fil du pipeline
        self.contributions = {}   # { agent_id: dict }

        # ── Erreurs non fatales — l'agent a échoué mais le pipeline continue
        self.errors = {}          # { agent_id: str }

        # ── Journal du pipeline — pour debug et transparence
        self.log = []

    # ── Raccourcis lecture input ──────────────────────────────────────────────

    @property
    def comments(self):
        return self.input['comments']

    @property
    def brain_context(self):
        return self.input['brain_context']

    @property
    def video_context(self):
        return self.input['video_context']

    @property
    def title(self):
        return self.input['title']

    # ── Écriture / lecture contributions ─────────────────────────────────────

    def add(self, agent_id, data):
        """Un agent dépose sa contribution."""
        if isinstance(data, dict):
            self.contributions[agent_id] = data

    def get(self, agent_id, default=None):
        """Un agent lit la contribution d'un agent précédent."""
        return self.contributions.get(agent_id, default)

    def record_error(self, agent_id, message):
        self.errors[agent_id] = message
        self.log.append(f"[ERREUR] {agent_id} : {message}")

    def record_step(self, message):
        self.log.append(message)

    # ── Assemblage du rapport final ───────────────────────────────────────────

    def to_response(self):
        """
        Fusionne toutes les contributions en un seul dict plat pour le frontend.
        Les clés privées (_agent, _pipeline, etc.) sont préservées séparément.
        """
        result = {}

        # Fusionner les contributions dans l'ordre du pipeline
        for agent_id, data in self.contributions.items():
            if isinstance(data, dict):
                # Les clés publiques (données) vont dans result
                for k, v in data.items():
                    if not k.startswith('_'):
                        result[k] = v

        # Méta-données pipeline
        result['_pipeline'] = {
            'agents_joues':  list(self.contributions.keys()),
            'agents_errors': self.errors,
            'log':           self.log,
        }

        return result
