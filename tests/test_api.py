import pytest
from lemmaTEIbrowser import create_app
from lemmaTEIbrowser.models import Base, get_session


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        from lemmaTEIbrowser.models import init_db
        init_db(app)
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