# Run the tests
<!-- agent-hint
covers: how to install the test extra and run the unit and end-to-end tests
source: .github/workflows/ovoscope.yml
generated: no
verify: test -f test/end2end/test_golden_utterances.py && grep -q "test_path: 'test/end2end/'" .github/workflows/ovoscope.yml
see: translations.md
-->

The skill has unit tests in `test/` and end-to-end tests in `test/end2end/`. The end-to-end tests start the skill in an ovoscope MiniCroft and send real utterances to it.

## Example

```bash
pytest test/end2end/test_spoken_numbers.py -v
```

## Steps

1. Make a venv and install the skill with the `test` extra:

   ```bash
   uv venv -p 3.11 .venv
   uv pip install -p .venv/bin/python --prerelease=allow -e '.[test]'
   ```

2. Run the unit tests:

   ```bash
   .venv/bin/python -m pytest test/ --ignore=test/end2end
   ```

3. Run the end-to-end tests:

   ```bash
   .venv/bin/python -m pytest test/end2end/
   ```

`pytest.ini` stops each test after 420 seconds. The CI workflow `.github/workflows/ovoscope.yml` runs `test/end2end/` on each pull request, with Python 3.11 and no parallel workers.

## Golden utterances

Each locale has two files in `test/end2end/`:

- `golden_utterances_<lang>.jsonl`: utterances and the intent that each one must reach.
- `negative_utterances_<lang>.jsonl`: utterances that must not reach the skill.

`test_golden_utterances.py` sends each row to the skill. Each row has the fields `utterance`, `lang` and `intent_label`. The routing rate of a locale must be at least `ovoscope_min_routing_rate` in `pytest.ini` (0.75).

## Reference

| Test file | What it checks |
| :--- | :--- |
| `test_golden_utterances.py` | each golden row reaches its intent |
| `test_intents_en_us.py` | the en-US intents and their handlers, with padacioso |
| `test_spoken_numbers.py` | the ordinals and counts that the skill speaks, per language |
| `test_wake_arbitration.py` | the "wake" words go to the correct skill when ovos-skill-naptime is loaded |
| `test_fleet_arbitration.py` | recurring reminders go to this skill and not to ovos-skill-date-time |

---
[← How alerts are timed](scheduling.md) · [Home](index.md) · [Translations →](translations.md)
