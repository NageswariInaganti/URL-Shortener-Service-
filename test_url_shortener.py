import pytest
from app.main import app
from datetime import datetime, timedelta
import threading
import time

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_checks(client):
    """Test health check endpoints"""
    # Root endpoint
    response = client.get('/')
    assert response.status_code == 200
    assert b"healthy" in response.data
    
    # API health endpoint
    response = client.get('/api/health')
    assert response.status_code == 200
    assert b"ok" in response.data

def test_url_shortening(client):
    """Test URL shortening workflow"""
    # Test valid URL
    response = client.post('/api/shorten', json={'url': 'https://example.com'})
    assert response.status_code == 201
    data = response.get_json()
    assert 'short_code' in data
    assert 'short_url' in data
    
    # Test invalid URL
    response = client.post('/api/shorten', json={'url': 'invalid-url'})
    assert response.status_code == 400

def test_url_redirection(client):
    """Test URL redirection"""
    # Shorten a URL
    shorten_resp = client.post('/api/shorten', json={'url': 'https://example.org'})
    short_code = shorten_resp.get_json()['short_code']
    
    # Redirect
    redirect_resp = client.get(f'/{short_code}', follow_redirects=False)
    assert redirect_resp.status_code == 302
    assert redirect_resp.location == 'https://example.org'
    
    # Check stats incremented
    stats_resp = client.get(f'/api/stats/{short_code}')
    assert stats_resp.get_json()['clicks'] == 1

def test_url_expiration(client):
    """Test URL expiration"""
    # Shorten with 1 second TTL
    response = client.post('/api/shorten', 
                         json={'url': 'https://temp.com', 'ttl_hours': 0.000278})  # ~1 second
    short_code = response.get_json()['short_code']
    
    # Should work immediately
    assert client.get(f'/{short_code}').status_code == 302
    
    # Wait for expiration
    time.sleep(1.5)
    
    # Should be expired now
    assert client.get(f'/{short_code}').status_code == 404
    assert client.get(f'/api/stats/{short_code}').status_code == 404

def test_concurrent_access(client):
    """Test concurrent access to the service"""
    # Shorten a URL
    shorten_resp = client.post('/api/shorten', json={'url': 'https://concurrent.example'})
    short_code = shorten_resp.get_json()['short_code']
    
    click_counts = []
    
    def make_requests():
        for _ in range(10):
            client.get(f'/{short_code}', follow_redirects=False)
    
    # Create multiple threads
    threads = [threading.Thread(target=make_requests) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Check the final count
    stats_resp = client.get(f'/api/stats/{short_code}')
    assert stats_resp.get_json()['clicks'] == 50

def test_list_urls(client):
    """Test listing all URLs"""
    # Clear existing URLs
    client.get('/')  # Triggers cleanup
    
    # Add some URLs
    client.post('/api/shorten', json={'url': 'https://example1.com'})
    client.post('/api/shorten', json={'url': 'https://example2.com'})
    
    # Get list
    response = client.get('/api/urls')
    assert response.status_code == 200
    data = response.get_json()
    assert data['count'] == 2
    assert len(data['urls']) == 2
