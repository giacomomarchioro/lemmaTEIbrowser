from xml.etree import ElementTree as ET

from click.testing import CliRunner
from lxml import etree
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from lemmaTEIbrowser.cli import import_tei, get_surrounding_text, parse_tei_file
from lemmaTEIbrowser import create_app
from lemmaTEIbrowser.models import Base, TextEntry, Word, PhrasemeWord
from lemmaTEIbrowser.xml_utils import ensure_word_ids
from lemmaTEIbrowser.tei_converter import convert_file
from assignIDs2TEI import process_tei_file
from tei2html import convert


TEI = '''<TEI xmlns="http://www.tei-c.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>T &amp; &lt;test&gt;</title>
<author>A</author></titleStmt></fileDesc></teiHeader>
<text><body><p>before<!-- comment -->after <?test value?>
<w xml:id="w1">&lt;img src=x onerror=alert(1)&gt;</w> &amp; tail</p></body></text></TEI>'''


def test_failed_file_preserves_successes_and_generates_html(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    for name, content in [('01.tei.xml', TEI), ('02.tei.xml', '<broken'), ('03.tei.xml', TEI)]:
        (source / name).write_text(content)
    database = tmp_path / 'test.db'
    output = tmp_path / 'texts'
    result = CliRunner().invoke(import_tei, [str(source), '--db-path', str(database), '--html-dir', str(output)])
    assert result.exit_code != 0
    engine = create_engine(f'sqlite:///{database}')
    with Session(engine) as session:
        assert session.query(TextEntry).count() == 2
        assert session.query(Word).count() == 2
        for text in session.query(TextEntry):
            assert (output / f'{text.sourceFile}.tei.html').exists()
    engine.dispose()
    class TestConfig:
        TESTING = True
        DEBUG = False
        SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

    app = create_app(TestConfig)
    app.static_folder = str(tmp_path)
    response = app.test_client().get('/static/texts/01.tei.html?w=w1')
    assert response.status_code == 200
    assert b'id="w1"' in response.data


def test_converters_escape_text_and_handle_comments(tmp_path):
    path = tmp_path / 'test.tei.xml'
    path.write_text(TEI)
    for html in [convert_file(path, 1), convert(str(path))]:
        assert '<img src=x' not in html
        assert '&lt;img src=x' in html
        assert 'beforeafter' in html
        assert '&amp; tail' in html
        assert 'T &amp; &lt;test&gt;' in html


def test_ids_avoid_existing_ids_on_any_element(tmp_path):
    source = tmp_path / 'test.xml'
    source.write_text('<TEI xmlns="http://www.tei-c.org/ns/1.0"><text xml:id="l_w0002"><body><w xml:id="l_w0001">a</w><w>b</w><w>c</w></body></text></TEI>')
    output = tmp_path / 'output.xml'
    process_tei_file(str(source), str(output))
    root = etree.parse(str(output))
    ids = root.xpath('//@xml:id')
    assert len(ids) == len(set(ids)) == 4


def test_context_tracks_specific_word():
    root = ET.fromstring('<root><p>one two three four five <w>a</w> <w>target</w> <w>c</w> <w>d</w> <w>target</w> <w>f</w></p></root>')
    words = root.findall('.//w')
    assert get_surrounding_text(words[1], root, window=1) == 'a target c'
    assert get_surrounding_text(words[4], root, window=1) == 'd target f'
    assert get_surrounding_text(words[1], root, window=0) == 'target'


def test_import_assigns_missing_ids_and_reuses_them_in_html(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    path = source / 'test.tei.xml'
    xml = '''<TEI xmlns="http://www.tei-c.org/ns/1.0">
    <teiHeader><fileDesc><titleStmt><title>T</title><author>A</author></titleStmt></fileDesc></teiHeader>
    <text><body><p xml:id="l_w0002"><w>concento</w>
    <w xml:id="l_w0001" ana="https://example.org/verso">verso</w> <w>altro</w>
    <span type="baseForm" target="#l_w0001" n="verso"/>
    </p></body></text></TEI>'''
    path.write_text(xml)
    database = tmp_path / 'test.db'
    output = tmp_path / 'html'
    result = CliRunner().invoke(import_tei, [str(source), '--db-path', str(database), '--html-dir', str(output)])
    assert result.exit_code == 0, result.output
    engine = create_engine(f'sqlite:///{database}')
    with Session(engine) as session:
        words = session.query(Word).order_by(Word.id_word_entry).all()
        assert [word.xml_id_word for word in words] == ['l_w0003', 'l_w0001', 'l_w0004']
        html = etree.HTML((output / 'test.tei.html').read_text())
        for word in words:
            spans = html.xpath('//span[@id=$id]', id=word.xml_id_word)
            assert len(spans) == 1
            assert ''.join(spans[0].itertext()) == word.occurrence
        assert session.query(PhrasemeWord).one().word.xml_id_word == 'l_w0001'
    engine.dispose()
    assert path.read_text() == xml


def test_direct_parser_assigns_missing_ids(tmp_path):
    path = tmp_path / 'test.tei.xml'
    path.write_text(TEI.replace(' xml:id="w1"', ''))
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        parse_tei_file(path, session)
        session.commit()
        assert session.query(Word).one().xml_id_word == 'l_w0001'
    engine.dispose()


def test_generated_word_ids_are_stable():
    root = ET.fromstring('<root><w>a</w><w xml:id="l_w0001">b</w><w>c</w></root>')
    assert ensure_word_ids(root) == 2
    original = ET.tostring(root)
    assert ensure_word_ids(root) == 0
    assert ET.tostring(root) == original
