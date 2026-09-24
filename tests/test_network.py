"""IPv4 d'abord : sans ça, un IPv6 annoncé mais cassé faisait expirer la
collecte YouTube (voir core/network.py)."""
import socket

import core.network as network


def test_ipv4_addresses_come_first_and_none_are_dropped(monkeypatch):
    v6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('2607:f8b0::200a', 443, 0, 0))
    v4 = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('172.217.118.4', 443))
    monkeypatch.setattr(network, '_original_getaddrinfo', lambda *a, **k: [v6, v4])
    monkeypatch.setattr(socket, 'getaddrinfo', socket.getaddrinfo)
    assert network.prefer_ipv4() is True
    assert socket.getaddrinfo('youtube.googleapis.com', 443) == [v4, v6]


def test_can_be_disabled(monkeypatch):
    monkeypatch.setenv('PREFER_IPV4', 'false')
    monkeypatch.setattr(socket, 'getaddrinfo', socket.getaddrinfo)
    before = socket.getaddrinfo
    assert network.prefer_ipv4() is False
    assert socket.getaddrinfo is before
