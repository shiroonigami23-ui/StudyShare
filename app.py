import os
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps

import firebase_admin
from firebase_admin import credentials, firestore

from flask import (Flask, render_template, redirect, url_for, session, 
                   request, send_from_directory, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --- Firebase Initialization (Database Only) ---
try:
    cred = credentials.Certificate("firebase-credentials.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Firestore connected successfully!")
except Exception as e:
    print(f"Error connecting to Firebase: {e}")
    db = None

# --- Configuration (Using Local Folders for Uploads) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MATERIALS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'materials')
PROFILE_PICS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'profile_pics')

app = Flask(__name__)
app.config['MATERIALS_FOLDER'] = MATERIALS_FOLDER
app.config['PROFILE_PICS_FOLDER'] = PROFILE_PICS_FOLDER
app.secret_key = 'a-super-secret-key-that-you-should-change'

# --- Utility & Security Functions ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Firebase Database Functions ---
def get_user_by_username(username):
    if not db: return None
    users_ref = db.collection('users')
    query = users_ref.where('username', '==', username).limit(1).stream()
    for user in query:
        user_data = user.to_dict()
        user_data['id'] = user.id
        return user_data
    return None

def get_user_by_id(user_id):
    if not db: return None
    doc_ref = db.collection('users').document(user_id)
    user = doc_ref.get()
    if user.exists:
        user_data = user.to_dict()
        user_data['id'] = user.id
        return user_data
    return None

# --- Authentication Routes are unchanged ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('signup.html')
        if get_user_by_username(username):
            flash('Username already taken.', 'error')
            return render_template('signup.html')
        hashed_password = generate_password_hash(password)
        new_user_data = { 'username': username, 'password_hash': hashed_password, 'role': 'user', 'profile_pic': 'default.jpg', 'created_at': firestore.SERVER_TIMESTAMP }
        db.collection('users').add(new_user_data)
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = get_user_by_username(username)
        if not user or not check_password_hash(user['password_hash'], password):
            flash('Invalid username or password.', 'error')
            return render_template('login.html')
        session.update({'user_id': user['id'], 'username': user['username'], 'user_role': user.get('role', 'user'), 'profile_pic': user.get('profile_pic', 'default.jpg')})
        flash('Logged in successfully!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been securely logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/')
def root():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))
    
# --- Main Dashboard ---
@app.route('/dashboard')
@login_required
def dashboard():
    user = get_user_by_id(session['user_id'])
    user_data = { 'username': user['username'], 'profile_pic': session.get('profile_pic', 'default.jpg') }
    
    materials = []
    materials_ref = db.collection('materials').order_by('uploaded_at', direction=firestore.Query.DESCENDING).stream()
    for material in materials_ref:
        mat_data = material.to_dict()
        mat_data['id'] = material.id
        materials.append(mat_data)

    return render_template('index.html', user_data=user_data, materials=materials)

# --- File Management (Local Storage) ---
@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_material():
    if request.method == 'POST':
        file = request.files.get('file')
        subject = request.form.get('subject', 'General').strip()
        description = request.form.get('description', '').strip()

        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['MATERIALS_FOLDER'], filename))

            material_data = {
                'uploader_id': session['user_id'], 'uploader_username': session['username'],
                'filename': filename, 'subject': subject, 'description': description,
                'uploaded_at': firestore.SERVER_TIMESTAMP
            }
            db.collection('materials').add(material_data)
            flash('File uploaded successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('No file selected.', 'error')

    return render_template('upload.html')

@app.route('/uploads/materials/<filename>')
@login_required
def serve_material(filename):
    return send_from_directory(app.config['MATERIALS_FOLDER'], filename)

@app.route('/delete_file/<material_id>')
@login_required
def delete_file(material_id):
    material_ref = db.collection('materials').document(material_id)
    material = material_ref.get().to_dict()

    if material and (material['uploader_id'] == session['user_id'] or session.get('user_role') == 'admin'):
        material_ref.delete()
        try:
            os.remove(os.path.join(app.config['MATERIALS_FOLDER'], material['filename']))
        except OSError as e:
            print(f"Error deleting file from local storage: {e}")
        flash(f"'{material['filename']}' deleted.", 'success')
    else:
        flash("You don't have permission to delete this file.", "error")
        
    return redirect(url_for('dashboard'))

# ### NEW ### Details and Comments Routes
@app.route('/details/<material_id>')
@login_required
def details(material_id):
    # Fetch the material document from Firestore
    material_ref = db.collection('materials').document(material_id)
    material_doc = material_ref.get()

    if not material_doc.exists:
        flash("Material not found.", "error")
        return redirect(url_for('dashboard'))

    material = material_doc.to_dict()
    material['id'] = material_doc.id

    # Fetch comments for this material
    comments = []
    comments_ref = db.collection('comments').where('material_id', '==', material_id).order_by('timestamp', direction=firestore.Query.ASCENDING).stream()
    for comment in comments_ref:
        comments.append(comment.to_dict())
        
    return render_template('details.html', file_item=material, comments=comments)


@app.route('/add_comment/<material_id>', methods=['POST'])
@login_required
def add_comment(material_id):
    comment_text = request.form.get('comment_text', '').strip()
    if not comment_text:
        flash("Comment cannot be empty.", "error")
        return redirect(url_for('details', material_id=material_id))

    comment_data = {
        'material_id': material_id,
        'user_id': session['user_id'],
        'username': session['username'],
        'text': comment_text,
        'timestamp': firestore.SERVER_TIMESTAMP
    }
    db.collection('comments').add(comment_data)
    
    return redirect(url_for('details', material_id=material_id))

# --- Startup ---
if __name__ == '__main__':
    os.makedirs(MATERIALS_FOLDER, exist_ok=True)
    os.makedirs(PROFILE_PICS_FOLDER, exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5001)
