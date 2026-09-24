"""Résolution réseau : IPv4 d'abord.

Constaté le 13/09/2026 : sur un réseau où l'IPv6 est annoncé mais ne route
pas, Python essaie l'adresse IPv6 de Google en premier et attend l'expiration
(15 s avec httplib2 → la collecte YouTube échouait ; 123 s avec requests).
curl, qui essaie les deux familles en parallèle, passait en moins d'une seconde.

On garde toutes les adresses, on change seulement l'ordre : IPv4 avant IPv6.
Un serveur IPv6-seul reste joignable. Désactivable avec PREFER_IPV4=false.
"""
import os
import socket

_original_getaddrinfo = socket.getaddrinfo


def _ipv4_first(*args, **kwargs):
    resultats = _original_getaddrinfo(*args, **kwargs)
    return sorted(resultats, key=lambda info: 0 if info[0] == socket.AF_INET else 1)


def prefer_ipv4():
    """Idempotent : installe le tri une seule fois pour tout le processus."""
    if os.environ.get('PREFER_IPV4', 'true').lower() in ('0', 'false', 'no'):
        return False
    if socket.getaddrinfo is not _ipv4_first:
        socket.getaddrinfo = _ipv4_first
    return True
