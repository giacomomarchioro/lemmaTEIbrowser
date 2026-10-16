from click.testing import CliRunner
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from lemmaTEIbrowser.cli import import_tei, serve
from lemmaTEIbrowser.config import database_path, html_directory
from lemmaTEIbrowser.models import Base, TextEntry, Word


def make_database(path):
    engine = create_engine(f'sqlite:///{path}')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        text = TextEntry(author='A', title='T')
        session.add(text)
        session.flush()
        session.add(Word(id_text=text.id, xml_id_word='w1', occurrence='verso'))
        session.commit()
    engine.dispose()


def test_shared_defaults_do_not_depend_on_cwd(tmp_path, monkeypatch):
    default_db = tmp_path / 'default.db'
    default_html = tmp_path / 'texts'
    monkeypatch.delenv('DATABASE_PATH', raising=False)
    monkeypatch.delenv('TEXT_HTML_DIR', raising=False)
    monkeypatch.setattr('lemmaTEIbrowser.config.DEFAULT_DATABASE_PATH', default_db)
    monkeypatch.setattr('lemmaTEIbrowser.config.DEFAULT_HTML_DIR', default_html)
    working = tmp_path / 'other'
    working.mkdir()
    monkeypatch.chdir(working)
    assert database_path() == default_db
    result = CliRunner().invoke(import_tei, [str(working)])
    assert result.exit_code == 0, result.output
    assert default_db.exists()
    assert not (working / 'tei_database.db').exists()

    captured = []
    monkeypatch.setattr(Flask, 'run', lambda self, **kwargs: captured.append(self))
    result = CliRunner().invoke(serve, ['--no-debug'])
    assert result.exit_code == 0, result.output
    assert captured[0].config['DATABASE_PATH'] == str(default_db)
    assert captured[0].config['TEXT_HTML_DIR'] == str(default_html)
    assert f'Database: {default_db}' in result.output
    assert 'Database contents: 0 texts, 0 words' in result.output
    assert 'this database contains no words' in result.output


def test_explicit_paths_override_environment_and_serve_html(tmp_path, monkeypatch):
    database = tmp_path / 'actual.db'
    make_database(database)
    html = tmp_path / 'custom texts'
    html.mkdir()
    (html / 'test.tei.html').write_text('<p id="w1">verso</p>')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'wrong.db'))
    monkeypatch.setenv('TEXT_HTML_DIR', str(tmp_path / 'wrong-html'))
    captured = []
    monkeypatch.setattr(Flask, 'run', lambda self, **kwargs: captured.append(self))
    result = CliRunner().invoke(serve, ['--db-path', './actual.db', '--html-dir', './custom texts', '--no-debug'])
    assert result.exit_code == 0, result.output
    app = captured[0]
    assert app.config['DATABASE_PATH'] == str(database)
    client = app.test_client()
    assert client.get('/api/v1/occurrences?q=verso&type=occurrence').get_json()['total_results'] == 1
    assert client.get('/static/texts/test.tei.html').data == b'<p id="w1">verso</p>'
    assert client.get('/static/css/text.css').status_code == 200
    assert 'Templates:' in result.output
    assert 'Static assets:' in result.output
    assert 'Database contents: 1 texts, 1 words' in result.output


def test_missing_database_is_not_created(tmp_path, monkeypatch):
    missing = tmp_path / 'missing' / 'test.db'
    monkeypatch.setattr(Flask, 'run', lambda *args, **kwargs: None)
    result = CliRunner().invoke(serve, ['--db-path', str(missing), '--no-debug'])
    assert result.exit_code != 0
    assert f'Database file does not exist: {missing}' in result.output
    assert not missing.exists()


def test_environment_paths_expand_home_and_relative_paths(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('DATABASE_PATH', '~/data/test.db')
    monkeypatch.setenv('TEXT_HTML_DIR', './html')
    assert database_path() == tmp_path / 'data' / 'test.db'
    assert html_directory() == tmp_path / 'html'


def test_import_environment_paths(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    database = tmp_path / 'environment.db'
    html = tmp_path / 'environment-html'
    monkeypatch.setenv('DATABASE_PATH', str(database))
    monkeypatch.setenv('TEXT_HTML_DIR', str(html))
    result = CliRunner().invoke(import_tei, [str(source)])
    assert result.exit_code == 0, result.output
    assert database.is_file()
    assert html.is_dir()
