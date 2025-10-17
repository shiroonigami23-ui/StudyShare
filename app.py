import os
import secrets
import json
from datetime import datetime
from functools import wraps

import requests
from flask import (Flask, render_template, redirect, url_for, session, 
                   request, send_from_directory, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --- Firebase Configuration ---
try:
    with open('firebase-credentials.json') as f:
        firebase_credentials = json.load(f)
    PROJECT_ID = firebase_credentials.get('project_id')
    print(f"SUCCESS: Loaded Firebase Project ID: {PROJECT_ID}")
except Exception as e:
    PROJECT_ID = None
    print(f"CRITICAL ERROR: Could not load or parse firebase-credentials.json: {e}")

BASE_FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

# --- App Configuration ---
# PythonAnywhere uses a different directory structure, so we get the base path this way
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MATERIALS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'materials')
PROFILE_PICS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'profile_pics')

app = Flask(__name__)
app.config['MATERIALS_FOLDER'] = MATERIALS_FOLDER
app.config['PROFILE_PICS_FOLDER'] = PROFILE_PICS_FOLDER
app.secret_key = os.environ.get('SECRET_KEY', 'a-very-secret-and-random-key-for-sessions')
ALLOWED_PIC_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# --- All Helper functions, routes, etc. remain the same as the 'Final Networking Fix' version ---
# ... (The rest of the code is identical to the last working version you had)
# --- Helper Functions for Firestore REST API ---

def firestore_request(method, url, **kwargs):
    if not PROJECT_ID:
        print("Firestore request failed: Project ID is not configured.")
        return None
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        print(f"Error during Firestore request to {url}: {e}")
        print(f"Response Body: {response.text if 'response' in locals() else 'No response'}")
        return None

def parse_firestore_document(doc):
    output = {}
    if 'name' in doc:
        output['id'] = doc['name'].split('/')[-1]
    
    fields = doc.get('fields', {})
    for key, value in fields.items():
        if 'stringValue' in value:
            output[key] = value['stringValue']
        elif 'integerValue' in value:
            output[key] = int(value['integerValue'])
        elif 'timestampValue' in value:
            output[key] = value['timestampValue']
    return output

def format_for_firestore(data):
    formatted = {}
    for key, value in data.items():
        if isinstance(value, str):
            formatted[key] = {'stringValue': value}
        elif isinstance(value, int):
            formatted[key] = {'integerValue': str(value)}
    return formatted

def firestore_query(collection, field, op, value):
    url = f"{BASE_FIRESTORE_URL}:runQuery"
    query_body = {
        'structuredQuery': {
            'from': [{'collectionId': collection}],
            'where': { 'fieldFilter': { 'field': {'fieldPath': field}, 'op': op, 'value': {'stringValue': value} } }
        }
    }
    parent_path = f"projects/{PROJECT_ID}/databases/(default)/documents"
    response = firestore_request('POST', url, json={'structuredQuery': query_body['structuredQuery'], 'parent': parent_path})

    if response:
        docs = response.json()
        return [parse_firestore_document(doc.get('document', {})) for doc in docs if 'document' in doc]
    return []

def firestore_add_document(collection, data):
    url = f"{BASE_FIRESTORE_URL}/{collection}"
    payload = {'fields': format_for_firestore(data)}
    response = firestore_request('POST', url, json=payload)
    return response.json() if response else None

def firestore_get_document(path):
    url = f"{BASE_FIRESTORE_URL}/{path}"
    response = firestore_request('GET', url)
    return parse_firestore_document(response.json()) if response else None

def firestore_delete_document(path):
    url = f"{BASE_FIRESTORE_URL}/{path}"
    response = firestore_request('DELETE', url)
    return response is not None

def firestore_update_document(path, data):
    url = f"{BASE_FIRESTORE_URL}/{path}"
    payload = {'fields': format_for_firestore(data)}
    response = firestore_request('PATCH', url, json=payload)
    return response.json() if response else None

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

# --- Login Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---
@app.route('/')
def root():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))
    
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Username and password are required.', 'error'); return render_template('signup.html')
        
        if firestore_query('users', 'username', 'EQUAL', username):
            flash('Username already exists.', 'error'); return render_template('signup.html')
        
        all_users_url = f"{BASE_FIRESTORE_URL}/users?pageSize=1"
        response = firestore_request('GET', all_users_url)
        is_first_user = not response or not response.json().get('documents')
        role = 'admin' if is_first_user else 'user'
        
        hashed_password = generate_password_hash(password)
        new_user_data = {
            'username': username,
            'password_hash': hashed_password,
            'role': role,
            'profile_pic': 'default.jpg'
        }
        firestore_add_document('users', new_user_data)
        flash(f'Account created! You are an {role}. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
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

@app.route('/dashboard')
@login_required
def dashboard():
    url = f"{BASE_FIRESTORE_URL}/materials"
    response = firestore_request('GET', url)
    materials = []
    if response and 'documents' in response.json():
        materials = [parse_firestore_document(doc) for doc in response.json().get('documents', [])]
    
    user_data = {
        'username': session.get('username'),
        'profile_pic': session.get('profile_pic')
    }
    return render_template('index.html', user_data=user_data, materials=materials, current_user_id=session['user_id'], user_role=session['user_role'])

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_material():
    if request.method == 'POST':
        file = request.files.get('file')
        subject = request.form.get('subject', 'General')
        description = request.form.get('description', '')

        if file and file.filename:
            filename = secure_filename(file.filename)
            # Ensure the directory exists
            os.makedirs(app.config['MATERIALS_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['MATERIALS_FOLDER'], filename))

            material_data = {
                'uploader_id': session['user_id'],
                'uploader_username': session['username'],
                'filename': filename,
                'subject': subject,
                'description': description,
                'uploaded_at': datetime.utcnow().isoformat() + "Z"
            }
            firestore_add_document('materials', material_data)
            flash('File uploaded!', 'success')
            return redirect(url_for('dashboard'))
    return render_template('upload.html')

@app.route('/delete_file/<material_id>')
@login_required
def delete_file(material_id):
    material = firestore_get_document(f'materials/{material_id}')
    
    if material and (material.get('uploader_id') == session['user_id'] or session.get('user_role') == 'admin'):
        firestore_delete_document(f'materials/{material_id}')
        try:
            os.remove(os.path.join(app.config['MATERIALS_FOLDER'], material['filename']))
        except OSError as e:
            print(f"Error removing file from disk: {e}")
        flash('File deleted.', 'success')
    else:
        flash('You do not have permission to delete this file.', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        file = request.files.get('profile_pic')
        if file and allowed_file(file.filename, ALLOWED_PIC_EXTENSIONS):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{session['user_id']}.{ext}"
            
            os.makedirs(app.config['PROFILE_PICS_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['PROFILE_PICS_FOLDER'], filename))
            
            firestore_update_document(f"users/{session['user_id']}", {'profile_pic': filename})
            
            session['profile_pic'] = filename
            flash('Profile picture updated!', 'success')
            return redirect(url_for('profile'))
        else:
            flash('Invalid file type for profile picture.', 'error')

    user_data = firestore_get_document(f"users/{session['user_id']}")
    return render_template('profile.html', user_data=user_data)

@app.route('/uploads/profile_pics/<filename>')
def serve_profile_pic(filename):
    return send_from_directory(app.config['PROFILE_PICS_FOLDER'], filename)

@app.route('/uploads/materials/<filename>')
def serve_material(filename):
    return send_from_directory(app.config['MATERIALS_FOLDER'], filename)
