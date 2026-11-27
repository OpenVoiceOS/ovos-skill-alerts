# Translations
<!-- agent-hint
covers: the locale file types and how to add or fix a language
source: locale/
generated: no
verify: ls locale/en-US/intent locale/en-US/vocab locale/en-US/dialog >/dev/null
see: troubleshooting.md
-->

Each language has a folder in `locale/<lang>/`. The skill matches utterances with file-based intents (padatious or padacioso), not with Adapt keyword intents.

## File types

| Folder | Contents |
| :--- | :--- |
| `intent/` | `.intent` files: phrase templates for each intent |
| `entity/` | `.entity` files: the values of a `{slot}` in a template |
| `vocab/` | `.voc` files: the words of a `<keyword>` in a template |
| `dialog/` | `.dialog` files: the sentences that the skill speaks, with mustache tags |

Some `.voc` files, for example `until.voc`, `priority.voc`, `repeat.voc` and `days.voc`, are also read by the skill code. The skill finds these words anywhere in the utterance, not only in a template slot.

## Steps

1. Copy the structure of `locale/en-US/` or `locale/de-DE/`.
2. Translate the files. Keep the mustache tags in each dialog.
3. Add golden rows for the language in `test/end2end/golden_utterances_<lang>.jsonl`.
4. Run the tests (see [Run the tests](testing.md)).

English and German have the most review. A machine translated most other languages, and they need a native speaker.

---
[← Run the tests](testing.md) · [Home](index.md) · [Troubleshooting →](troubleshooting.md)
