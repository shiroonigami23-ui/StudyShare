import os
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps

# Import Firebase
import firebase_admin
from firebase_admin import credentials, firestore

from flask import (Flask, render_template, redirect, url_for, session, 
                   request, send_from_directory, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

# --- Firebase Initialization ---
# Make sure 'firebase-credentials.json' is in the same directory as this script
try:
    cred = credentials.Certificate("firebase-credentials.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase connected successfully!")
except Exception as e:
    print(f"Error connecting to Firebase: {e}")
    db = None

# --- Configuration & Limits ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PICS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'profile_pics')
MATERIALS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'materials')

app = Flask(__name__)
app.config['PROFILE_PICS_FOLDER'] = PROFILE_PICS_FOLDER
app.config['MATERIALS_FOLDER'] = MATERIALS_FOLDER
app.secret_key = os.environ.get('SECRET_KEY', 'a-super-secret-key-that-you-should-change')
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024
app.permanent_session_lifetime = timedelta(days=30)

ALLOWED_PIC_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_MATERIAL_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'txt', 'ppt', 'pptx', 'zip', 'rar'}

# --- Utility & Security Functions ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Firebase Database Functions (New) ---

def get_user_by_username(username):
    """Fetches a user from Firestore by their username."""
    if not db: return None
    users_ref = db.collection('users')
    query = users_ref.where('username', '==', username).limit(1).stream()
    for user in query:
        user_data = user.to_dict()
        user_data['id'] = user.id # Attach the document ID
        return user_data
    return None

def get_user_by_id(user_id):
    """Fetches a user from Firestore by their document ID."""
    if not db: return None
    doc_ref = db.collection('users').document(user_id)
    user = doc_ref.get()
    if user.exists:
        user_data = user.to_dict()
        user_data['id'] = user.id
        return user_data
    return None

# --- Authentication Routes (Updated for Firebase) ---

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('signup.html')

        # Check if user already exists
        if get_user_by_username(username):
            flash('Username already taken. Please choose another.', 'error')
            return render_template('signup.html')

        # Create new user document
        hashed_password = generate_password_hash(password)
        new_user_data = {
            'username': username,
            'password_hash': hashed_password,
            'email': '', # You can add an email field to your form
            'role': 'user',
            'profile_pic': 'default.jpg',
            'created_at': firestore.SERVER_TIMESTAMP
        }
        
        # Add to Firestore
        db.collection('users').add(new_user_data)
        flash('Account created successfully! Please log in.', 'success')
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

        # Set session variables
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['user_role'] = user.get('role', 'user')
        session['profile_pic'] = user.get('profile_pic', 'default.jpg')
        
        flash('Logged in successfully! Welcome.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been securely logged out.', 'success')
    return redirect(url_for('login'))

# --- Main Application Routes (Needs Firebase data fetching) ---
# Note: These routes still use placeholder data. We'll update them next.

@app.route('/')
def root():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = get_user_by_id(session['user_id'])
    
    # This data is now coming from Firebase
    user_data = {
        'username': user['username'],
        'badge': 'New Member', # Placeholder, logic needed
        'role': user.get('role', 'user'),
        'profile_pic': session.get('profile_pic', 'default.jpg')
    }
    
    # Placeholder data for now - will be replaced with Firebase queries
    stat_data = {'total_uploads': 0, 'total_likes': 0, 'new_activity': 0, 'total_comments': 0}
    materials = []
    
    return render_template('index.html',
                           user_data=user_data,
                           stat_data=stat_data,
                           materials=materials,
                           time_of_day="Morning") # Placeholder

# --- Other routes remain the same for now ---

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile_settings():
    user = get_user_by_id(session['user_id'])
    return render_template('profile.html', user_data=user)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_material():
    return render_template('upload.html', allowed_ext=list(ALLOWED_MATERIAL_EXTENSIONS))

@app.route('/preview/<filename>')
@login_required
def preview_file(filename):
    return send_from_directory(app.config['MATERIALS_FOLDER'], filename)

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['MATERIALS_FOLDER'], filename, as_attachment=True)


# --- Startup ---
if __name__ == '__main__':
    os.makedirs(PROFILE_PICS_FOLDER, exist_ok=True)
    os.makedirs(MATERIALS_FOLDER, exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5001)
