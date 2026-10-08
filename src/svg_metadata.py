"""Give SVG IDs document-local namespaces while preserving local references."""
from collections import Counter
import re
from uuid import uuid4

URL_REF=re.compile(r'''url\(\s*['"]?#([^)'"\s]+)['"]?\s*\)''')

SVG_NS = 'http://www.w3.org/2000/svg'
SVG_TAGS = set('svg g defs path rect circle ellipse line polyline polygon text tspan '
               'title desc use clipPath linearGradient radialGradient stop pattern image style'.split())
SVG_ATTRS = set('id version viewBox width height x y x1 y1 x2 y2 cx cy r rx ry d points '
               'transform preserveAspectRatio clip-path clip-rule fill fill-rule fill-opacity '
               'stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-dasharray '
               'stroke-dashoffset stroke-miterlimit opacity color font-family font-size font-style '
               'font-weight text-anchor dominant-baseline offset stop-color stop-opacity '
               'gradientUnits gradientTransform patternUnits patternContentUnits patternTransform'.split())
CSS_PROPERTIES = set('fill fill-rule fill-opacity stroke stroke-width stroke-opacity stroke-linecap '
                     'stroke-linejoin stroke-dasharray stroke-dashoffset stroke-miterlimit opacity '
                     'font font-family font-size font-style font-weight text-anchor '
                     'dominant-baseline color clip-path'.split())


def _safe_css(value):
    """Only presentation declarations and local fragment URLs are permitted."""
    declarations = []
    for declaration in value.split(';'):
        key, separator, val = declaration.partition(':')
        key, val = key.strip().lower(), val.strip()
        if not separator or key not in CSS_PROPERTIES:
            continue
        lowered = val.lower()
        if any(ord(c)<32 for c in val) or any(token in lowered for token in ('\\', '@', '<', '>', 'expression', '/*', '*/')):
            continue
        # CSS URLs are allowed only when the whole value is a local reference.
        if 'url' in lowered and not URL_REF.fullmatch(val):
            continue
        if '(' in val and not (URL_REF.fullmatch(val) or re.fullmatch(r'rgba?\([\d\s.,%]+\)', val, re.I)):
            continue
        declarations.append(f'{key}: {val}')
    return '; '.join(declarations)


def sanitize_svg(root):
    """Remove active SVG and external resources, retaining Matplotlib geometry."""
    from lxml import etree
    if root.tag != '{' + SVG_NS + '}svg':
        raise ValueError('expected SVG namespace/root')
    for element in list(root.iter()):
        if not isinstance(element.tag, str):
            if isinstance(element, etree._Entity):
                raise ValueError('SVG entities are not supported')
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
            continue
        name = etree.QName(element)
        if name.namespace != SVG_NS or name.localname not in SVG_TAGS:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
            continue
        for key, value in list(element.attrib.items()):
            attr = etree.QName(key)
            local = attr.localname
            if attr.namespace not in (None, 'http://www.w3.org/1999/xlink'):
                del element.attrib[key]
            elif local == 'href':
                inline_image = (name.localname == 'image' and re.fullmatch(
                    r'data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=\s]+', value))
                if not value.startswith('#') and not inline_image:
                    del element.attrib[key]
            elif local == 'style':
                element.set(key, _safe_css(value))
            elif local in CSS_PROPERTIES and (any(ord(c)<32 for c in value) or
                    any(token in value.lower() for token in ('\\','/*','*/','expression','@','<','>'))):
                # Presentation attributes are CSS too: escaped spellings of
                # url() must not bypass the literal external-resource check.
                del element.attrib[key]
            elif local not in SVG_ATTRS and not local.startswith('data-'):
                del element.attrib[key]
            elif 'url' in value.lower() and not URL_REF.fullmatch(value):
                del element.attrib[key]
        if name.localname == 'style':
            # Matplotlib's only default stylesheet is a universal presentation rule.
            match = re.fullmatch(r'\s*\*\s*\{([^{}]*)\}\s*', element.text or '')
            element.text = '*{' + _safe_css(match[1]) + '}' if match else ''
    return root


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
