import os
import secrets
import time
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, redirect, url_for, session, request, send_from_directory, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

# --- Configuration & Limits ---
# This setup assumes your app.py is in the root project directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PICS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'profile_pics')
MATERIALS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'materials')

app = Flask(__name__)
app.config['PROFILE_PICS_FOLDER'] = PROFILE_PICS_FOLDER
app.config['MATERIALS_FOLDER'] = MATERIALS_FOLDER
app.secret_key = os.environ.get('SECRET_KEY', 'a-super-secret-key-that-you-should-change')

# 15 MB File Size Limit
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024

app.permanent_session_lifetime = timedelta(days=30)

ALLOWED_PIC_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_MATERIAL_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'txt', 'ppt', 'pptx', 'zip', 'rar'}
MAX_COMMENT_LENGTH = 500


# --- Placeholder Database Models ---
# This section simulates a database. We will replace this with Firebase.
class User:
    def __init__(self, id, username, email, role='user', password_hash=None, profile_pic='default.jpg', created_at=None, total_uploads=0, last_login=None):
        self.id = id
        self.username = username
        self.email = email
        self.role = role
        self.password_hash = password_hash or generate_password_hash(secrets.token_urlsafe(12))
        self.profile_pic = profile_pic
        self.created_at = created_at or datetime.now()
        self.total_uploads = total_uploads
        self.last_login = last_login or datetime.now()

    def get_badge(self):
        if self.role == 'admin': return 'Admin'
        if self.total_uploads >= 10: return 'Uploader'
        if (datetime.now() - self.created_at).days > 30: return 'Regular Member'
        return 'New Member'

class File:
    def __init__(self, id, owner_id, filename, stored_name, file_type, likes=0, previewable=False):
        self.id = id
        self.owner_id = owner_id
        self.filename = filename
        self.stored_name = stored_name
        self.file_type = file_type
        self.likes = likes
        self.previewable = previewable

class Comment:
    def __init__(self, id, user_id, material_id, text, parent_id=None, timestamp=None):
        self.id = id
        self.user_id = user_id
        self.material_id = material_id
        self.text = text
        self.parent_id = parent_id
        self.timestamp = timestamp or datetime.now()

# In-Memory Data Store (This will be replaced by Firebase)
USERS = {
    1: User(1, 'admin_user', 'admin@study.com', 'admin', generate_password_hash("adminpass"), total_uploads=15),
    2: User(2, 'regular_user', 'regular@study.com', 'user', generate_password_hash("userpass"), total_uploads=3),
}
FILES = [
    File(101, 1, 'Math Notes.pdf', '1-math-notes.pdf', 'pdf', likes=15, previewable=True),
    File(102, 2, 'History Thesis.docx', '2-thesis.docx', 'docx', likes=5, previewable=False),
]
COMMENTS = [
    Comment(1, 1, 101, "Great notes!", parent_id=None),
    Comment(2, 2, 101, "Thanks!", parent_id=1),
]


# --- Utility & Security Functions ---

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def get_time_of_day():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "Morning"
    elif 12 <= hour < 18: return "Afternoon"
    else: return "Evening"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'admin':
            flash("Access denied. Admin privileges required.", 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# --- Placeholder Database Functions ---

def get_user_by_id(user_id):
    return USERS.get(user_id)

def get_user_by_username(username):
    for user in USERS.values():
        if user.username == username: return user
    return None

def get_file_owner_id(file_id):
    for file in FILES:
        if file.id == file_id: return file.owner_id
    return None

def get_dashboard_stats(user_id):
    user_files = [f for f in FILES if f.owner_id == user_id]
    user_comments = [c for c in COMMENTS if c.user_id == user_id]
    
    return {
        'total_uploads': len(user_files),
        'total_comments': len(user_comments),
        'total_likes': sum(f.likes for f in FILES),
        'new_activity': len([c for c in COMMENTS if c.timestamp > datetime.now() - timedelta(hours=24)])
    }

def get_available_filters():
    return {
        'subjects': ['Math', 'Science', 'History', 'Programming'],
        'types': ['PDF', 'Video', 'Notes', 'Code']
    }
    
def get_comments_for_material(material_id):
    return [c for c in COMMENTS if c.material_id == material_id]

# --- Error Handler ---

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    flash(f"File is too large. Maximum size is {app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024):.0f}MB.", 'error')
    return redirect(request.url)

# --- Authentication Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = get_user_by_username(username)
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password.', 'error')
            return render_template('login.html')

        session['user_id'] = user.id
        session['username'] = user.username
        session['user_role'] = user.role
        session['profile_pic'] = user.profile_pic
        
        flash('Logged in successfully! Welcome.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been securely logged out.', 'success')
    return redirect(url_for('login'))


# --- Main Application Routes ---

@app.route('/')
def root():
    # Redirect root URL to the login page if not logged in, or dashboard if they are.
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = get_user_by_id(session['user_id'])
    
    user_data = {
        'username': user.username,
        'badge': user.get_badge(),
        'role': user.role,
        'profile_pic': session.get('profile_pic', 'default.jpg')
    }
    
    filtered_materials = FILES
    
    return render_template('index.html',
                           user_data=user_data,
                           stat_data=get_dashboard_stats(user.id),
                           time_of_day=get_time_of_day(),
                           filters=get_available_filters(),
                           materials=filtered_materials)

# --- Profile Management ---

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile_settings():
    user = get_user_by_id(session['user_id'])
    
    if request.method == 'POST':
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            
            if file.filename != '' and allowed_file(file.filename, ALLOWED_PIC_EXTENSIONS):
                filename_base = user.username.replace(' ', '_')
                file_ext = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"{filename_base}-{int(time.time())}.{file_ext}")
                
                file.save(os.path.join(app.config['PROFILE_PICS_FOLDER'], filename))
                
                user.profile_pic = filename # Update placeholder DB
                session['profile_pic'] = filename
                flash('Profile picture updated!', 'success')
                return redirect(url_for('profile_settings'))
            else:
                flash('Invalid file type for profile picture.', 'error')

    user_data_display = {
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'profile_pic': session.get('profile_pic', 'default.jpg')
    }
    return render_template('profile.html', user_data=user_data_display)

# --- File Management ---

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_material():
    if request.method == 'POST':
        if 'material_file' in request.files:
            file = request.files['material_file']
            if file.filename != '' and allowed_file(file.filename, ALLOWED_MATERIAL_EXTENSIONS):
                filename = secure_filename(f"{session['username']}-{int(time.time())}-{file.filename}")
                file.save(os.path.join(app.config['MATERIALS_FOLDER'], filename))
                
                flash('Material uploaded successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid file type or no file selected.', 'error')
                
    return render_template('upload.html', allowed_ext=list(ALLOWED_MATERIAL_EXTENSIONS))


@app.route('/preview/<filename>')
@login_required
def preview_file(filename):
    return send_from_directory(app.config['MATERIALS_FOLDER'], filename)

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['MATERIALS_FOLDER'], filename, as_attachment=True)

@app.route('/delete_file/<int:file_id>')
@login_required
def delete_file(file_id):
    owner_id = get_file_owner_id(file_id)
    
    if session.get('user_id') == owner_id or session.get('user_role') == 'admin':
        flash(f'Material successfully deleted.', 'success')
    else:
        flash('Permission denied.', 'error')
        
    return redirect(url_for('dashboard'))

# --- Startup ---
if __name__ == '__main__':
    # Ensure necessary folders exist
    os.makedirs(PROFILE_PICS_FOLDER, exist_ok=True)
    os.makedirs(MATERIALS_FOLDER, exist_ok=True)
    
    app.run(debug=True, host='0.0.0.0', port=5001)
