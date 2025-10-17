import os
import secrets
import json
from datetime import datetime
from functools import wraps
from collections import defaultdict

import requests
from flask import (Flask, render_template, redirect, url_for, session, 
                   request, send_from_directory, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --- Firebase Configuration ---
CREDENTIALS_PATH = '/home/shiroonigami23/firebase-credentials.json'
try:
    with open(CREDENTIALS_PATH) as f:
        firebase_credentials = json.load(f)
    PROJECT_ID = firebase_credentials.get('project_id')
    print(f"SUCCESS: Loaded Firebase Project ID: {PROJECT_ID}")
except Exception as e:
    PROJECT_ID = None
    print(f"CRITICAL ERROR: Could not load or parse firebase-credentials.json from {CREDENTIALS_PATH}: {e}")

BASE_FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

# --- App Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MATERIALS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'materials')
PROFILE_PICS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'profile_pics')

app = Flask(__name__)
app.config['MATERIALS_FOLDER'] = MATERIALS_FOLDER
app.config['PROFILE_PICS_FOLDER'] = PROFILE_PICS_FOLDER
app.secret_key = os.environ.get('SECRET_KEY', 'a-very-secret-and-random-key-for-sessions')
ALLOWED_PIC_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# --- Helper Functions for Firestore ---
def firestore_request(method, url, **kwargs):
    if not PROJECT_ID: return None
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        print(f"Error during Firestore request to {url}: {e}")
        if 'response' in locals(): print(f"Response Body: {response.text}")
        return None

def parse_firestore_document(doc):
    output = {}
    if 'name' in doc: output['id'] = doc['name'].split('/')[-1]
    fields = doc.get('fields', {})
    for key, value in fields.items():
        if 'stringValue' in value: output[key] = value['stringValue']
        elif 'integerValue' in value: output[key] = int(value['integerValue'])
        elif 'timestampValue' in value: output[key] = value['timestampValue']
    return output

def format_for_firestore(data):
    formatted = {}
    for key, value in data.items():
        if isinstance(value, str): formatted[key] = {'stringValue': value}
        elif isinstance(value, int): formatted[key] = {'integerValue': str(value)}
    return formatted
    
def firestore_query(collection, field, op, value):
    url = f"https://firestore.googleapis.com/v1/{BASE_FIRESTORE_URL.split('/v1/')[1]}:runQuery"
    query_body = {'structuredQuery': {'from': [{'collectionId': collection}],'where': { 'fieldFilter': { 'field': {'fieldPath': field}, 'op': op, 'value': {'stringValue': value} } }}}
    response = firestore_request('POST', url, json=query_body)
    if response:
        docs = response.json()
        return [parse_firestore_document(doc.get('document', {})) for doc in docs if 'document' in doc]
    return []

def firestore_add_document(collection, data):
    url = f"https://{BASE_FIRESTORE_URL.split('https://')[1]}/{collection}"
    payload = {'fields': format_for_firestore(data)}
    response = firestore_request('POST', url, json=payload)
    return response.json() if response else None

def firestore_get_document(path):
    url = f"https://{BASE_FIRESTORE_URL.split('https://')[1]}/{path}"
    response = firestore_request('GET', url)
    return parse_firestore_document(response.json()) if response else None

def firestore_delete_document(path):
    url = f"https://{BASE_FIRESTORE_URL.split('https://')[1]}/{path}"
    response = firestore_request('DELETE', url)
    return response is not None

def firestore_update_document(path, data):
    url = f"https://{BASE_FIRESTORE_URL.split('https://')[1]}/{path}"
    payload = {'fields': format_for_firestore(data)}
    response = firestore_request('PATCH', url, json=payload)
    return response.json() if response else None

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

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
    return redirect(url_for('login') if 'user_id' not in session else url_for('dashboard'))
    
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Username and password are required.', 'error'); return render_template('signup.html')
        if firestore_query('users', 'username', 'EQUAL', username):
            flash('Username already exists.', 'error'); return render_template('signup.html')
        
        all_users_url = f"https://{BASE_FIRESTORE_URL.split('https://')[1]}/users?pageSize=1"
        response = firestore_request('GET', all_users_url)
        is_first_user = not response or not response.json().get('documents')
        role = 'admin' if is_first_user else 'user'
        
        new_user_data = {'username': username, 'password_hash': generate_password_hash(password), 'role': role, 'profile_pic': 'default.jpg'}
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

        session.update(user_id=user['id'], username=user['username'], user_role=user.get('role', 'user'), profile_pic=user.get('profile_pic', 'default.jpg'))
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
    search_term = request.args.get('search', '').lower()
    subject_filter = request.args.get('subject', '').lower()

    # Fetch and filter materials
    materials_url = f"https://{BASE_FIRESTORE_URL.split('https://')[1]}/materials"
    materials_response = firestore_request('GET', materials_url)
    all_materials = [parse_firestore_document(doc) for doc in materials_response.json().get('documents', [])] if materials_response else []
    filtered_materials = [m for m in all_materials if (not search_term or search_term in m.get('filename', '').lower()) and (not subject_filter or subject_filter in m.get('subject', '').lower())]

    # Fetch and structure shoutbox messages
    shoutbox_url = f"https://{BASE_FIRESTORE_URL.split('https://')[1]}/shoutbox"
    shoutbox_response = firestore_request('GET', shoutbox_url)
    all_messages = [parse_firestore_document(doc) for doc in shoutbox_response.json().get('documents', [])] if shoutbox_response else []
    all_messages.sort(key=lambda x: x.get('timestamp', ''))

    # Organize messages into threads
    message_map = {msg['id']: msg for msg in all_messages}
    threaded_messages = defaultdict(list)
    root_messages = []
    for msg in all_messages:
        parent_id = msg.get('parent_id')
        if parent_id and parent_id in message_map:
            threaded_messages[parent_id].append(msg)
        else:
            root_messages.append(msg)

    user_data = firestore_get_document(f"users/{session['user_id']}")
    return render_template('index.html', user_data=user_data, materials=filtered_materials, messages=root_messages, replies=threaded_messages, current_user_id=session['user_id'], user_role=session.get('user_role', 'user'), search_term=request.args.get('search', ''), subject_filter=request.args.get('subject', ''))

@app.route('/shout', methods=['POST'])
@login_required
def post_shout():
    text = request.form.get('text', '').strip()
    parent_id = request.form.get('parent_id') # New field for replies
    if text:
        message_data = {'username': session['username'], 'text': text, 'timestamp': datetime.utcnow().isoformat() + "Z"}
        if parent_id: message_data['parent_id'] = parent_id
        firestore_add_document('shoutbox', message_data)
    return redirect(url_for('dashboard'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_material():
    if request.method == 'POST':
        file, subject = request.files.get('file'), request.form.get('subject', 'General').strip()
        if file and file.filename and subject:
            filename = secure_filename(file.filename)
            os.makedirs(app.config['MATERIALS_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['MATERIALS_FOLDER'], filename))
            material_data = {'uploader_id': session['user_id'], 'uploader_username': session['username'], 'filename': filename, 'subject': subject, 'description': request.form.get('description', '').strip(), 'uploaded_at': datetime.utcnow().isoformat() + "Z"}
            firestore_add_document('materials', material_data)
            flash('File uploaded!', 'success')
        else:
            flash('File and subject are required.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('upload.html')

@app.route('/delete_file/<material_id>')
@login_required
def delete_file(material_id):
    material = firestore_get_document(f'materials/{material_id}')
    if material and (material.get('uploader_id') == session['user_id'] or session.get('user_role') == 'admin'):
        firestore_delete_document(f'materials/{material_id}')
        try: os.remove(os.path.join(app.config['MATERIALS_FOLDER'], material['filename']))
        except OSError as e: print(f"Error removing file from disk: {e}")
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
