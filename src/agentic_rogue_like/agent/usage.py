"""Verbrauchsmessung fuer jeden LLM-Aufruf: eine Logzeile pro Aufruf plus
prozessweite Summen pro Zweck ("encounter", "event", "narrator").

Die Zahlen kommen aus usage_metadata der Modellantwort. Bei strukturierter Ausgabe
laedt usage.invoke_structured() dazu include_raw=True, weil LangChain die Roantwort
(und damit usage_metadata) sonst vor dem Parser versteckt. Fehlt usage_metadata -
kein Attribut, None, oder ein Dict ohne den jeweiligen Schluessel - zaehlt der
Aufruf mit 0 Tokens: gemessen wird, dass der Aufruf stattgefunden hat.

Ein Retry-Versuch ist ein eigener Aufruf und zaehlt einzeln, weil jeder Versuch
tokens kostet. Gezaeht wird nur, wenn eine Antwort vorliegt: wirft invoke selbst
(Netzwerkfehler, Timeout), ist nichts aufgezeichnet; liefert sie dagegen eine
unparsbare Antwort, wird zuerst aufgezeichnet und danach der Fehler geworfen.

Die Summen sind prozessweit und absichtlich ohne Reset-API - ein Spielprozess
soll seinen Gesamtverbrauch bis zum Ende behalten. Ein Reset ist Sache der Tests
(monkeypatch ersetzt _totals). Alle Zugriffe, lesende wie schreibende, laufen
unter einem Lock, weil der API-Server die Agents in Worker-Threads aufruft.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_totals: dict[str, dict[str, int]] = {}
_lock = threading.Lock()


def record(zweck: str, eingabe_tokens: int, ausgabe_tokens: int) -> None:
    """Ein Aufruf ist passiert: Logzeile dafuer, und er fliesst in die Summen
    dieses Zwecks ein (aufrufe, eingabe_tokens, ausgabe_tokens)."""
    with _lock:
        summe = _totals.setdefault(
            zweck, {"aufrufe": 0, "eingabe_tokens": 0, "ausgabe_tokens": 0}
        )
        summe["aufrufe"] += 1
        summe["eingabe_tokens"] += eingabe_tokens
        summe["ausgabe_tokens"] += ausgabe_tokens
    logger.info("llm usage zweck=%s eingabe=%d ausgabe=%d", zweck, eingabe_tokens, ausgabe_tokens)


def tokens_from(message: Any) -> tuple[int, int]:
    """(eingabe, ausgabe) Tokens einer Modellantwort, (0, 0) ueberall, wo die
    Angaben fehlen - auch wenn die Antwort selbst None ist."""
    metadata = getattr(message, "usage_metadata", None)
    return _token(metadata, "input_tokens"), _token(metadata, "output_tokens")


def totals() -> dict[str, dict[str, int]]:
    """Kopie der Summen, damit ein Lesender (GET /usage) nicht an _totals selbst
    schreibt; ohne einen einzigen Aufruf ist sie leer."""
    with _lock:
        return {zweck: dict(summe) for zweck, summe in _totals.items()}


def invoke_structured(model: Any, schema: type, prompt: Any, zweck: str) -> Any:
    """Strukturierter Aufruf ueber include_raw=True, damit usage_metadata der
    Roantwort erreichbar bleibt: aufgezeichnet wird der Aufruf in jedem Fall,
    zurueckkommt das geparste Ergebnis.

    Eine unparsbare Antwort liefert LangChain in parsing_error; sie wird erst
    aufgezeichnet (bezahlt hat sie Tokens laengst) und dann geworfen, genau wie
    der Fehler ohne include_raw schon bisher durchgereicht wurde.
    """
    result = model.with_structured_output(schema, include_raw=True).invoke(prompt)
    record(zweck, *tokens_from(result.get("raw")))
    parsing_error = result.get("parsing_error")
    if parsing_error is not None:
        raise parsing_error
    return result.get("parsed")


def _token(metadata: Any, key: str) -> int:
    """Ein Wert aus usage_metadata, 0 fuer alles, was kein Zahlenwert ist.
    LangChain liefert usage_metadata als Dict, andere Integrationen als Objekt."""
    if metadata is None:
        return 0
    getter = getattr(metadata, "get", None)
    value = getter(key) if callable(getter) else getattr(metadata, key, None)
    return value if isinstance(value, int) else 0
