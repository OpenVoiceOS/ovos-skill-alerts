"""pt-PT list_alerts and cancel_alert must hear Portuguese, and only Portuguese.

Both files used to be a cross product of three bags of words translated one
word at a time from an English option list: a first group holding `claro`
for "clear", `espetáculo` for "show", `nomeação` for "appointment",
`obteve` for "got" and the fragment `ter i` for "have I". The result
matched utterances nobody says and missed the ones people do say, and the
cross product also swallowed `o que é um alarme`, a question about what an
alarm is, into list_alerts.

The templates now use the `{alertkind}` slot the locale already ships,
as en-US does, instead of repeating a noun list inside each file.

These rows are the regression: the positives are ordinary requests a
Portuguese speaker makes, and the negative is the definition question that
must not be read as a request to list anything.
"""
from pathlib import Path

import pytest
from padacioso import IntentContainer

LOCALE = Path(__file__).parent.parent / "locale" / "pt-PT"

POSITIVES = [
    ("quando é o meu próximo alarme", "list_alerts"),
    ("quais são os meus lembretes", "list_alerts"),
    ("que alarmes tenho", "list_alerts"),
    ("lista os meus alarmes", "list_alerts"),
    ("lista alarmes", "list_alerts"),
    ("mostra os meus lembretes", "list_alerts"),
    ("diz-me os meus alarmes", "list_alerts"),
    ("tenho algum lembrete", "list_alerts"),
    ("há algum evento", "list_alerts"),
    ("o que tenho agendado", "list_alerts"),
    ("cancelar alarmes", "cancel_alert"),
    ("cancela todos os alarmes", "cancel_alert"),
    ("apaga o alarme", "cancel_alert"),
    ("elimina os meus lembretes", "cancel_alert"),
    ("cancela o próximo alarme", "cancel_alert"),
    ("remove o evento", "cancel_alert"),
]

NEGATIVES = [
    "o que é um alarme",
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
def test_definition_question_is_not_a_listing_request(container, utterance):
    assert container.calc_intent(utterance).get("name") != "list_alerts"
