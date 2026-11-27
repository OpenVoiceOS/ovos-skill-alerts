"""Send each phrase quoted in docs/usage.md to a padacioso container of the en-US intents."""
import re
import sys
from pathlib import Path

from padacioso import IntentContainer
from ovos_spec_tools.resources import LocaleResources

LANG = "en-US"
res = LocaleResources("locale")
container = IntentContainer()
for path in sorted(Path("locale", LANG, "intent").glob("*.intent")):
    container.add_intent(path.stem, res.load_intent(path.stem, LANG))

text = Path("docs/usage.md").read_text()
phrases = re.findall(r'^- "([^"]+)"', text, re.M) + re.findall(r'^"([^"]+)"\s+->', text, re.M)
missed = 0
for phrase in phrases:
    utterance = re.sub(r"[.?!]+$", "", phrase).lower()
    match = container.calc_intent(utterance)
    name = match.get("name") if match else None
    missed += name is None
    print(f"{name or 'NO MATCH':24} {phrase}")
print(f"{len(phrases)} phrases, {missed} with no intent")
sys.exit(1 if missed or not phrases else 0)
