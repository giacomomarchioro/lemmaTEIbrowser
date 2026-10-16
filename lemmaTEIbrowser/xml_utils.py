"""Utilities shared by TEI import and preprocessing."""

TEI_NS = 'http://www.tei-c.org/ns/1.0'
XML_ID = '{http://www.w3.org/XML/1998/namespace}id'


def ensure_word_ids(root):
    """Assign missing word IDs in place, preserving all existing XML IDs.

    Supports both ElementTree and lxml trees. Returns the number assigned.
    """
    used_ids = {el.get(XML_ID) for el in root.iter() if el.get(XML_ID)}
    counter = 1
    added = 0
    for element in root.iter():
        if element.tag not in (f'{{{TEI_NS}}}w', 'w') or element.get(XML_ID):
            continue
        candidate = f'l_w{counter:04d}'
        while candidate in used_ids:
            counter += 1
            candidate = f'l_w{counter:04d}'
        element.set(XML_ID, candidate)
        used_ids.add(candidate)
        counter += 1
        added += 1
    return added
