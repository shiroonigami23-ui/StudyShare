import os
import secrets
import json
from datetime import datetime
from functools import wraps

import requests  # We use the requests library for the REST API
from flask import (Flask, render_template, redirect, url_for, session, 
                   request, send_from_directory, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --- Firebase Configuration (REST API) ---
# Load credentials from the secret file
try:
    with open('firebase-credentials.json') as f:
        firebase_credentials = json.load(f)
    PROJECT_ID = firebase_credentials.get('project_id')
    print(f"SUCCESS: Loaded Firebase Project ID: {PROJECT_ID}")
except FileNotFoundError:
    PROJECT_ID = None
    print("CRITICAL ERROR: firebase-credentials.json not found!")
except Exception as e:
    PROJECT_ID = None
    print(f"CRITICAL ERROR: Could not parse firebase-credentials.json: {e}")

# Construct the base URL for Firestore REST API requests
FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

# --- App Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MATERIALS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'materials')
PROFILE_PICS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'profile_pics')

app = Flask(__name__)
app.config['MATERIALS_FOLDER'] = MATERIALS_FOLDER
app.config['PROFILE_PICS_FOLDER'] = PROFILE_PICS_FOLDER
app.secret_key = os.environ.get('SECRET_KEY', 'a-very-secret-and-random-key-for-sessions')

# --- Helper Functions for REST API ---

def firestore_get_document(collection, document_id):
    """Fetches a single document from Firestore."""
    if not PROJECT_ID: return None
    url = f"{FIRESTORE_URL}/{collection}/{document_id}"
    response = requests.get(url)
    if response.status_code == 200:
        return parse_firestore_document(response.json())
    return None

def firestore_query(collection, field, op, value):
    """Queries a collection for documents matching a condition."""
    if not PROJECT_ID: return []
    url = f"{FIRESTORE_URL}/{collection}:runQuery"
    query = {
        'structuredQuery': {
            'from': [{'collectionId': collection}],
            'where': {
                'fieldFilter': {
                    'field': {'fieldPath': field},
                    'op': op,
                    'value': {'stringValue': value}
                }
            },
            'limit': 1
        }
    }
    response = requests.post(url, json=query)
    if response.status_code == 200:
        docs = response.json()
        return [parse_firestore_document(doc.get('document', {})) for doc in docs if 'document' in doc]
    return []

def firestore_add_document(collection, data):
    """Adds a new document to a collection."""
    if not PROJECT_ID: return None
    url = f"{FIRESTORE_URL}/{collection}"
    # Firestore REST API expects values to be typed
    payload = { 'fields': format_for_firestore(data) }
    response = requests.post(url, json=payload)
    return response.json() if response.status_code == 200 else None
    
def firestore_delete_document(collection, document_id):
    """Deletes a document."""
    if not PROJECT_ID: return False
    url = f"{FIRESTORE_URL}/{collection}/{document_id}"
    response = requests.delete(url)
    return response.status_code == 200

def parse_firestore_document(doc):
    """Converts a Firestore REST API document into a simple Python dictionary."""
    output = {}
    if 'name' in doc:
        # Extract the document ID from the full path
        output['id'] = doc['name'].split('/')[-1]
    
    fields = doc.get('fields', {})
    for key, value in fields.items():
        # Firestore returns values in a nested dictionary like {'stringValue': '...'}
        # We need to extract the actual value.
        if 'stringValue' in value:
            output[key] = value['stringValue']
        elif 'integerValue' in value:
            output[key] = int(value['integerValue'])
        elif 'timestampValue' in value:
            output[key] = value['timestampValue']
        # Add other types as needed (booleanValue, doubleValue, etc.)
    return output

def format_for_firestore(data):
    """Converts a Python dict to Firestore REST API format."""
    formatted = {}
    for key, value in data.items():
        if isinstance(value, str):
            formatted[key] = {'stringValue': value}
        elif isinstance(value, int):
            formatted[key] = {'integerValue': str(value)}
        # Add other type conversions as needed
    return formatted
    
# --- Utility & Security ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
    
# --- Authentication Routes ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('signup.html')
        
        # Check if user already exists
        existing_users = firestore_query('users', 'username', 'EQUAL', username)
        if existing_users:
            flash('Username already taken.', 'error')
            return render_template('signup.html')
        
        # Create new user
        hashed_password = generate_password_hash(password)
        new_user_data = {
            'username': username,
            'password_hash': hashed_password,
            'role': 'user',
            'profile_pic': 'default.jpg'
        }
        firestore_add_document('users', new_user_data)
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        users = firestore_query('users', 'username', 'EQUAL', username)
        user = users[0] if users else None

        if not user or not check_password_hash(user.get('password_hash', ''), password):
            flash('Invalid username or password.', 'error')
            return render_template('login.html')

        session['user_id'] = user['id']
        session['username'] = user['username']
        session['user_role'] = user.get('role', 'user')
        session['profile_pic'] = user.get('profile_pic', 'default.jpg')
        
        flash('Logged in successfully!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been securely logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/')
def root():
    return redirect(url_for('login') if 'user_id' not in session else url_for('dashboard'))

# --- Main App Routes ---
@app.route('/dashboard')
@login_required
def dashboard():
    # A bit more complex to get all documents without admin library
    url = f"{FIRESTORE_URL}/materials"
    response = requests.get(url)
    materials = []
    if response.status_code == 200:
        docs = response.json().get('documents', [])
        materials = [parse_firestore_document(doc) for doc in docs]
    
    user_data = {
        'username': session.get('username'),
        'profile_pic': session.get('profile_pic')
    }
    return render_template('index.html', user_data=user_data, materials=materials)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_material():
    if request.method == 'POST':
        file = request.files.get('file')
        subject = request.form.get('subject', 'General')
        description = request.form.get('description', '')

        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['MATERIALS_FOLDER'], filename))

            material_data = {
                'uploader_id': session['user_id'],
                'uploader_username': session['username'],
                'filename': filename,
                'subject': subject,
                'description': description,
                'uploaded_at': datetime.utcnow().isoformat() + "Z" # ISO 8601 format for time
            }
            firestore_add_document('materials', material_data)
            flash('File uploaded!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('No file selected.', 'error')

    return render_template('upload.html')
    
@app.route('/details/<material_id>')
@login_required
def details(material_id):
    material = firestore_get_document('materials', material_id)
    if not material:
        flash('Material not found.', 'error')
        return redirect(url_for('dashboard'))
    
    # Query for comments related to this material_id
    # This part is more complex with REST and would require a more advanced query structure.
    # For now, we will return an empty list.
    comments = []
    
    return render_template('details.html', file_item=material, comments=comments)
    
@app.route('/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['MATERIALS_FOLDER'], filename)
    
@app.route('/profile')
@login_required
def profile():
     user_data = firestore_get_document('users', session['user_id'])
     return render_template('profile.html', user_data=user_data)

# --- Startup ---
if __name__ == '__main__':
    os.makedirs(MATERIALS_FOLDER, exist_ok=True)
    os.makedirs(PROFILE_PICS_FOLDER, exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5001)
