# The Board - Auto

Free, automatic version of the betting board. GitHub runs it three times a day (8 AM, 5 PM, midnight Central):

1. Grades every logged pick from ESPN final scores and compares it with the closing line.
2. Builds today's card for NFL, college football, NBA, college basketball and NHL from ESPN's free feeds (DraftKings lines, FPI/BPI, injuries, every game played this season).
3. Rebuilds `docs/index.html` - the page you open on your phone.

Cash picks need both models to agree, confidence 7.0+, and a past-games test showing that kind of pick won 53.5%+ over 200+ games. Everything else is paper.

Run it by hand: Actions tab -> board -> Run workflow. Locally: `python -m board.run`.
Settings you can edit: `data/settings.json` (bankroll, goal), `data/rules.json` (rules text).
