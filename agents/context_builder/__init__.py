# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDER ARCHITECTURE — point d'entrée du package.
#
# Statut de migration : la V1.1 (orchestrateur + Business Context Store réel)
# est en construction dans ce package, étape par étape (voir schema.py pour le
# schéma des 7 dimensions déjà verrouillé). En attendant que l'orchestrateur
# soit prêt et vérifié, ce fichier réexporte l'implémentation existante
# (agents/context_builder_legacy.py) pour que /context-chat continue de
# fonctionner exactement comme avant, sans interruption.
#
# Ne pas ajouter de logique ici — ce fichier est un simple point d'entrée.
# ═══════════════════════════════════════════════════════════════════════════

from agents.context_builder_legacy import process_message, extract_context

__all__ = ["process_message", "extract_context"]
