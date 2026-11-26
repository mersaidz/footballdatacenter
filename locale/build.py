"""Fill locale/*/django.po from translations.py and compile .mo (needs `pip install polib`)."""
import sys
from pathlib import Path

import polib

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from translations import T  # noqa: E402

missing = set()
for idx, lang in ((0, 'ru'), (1, 'kk'), (None, 'en')):
    po_path = HERE / lang / 'LC_MESSAGES' / 'django.po'
    po = polib.pofile(str(po_path))
    po.metadata['Language'] = lang
    po.metadata['Content-Type'] = 'text/plain; charset=UTF-8'
    po.metadata['Plural-Forms'] = {'ru': 'nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);',
                                   'kk': 'nplurals=2; plural=(n!=1);', 'en': 'nplurals=2; plural=(n != 1);'}[lang]
    for e in po:
        e.flags = [f for f in e.flags if f != 'fuzzy']
        if idx is None:
            e.msgstr = ''                       # English = source text
        elif e.msgid in T:
            e.msgstr = T[e.msgid][idx]
        else:
            missing.add(e.msgid)
    po.save(str(po_path))
    po.save_as_mofile(str(po_path.with_suffix('.mo')))
print('compiled ru, kk, en;', f'{len(missing)} without translation: {sorted(missing)}' if missing else 'all translated')
