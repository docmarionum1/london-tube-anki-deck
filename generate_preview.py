#!/usr/bin/env python3
"""Generate an HTML preview of all flashcards, viewable in a browser."""

import io
import html as html_mod
from collections import defaultdict
from contextlib import redirect_stdout
from pathlib import Path

import generate_deck as gd

# Build database (suppress verbose output)
with redirect_stdout(io.StringIO()):
    stations, line_graph, line_segments = gd.build_database()

type1 = gd.generate_type1_cards(stations)
type2 = gd.generate_type2_cards(stations, line_graph, line_segments)
type3 = gd.generate_type3_cards(stations, line_segments)
all_cards = type1 + type2 + type3

decks = defaultdict(list)
for subdeck, note in all_cards:
    decks[subdeck].append(note)

html = '<!DOCTYPE html><html><head><meta charset="utf-8">'
html += '<meta name="viewport" content="width=device-width, initial-scale=1">'
html += '<title>London Transport Flashcards</title><style>'
html += gd.SHARED_CSS
html += '''
body { background: #ddd; font-family: -apple-system, sans-serif; }
h1 { text-align: center; margin: 20px 0; color: #333; }
.deck-section { max-width: 500px; margin: 10px auto; }
.deck-header {
    background: #fff; padding: 12px 16px; border-radius: 8px;
    cursor: pointer; user-select: none; display: flex;
    justify-content: space-between; align-items: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 4px;
}
.deck-header:hover { background: #f0f0f0; }
.deck-header h2 { margin: 0; font-size: 0.95rem; color: #333; }
.deck-cards { display: none; }
.deck-cards.open { display: block; }
.card-pair { display: flex; gap: 8px; margin: 8px auto; max-width: 500px; }
.card-side {
    flex: 1; background: #F5F5F5; padding: 12px; border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.15); min-width: 0;
}
.card-side .label {
    font-size: 0.7rem; text-transform: uppercase; color: #999;
    letter-spacing: 1px; margin-bottom: 6px; text-align: center;
}
.card-num { text-align: center; font-size: 0.75rem; color: #bbb; margin: 4px 0; }
'''
html += '</style></head><body><h1>London Transport Flashcards</h1>'
for deck_path in sorted(decks):
    notes = decks[deck_path]
    short = " / ".join(deck_path.split("::")[1:])
    html += f'<div class="deck-section">'
    html += f'<div class="deck-header" onclick="this.nextElementSibling.classList.toggle(\'open\')">'
    html += f'<h2>{html_mod.escape(short)}</h2><span style="color:#999;font-size:0.85rem">{len(notes)}</span>'
    html += f'</div><div class="deck-cards">'
    for i, note in enumerate(notes):
        html += f'<div class="card-num">#{i+1}</div><div class="card-pair">'
        html += f'<div class="card-side"><div class="label">Front</div>{note.fields[0]}</div>'
        html += f'<div class="card-side"><div class="label">Back</div>{note.fields[1]}</div>'
        html += f'</div>'
    html += '</div></div>'
html += '</body></html>'

output_path = Path(__file__).parent / "preview.html"
with open(output_path, "w") as f:
    f.write(html)
print(f"Saved {output_path} ({len(all_cards)} cards)")
