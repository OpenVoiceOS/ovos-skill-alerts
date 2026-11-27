# How the skill speaks numbers
<!-- agent-hint
covers: how numtag spells counts and ordinals, the noun gender per dialog, and the fallback languages
source: util/locale.py:spoken_number
generated: no
verify: .venv/bin/python docs/verify_examples.py
see: settings.md
-->

The skill spells the numbers in its dialogs with numtag. A count takes the gender of the noun that it counts.

## Example

```python
from ovos_skill_alerts.util.locale import spoken_number

spoken_number(1, "pt-PT", "list_todo_num_deleted")  # um   (itens, masculine)
spoken_number(1, "pt-PT", "list_todo_lists")        # uma  (listas, feminine)
spoken_number(1, "es-ES", "list_todo_num_deleted")  # una  (tareas, feminine)
spoken_number(1, "de-DE", "list_todo_lists")        # eine (Listen, feminine)
spoken_number(1, "da-DK", "list_todo_num_deleted")  # et   (elementer, neuter)
spoken_number(2, "pl-PL")                           # dwa  (fallback)
```

`docs/verify_examples.py` runs these examples and compares each value.

## Rules

1. The skill gives numtag the number, the language and the gender of the noun.
2. The table `NOUN_GENDER` in `util/locale.py` holds the gender for each dialog and each language. A language that is not in the table gets the default gender of the numtag writer.
3. The ordinals that name timers ("first timer", "second timer") use the gender of the `timer_status` row.
4. numtag has no writer for eu, fa, oc, pl and sv. For these languages, the skill uses `pronounce_number` from ovos-number-parser.

## Reference

| Dialog | What it counts | Genders in the table |
| :--- | :--- | :--- |
| `timer_status` | timers, as ordinals | pt, es, fr, it, ca, gl: masculine |
| `list_todo_num_deleted` | removed entries | pt, de, ca, gl: masculine, es, fr, it: feminine, da: neuter |
| `list_todo_subitems_added` | added entries | pt, es, fr, it, ca: feminine, de, gl: masculine |
| `list_todo_lists` | lists | pt, es, fr, it, de, ca, gl: feminine |

---
[← How the skill reads times](times.md) · [Home](index.md) · [Settings and CalDAV sync →](settings.md)
