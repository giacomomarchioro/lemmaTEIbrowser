import shutil
import subprocess
from pathlib import Path

import pytest


def test_result_rendering_escapes_untrusted_content():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for JavaScript rendering tests')
    template = (Path(__file__).parents[1] / 'lemmaTEIbrowser/templates/list.html').read_text()
    functions = 'function buildEntry' + template.split('function buildEntry', 1)[1].split('</script>', 1)[0]
    checks = r'''
const assert = require('node:assert/strict');
const payload = '<img src=x onerror=alert(1)>';
const item = {
    type: 'word', occurrence: payload, lemma: payload, context: 'target ' + payload,
    xml_id: 'w1', concept: {url: 'javascript:alert(1)'},
    text: {author: payload, title: payload, sourceFile: 'file', notBefore: payload}
};
const html = buildEntry(item);
assert.ok(!html.includes('<img'));
assert.ok(!html.includes('href="javascript:'));
assert.ok(html.includes('&lt;img'));
assert.ok(html.includes('/static/texts/file.tei.html?w=w1'));
assert.equal(highlightOccurrence('target ' + payload, 'target'),
    '<span class="highlight">target</span> &lt;img src=x onerror=alert(1)&gt;');
assert.equal(safeUrl('https://example.org/concept'), 'https://example.org/concept');
assert.equal(safeUrl('data:text/html,test'), '');
item.concept.url = 'https://example.org/?q=" onmouseover="alert(1)';
assert.ok(!buildEntry(item).includes(' onmouseover="'));
'''
    subprocess.run([node, '-e', functions + checks], check=True, capture_output=True, text=True)
