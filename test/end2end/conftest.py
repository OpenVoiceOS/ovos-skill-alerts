import os

# ovos-skill-alerts is the heaviest skill in the fleet (~35 intents). Under coverage
# instrumentation on 2-core CI runners its MiniCroft training exceeds the 180s
# ovoscope trained-wait default (times out at 180, verified green at 300), so raise
# the ceiling here per the ovoscope heavy-skill convention. The multilang fixture
# sets its own higher 480 explicitly and still wins.
os.environ.setdefault("OVOSCOPE_TRAINED_TIMEOUT", "300")
