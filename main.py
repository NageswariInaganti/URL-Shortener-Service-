import string
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, redirect
from urllib.parse import urlparse
from collections import defaultdict
import threading

app = Flask(__name__)

# Thread-safe in-memory storage
url_mappings = {}
url_stats = defaultdict(lambda: {'clicks': 0, 'created_at': None, 'expires_at': None})
lock = threading.Lock()

def generate_short_code(length=6):
    """Generate a random alphanumeric short code"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def is_valid_url(url):
    """Validate the URL format"""
    try:
        result = urlparse(url)
        return all([result.scheme in ('http', 'https'), result.netloc])
    except ValueError:
        return False

def cleanup_expired_urls():
    """Remove expired URLs from storage"""
    now = datetime.utcnow()
    expired_codes = [code for code, stats in url_stats.items() 
                    if stats['expires_at'] and stats['expires_at'] < now]
    
    with lock:
        for code in expired_codes:
            url_mappings.pop(code, None)
            url_stats.pop(code, None)

@app.before_request
def before_request():
    """Clean up expired URLs before each request"""
    cleanup_expired_urls()

@app.route('/')
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "URL Shortener API",
        "version": "1.1.0",
        "uptime": str(datetime.utcnow() - app.start_time)
    })

@app.route('/api/health')
def api_health():
    return jsonify({
        "status": "ok",
        "message": "URL Shortener API is running",
        "statistics": {
            "active_urls": len(url_mappings),
            "total_clicks": sum(stats['clicks'] for stats in url_stats.values())
        }
    })

@app.route('/api/shorten', methods=['POST'])
def shorten_url():
    """Shorten a URL endpoint"""
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400
    
    original_url = data['url'].strip()
    ttl_hours = data.get('ttl_hours', None)  # Optional time-to-live in hours
    
    if not is_valid_url(original_url):
        return jsonify({'error': 'Invalid URL. Must include http:// or https:// and a domain'}), 400
    
    # Generate unique short code
    short_code = generate_short_code()
    
    with lock:
        while short_code in url_mappings:
            short_code = generate_short_code()
        
        # Store mapping
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(hours=ttl_hours) if ttl_hours else None
        
        url_mappings[short_code] = original_url
        url_stats[short_code] = {
            'created_at': created_at.isoformat(),
            'expires_at': expires_at.isoformat() if expires_at else None,
            'clicks': 0
        }
    
    return jsonify({
        'short_code': short_code,
        'short_url': f"{request.host_url}{short_code}",
        'original_url': original_url,
        'expires_at': url_stats[short_code]['expires_at']
    }), 201

@app.route('/<short_code>', methods=['GET'])
def redirect_to_url(short_code):
    """Redirect to original URL endpoint"""
    if short_code not in url_mappings:
        return jsonify({'error': 'Short code not found'}), 404
    
    with lock:
        url_stats[short_code]['clicks'] += 1
    
    return redirect(url_mappings[short_code], code=302)

@app.route('/api/stats/<short_code>', methods=['GET'])
def get_stats(short_code):
    """Get analytics for a short URL"""
    if short_code not in url_mappings:
        return jsonify({'error': 'Short code not found'}), 404
    
    stats = url_stats[short_code]
    return jsonify({
        'short_code': short_code,
        'original_url': url_mappings[short_code],
        'clicks': stats['clicks'],
        'created_at': stats['created_at'],
        'expires_at': stats['expires_at'],
        'is_active': not (stats['expires_at'] and datetime.fromisoformat(stats['expires_at']) < datetime.utcnow())
    })

@app.route('/api/urls', methods=['GET'])
def list_urls():
    """List all active shortened URLs"""
    return jsonify({
        'count': len(url_mappings),
        'urls': [{
            'short_code': code,
            'short_url': f"{request.host_url}{code}",
            'clicks': url_stats[code]['clicks']
        } for code in url_mappings]
    })

# Initialize app start time
app.start_time = datetime.utcnow()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
