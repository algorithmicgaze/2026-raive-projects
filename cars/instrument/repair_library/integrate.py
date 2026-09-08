# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create AI-repaired Figment variants while preserving the original projects."""
import json,sys
from pathlib import Path

root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[2]/'output-figment'
manifest=json.loads((root/'manifest-repaired.json').read_text())
expected={c['sheet'] for c in json.loads((root/'manifest.json').read_text())['clips']}
assert len(manifest['clips'])==len(expected),'Repaired library is incomplete'
for c in manifest['clips']:assert (root/c['sheet']).is_file(),c['sheet']
source=(Path(__file__).resolve().parent.parent/'figment/highway.js').read_text()
for name in ['highway.fgmt','highway-hands.fgmt']:
    original=root/name
    p=root/f'{original.stem}-ai-repaired{original.suffix}'
    before=json.loads(original.read_text());after=json.loads(original.read_text())
    matched=False
    for t in after['types']:
        if t['type']=='project.highway':t['source']=source;matched=True
    assert matched,f'No Highway type in {name}'
    for node in after['nodes']:
        if node['type']=='project.highway':node.setdefault('values',{})['manifest']={'type':'value','value':'manifest-repaired.json'}
    # Only the Highway implementation and its library path may change.
    restored=json.loads(json.dumps(after))
    for t,old in zip(restored['types'],before['types']):
        if t['type']=='project.highway':t['source']=old['source']
    for node,old in zip(restored['nodes'],before['nodes']):
        if node['type']=='project.highway':node['values']=old.get('values',{})
    assert restored==before,f'Unexpected project change in {name}'
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(after,indent=1));temp.replace(p)
    print(f'Created {p.name} from {name}; controls, node layout and connections preserved')
