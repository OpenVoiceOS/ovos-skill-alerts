"""it-IT list_alerts and cancel_alert must hear Italian, not a word list.

Both files were a cross product of three bags of words translated one word
at a time from an English option list. The first bag held `chiaro` for
"clear", the adjective and not the verb, `ottenuto` for "got", and the
fragment `hanno i` with the English pronoun left in place. The middle bag
held 20 function words, `per caso mi io è sono ho un una di in da il non a
ci c la devo le`, and the last bag repeated the noun list the locale
already ships in `entity/alertkind.entity`.

A cross product fails in both directions at once, and only the missing
match is visible. Measured with a real padacioso container built from this
locale's own files, 1 of 17 ordinary Italian requests reached the right
intent.

The templates now use the `{alertkind}` slot, as en-US does, instead of
repeating a noun list inside each file. Both registers are kept, the
singular `dimmi` and the plural `ditemi` and `diteci`, and the first
person plural `abbiamo` beside `ho`.

These rows are the regression: the positives are ordinary requests an
Italian speaker makes, and the negatives are definition questions that
must not be read as a request to list or to cancel anything.
"""
from pathlib import Path

import pytest
from padacioso import IntentContainer

LOCALE = Path(__file__).parent.parent / "locale" / "it-IT"

POSITIVES = [
    ("quali allarmi ho", "list_alerts"),
    ("quali sono i miei promemoria", "list_alerts"),
    ("elenca i miei allarmi", "list_alerts"),
    ("elenca gli allarmi", "list_alerts"),
    ("mostrami i miei promemoria", "list_alerts"),
    ("dimmi i miei allarmi", "list_alerts"),
    ("ditemi gli allarmi", "list_alerts"),
    ("ho qualche promemoria", "list_alerts"),
    ("abbiamo degli allarmi", "list_alerts"),
    ("ci sono eventi", "list_alerts"),
    ("quando è il mio prossimo allarme", "list_alerts"),
    ("quanti allarmi ho", "list_alerts"),
    ("che allarmi ho", "list_alerts"),
    ("cancella gli allarmi", "cancel_alert"),
    ("cancella tutti i miei allarmi", "cancel_alert"),
    ("elimina l'allarme", "cancel_alert"),
    ("rimuovi i miei promemoria", "cancel_alert"),
    ("annulla il prossimo allarme", "cancel_alert"),
    ("elimina tutti gli eventi", "cancel_alert"),
]

NEGATIVES = [
    "cos'è un allarme",
    "che cos'è una sveglia",
]


def _container():
    container = IntentContainer()
    for path in sorted(LOCALE.rglob("*.intent")):
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
        container.add_intent(path.stem, lines)
    for path in sorted(LOCALE.rglob("*.voc")) + sorted(LOCALE.rglob("*.entity")):
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
        container.add_entity(path.stem, lines)
    return container


@pytest.fixture(scope="module")
def container():
    return _container()


@pytest.mark.parametrize("utterance,intent", POSITIVES, ids=[u for u, _ in POSITIVES])
def test_utterance_reaches_its_intent(container, utterance, intent):
    assert container.calc_intent(utterance).get("name") == intent


@pytest.mark.parametrize("utterance", NEGATIVES)
def test_definition_question_is_not_an_alert_request(container, utterance):
    assert container.calc_intent(utterance).get("name") not in ("list_alerts",
                                                                "cancel_alert")
