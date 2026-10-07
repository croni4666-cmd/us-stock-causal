"""Give SVG IDs document-local namespaces while preserving local references."""
from collections import Counter
import re
from uuid import uuid4

URL_REF=re.compile(r'''url\(\s*['"]?#([^)'"\s]+)['"]?\s*\)''')


def namespace_svg_ids(root):
    elements=[e for e in root.iter() if e.get('id')]
    counts=Counter(e.get('id') for e in elements)
    references=set()
    for element in root.iter():
        for key,value in element.attrib.items():
            references.update(URL_REF.findall(value))
            if key.endswith('href') and value.startswith('#'): references.add(value[1:])
        if str(element.tag).endswith('style') and element.text:
            references.update(URL_REF.findall(element.text))
    if any(ref not in counts or counts[ref]!=1 for ref in references):
        raise ValueError('SVG has missing or ambiguous local reference targets')
    prefix='svg-'+uuid4().hex
    mapping={}
    for i,element in enumerate(elements):
        old=element.get('id'); new=f'{prefix}-{i}-{old}'
        mapping.setdefault(old,new)
        element.set('id',new)
    def urls(value): return URL_REF.sub(lambda match:'url(#'+mapping[match[1]]+')',value)
    for element in root.iter():
        for key,value in list(element.attrib.items()):
            if key=='id': continue
            if key.endswith('href') and value.startswith('#'): value='#'+mapping[value[1:]]
            element.set(key,urls(value))
        if str(element.tag).endswith('style') and element.text: element.text=urls(element.text)
    return len(elements)
