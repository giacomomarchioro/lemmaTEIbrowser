import pytest
from lemmaTEIbrowser import create_app
from lemmaTEIbrowser.models import Base, get_session


@pytest.fixture
def app():
    class TestConfig:
        TESTING = True
        DEBUG = False
        SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

    app = create_app(TestConfig)
    
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_stats_endpoint(client):
    response = client.get('/api/v1/stats')
    assert response.status_code == 200
    data = response.get_json()
    assert 'data' in data


def test_occurrences_without_params(client):
    response = client.get('/api/v1/occurrences')
    assert response.status_code == 400


def test_occurrences_with_query(client):
    response = client.get('/api/v1/occurrences?q=test&page=1&size=50')
    assert response.status_code == 200
    data = response.get_json()
    assert 'data' in data
    assert 'total_results' in data


@pytest.mark.parametrize('params', ['size=0', 'size=-1', 'page=0', 'page=no',
                                   'size=no', 'text_id=abc', 'text_id=0',
                                   'text_id=-1', 'concept_id=no'])
def test_invalid_parameters(client, params):
    assert client.get('/api/v1/occurrences?q=test&' + params).status_code == 400


def test_large_search_is_not_truncated(client):
    from lemmaTEIbrowser.models import TextEntry, Word
    with get_session() as session:
        text = TextEntry(author='A', title='T')
        session.add(text)
        session.flush()
        session.add_all([Word(id_text=text.id, xml_id_word=f'w{i}',
                              occurrence='test', lemma='test') for i in range(10001)])
        session.commit()
    data = client.get('/api/v1/occurrences?q=test&size=500&page=21').get_json()
    assert data['total_results'] == 10001
    assert data['last_page'] == 21
    assert len(data['data']) == 1


@pytest.mark.parametrize('search', ['type=concept&q=verso', 'concept_id=1',
                                    'type=alternativeLabel&q=verso'])
def test_combined_pagination(client, search):
    from lemmaTEIbrowser.models import TextEntry, Word, Concept, Phraseme
    with get_session() as session:
        text = TextEntry(author='A', title='T')
        concepts = [Concept(URLconcept=f'https://example.org/{i}/verso') for i in range(2)]
        session.add_all([text] + concepts)
        session.flush()
        session.add_all([
            Word(id_text=text.id, xml_id_word='w1', occurrence='verso', lemma='verso', id_concept=concepts[0].id_concept),
            Phraseme(id_text=text.id, normalized_form='verso uno', id_concept=concepts[0].id_concept),
            Phraseme(id_text=text.id, normalized_form='verso due', id_concept=concepts[1].id_concept),
        ])
        session.commit()
    expected_count = 2 if search == 'concept_id=1' else 3
    ids = []
    for page in range(1, expected_count + 1):
        data = client.get(f'/api/v1/occurrences?{search}&size=1&page={page}').get_json()
        assert data['total_results'] == expected_count
        assert len(data['data']) == 1
        ids.append((data['data'][0]['type'], data['data'][0]['id']))
    assert len(set(ids)) == expected_count
