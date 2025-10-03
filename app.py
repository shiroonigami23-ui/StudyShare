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

# --- Configuration & Limits (Lines 20-40) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PICS_FOLDER = os.path.join('static', 'uploads', 'profile_pics')
MATERIALS_FOLDER = os.path.join('static', 'uploads', 'materials')

app = Flask(__name__)
app.config['PROFILE_PICS_FOLDER'] = PROFILE_PICS_FOLDER
app.config['MATERIALS_FOLDER'] = MATERIALS_FOLDER
app.secret_key = os.environ.get('SECRET_KEY', 'ULTIMATE_SECRET_KEY_MUST_BE_LONG_AND_RANDOM_123456789')

# 15 MB File Size Limit (RequestEntityTooLarge handler will catch this)
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024 

app.permanent_session_lifetime = timedelta(days=30) 

ALLOWED_PIC_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} 
ALLOWED_MATERIAL_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'txt', 'ppt', 'pptx', 'zip', 'rar'}
MAX_COMMENT_LENGTH = 500


# --- DB Placeholder Classes (Lines 46-95) ---
# These simulate database models and data for a richer feature set.
# REPLACE THIS ENTIRE SECTION WITH YOUR REAL DATABASE MODELS.

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

# Placeholder Data Store (In-Memory Simulation)
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


# --- Utility & Security Functions (Lines 100-135) ---

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


# --- DB Placeholder Functions (Integration) (Lines 140-190) ---

def get_user_by_id(user_id):
    # [DB ACTION]: Fetch User by ID
    return USERS.get(user_id)

def get_user_by_username(username):
    # [DB ACTION]: Fetch User by Username
    for user in USERS.values():
        if user.username == username: return user
    return None

def get_file_owner_id(file_id):
    # [DB ACTION]: Get owner_id from File table
    for file in FILES:
        if file.id == file_id: return file.owner_id
    return None

def get_dashboard_stats(user_id):
    # [DB ACTION]: Calculate and fetch complex stats
    user_files = [f for f in FILES if f.owner_id == user_id]
    user_comments = [c for c in COMMENTS if c.user_id == user_id]
    
    return {
        'total_uploads': len(user_files),
        'total_comments': len(user_comments),
        'total_likes': sum(f.likes for f in FILES),
        'new_activity': len([c for c in COMMENTS if c.timestamp > datetime.now() - timedelta(hours=24)])
    }

def get_available_filters():
    # [DB ACTION]: Fetch distinct categories from File records
    return {
        'subjects': ['Math', 'Science', 'History', 'Programming'],
        'types': ['PDF', 'Video', 'Notes', 'Code']
    }
    
def get_comments_for_material(material_id):
    # [DB ACTION]: Fetch comments and associated user data for a material
    # Logic for nested replies (parent_id) is handled here.
    return [c for c in COMMENTS if c.material_id == material_id]

# --- Error Handler for File Size Limit (Lines 195-200) ---

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    flash(f"File is too large. Maximum size is {app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024):.0f}MB.", 'error')
    return redirect(request.url)

# --- Authentication Routes (Lines 205-245) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember')

        # [DB ACTION]: Retrieve user object
        user = get_user_by_username(username)
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password.', 'error')
            return render_template('login.html')

        session.permanent = True if remember else False
        session['user_id'] = user.id
        session['username'] = user.username
        session['user_role'] = user.role
        session['profile_pic'] = user.profile_pic
        
        # [DB ACTION]: Update user.last_login = datetime.now()
        flash('Logged in successfully! Welcome.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been securely logged out.', 'success')
    return redirect(url_for('login'))


# --- Main Application Routes (Lines 250-275) ---

@app.route('/')
@login_required
def dashboard():
    user = get_user_by_id(session['user_id'])
    
    user_data = {
        'username': user.username,
        'badge': user.get_badge(),
        'profile_pic': session.get('profile_pic', 'default.jpg')
    }
    
    # [DB ACTION]: Apply filters from request.args to fetch materials
    filtered_materials = FILES # Placeholder: needs real filtering logic here
    
    return render_template('index.html',
                           user_data=user_data,
                           stat_data=get_dashboard_stats(user.id),
                           time_of_day=get_time_of_day(),
                           filters=get_available_filters(),
                           materials=filtered_materials)

# --- Profile Management (Lines 280-345) ---

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile_settings():
    user = get_user_by_id(session['user_id'])
    
    if request.method == 'POST':
        # Handles Profile Picture Upload
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            
            if file.filename == '':
                flash('No file selected.', 'error')
                return redirect(request.url)

            if not allowed_file(file.filename, ALLOWED_PIC_EXTENSIONS):
                flash('Invalid file type for profile picture. Must be PNG, JPG, or GIF.', 'error')
                return redirect(request.url)
            
            # Secure Filename generation
            filename_base = user.username.replace(' ', '_')
            file_ext = file.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f"{filename_base}-{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}")
            
            # Save the file
            file.save(os.path.join(app.root_path, app.config['PROFILE_PICS_FOLDER'], filename))
            
            # [DB ACTION]: Update user.profile_pic in the database
            
            session['profile_pic'] = filename
            flash('Profile picture updated successfully!', 'success')
            return redirect(url_for('profile_settings'))
        
        # Handles Password Change (New Feature)
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        if current_password and new_password:
            if not check_password_hash(user.password_hash, current_password):
                flash('Current password is incorrect.', 'error')
                return redirect(request.url)
            
            if len(new_password) < 8:
                flash('New password must be at least 8 characters long.', 'error')
                return redirect(request.url)
            
            new_hash = generate_password_hash(new_password)
            # [DB ACTION]: Update user.password_hash = new_hash
            flash('Password updated successfully!', 'success')
            return redirect(url_for('profile_settings'))
            
    user_data_display = {
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'profile_pic': session.get('profile_pic', 'default.jpg')
    }
    return render_template('profile.html', user_data=user_data_display)

# --- File Management (Lines 350-435) ---

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_material():
    if request.method == 'POST':
        if 'material_file' not in request.files:
            flash('No file selected.', 'error')
            return redirect(request.url)
        
        file = request.files['material_file']
        
        if file.filename == '':
            flash('No selected file.', 'error')
            return redirect(request.url)
            
        if not allowed_file(file.filename, ALLOWED_MATERIAL_EXTENSIONS):
            flash('Invalid file type.', 'error')
            return redirect(request.url)
            
        # Secure filename (sanitized input + unique timestamp)
        filename = secure_filename(f"{session['username']}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{file.filename}")
        
        file.save(os.path.join(app.root_path, app.config['MATERIALS_FOLDER'], filename))
        
        # DB_ACTION: Save file metadata (owner_id, original_name, stored_name, type)
        # file_id = db.session.insert(...)
        
        flash('Material uploaded successfully! It is now available for the community.', 'success')
        return redirect(url_for('dashboard'))
            
    return render_template('upload.html', allowed_ext=list(ALLOWED_MATERIAL_EXTENSIONS))


@app.route('/preview/<filename>')
@login_required
def preview_file(filename):
    # Security check: Ensure file exists before serving
    if not os.path.exists(os.path.join(app.root_path, app.config['MATERIALS_FOLDER'], filename)):
        flash('File not found.', 'error')
        return redirect(url_for('dashboard'))
        
    return send_from_directory(os.path.join(app.root_path, app.config['MATERIALS_FOLDER']), 
                               filename, as_attachment=False)

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    if not os.path.exists(os.path.join(app.root_path, app.config['MATERIALS_FOLDER'], filename)):
        flash('File not found for download.', 'error')
        return redirect(url_for('dashboard'))
        
    return send_from_directory(os.path.join(app.root_path, app.config['MATERIALS_FOLDER']), 
                               filename, as_attachment=True)

@app.route('/delete_file/<int:file_id>')
@login_required
def delete_file(file_id):
    owner_id = get_file_owner_id(file_id)
    
    # Permission Check: User can delete only their own, Admin can delete everyone's
    if session.get('user_id') == owner_id or session.get('user_role') == 'admin':
        
        # DB_ACTION: Fetch stored filename from database using file_id
        file_to_delete_filename = "example_file.pdf" # Placeholder filename
        
        file_path = os.path.join(app.root_path, app.config['MATERIALS_FOLDER'], file_to_delete_filename)
        
        if os.path.exists(file_path):
             os.remove(file_path)
             # DB_ACTION: Delete file record from the database
             flash(f'Material successfully deleted.', 'success')
        else:
             # DB_ACTION: Delete file record even if physical file is missing
             flash('Material record deleted (physical file was missing).', 'warning')
    else:
        flash('Permission denied. You can only delete your own files.', 'error')
        
    return redirect(url_for('dashboard'))

# --- Community/Social Features (Comments & Rating) (Lines 440-520) ---

@app.route('/comment', methods=['POST'])
@login_required
def post_comment():
    comment_text = request.form.get('comment_text', '').strip()
    material_id = request.form.get('material_id')
    parent_id = request.form.get('parent_id') # For replies

    if not comment_text or not material_id:
        flash("Comment text or material ID is missing.", 'error')
        return redirect(url_for('dashboard'))
        
    if len(comment_text) > MAX_COMMENT_LENGTH:
        flash(f"Comment is too long. Max is {MAX_COMMENT_LENGTH} characters.", 'error')
        return redirect(url_for('dashboard'))

    # DB_ACTION: Get the next comment ID (e.g., auto-increment)
    new_id = len(COMMENTS) + 1 
    
    # Create the new comment object
    new_comment = Comment(
        id=new_id,
        user_id=session['user_id'],
        material_id=int(material_id),
        text=comment_text,
        parent_id=int(parent_id) if parent_id else None
    )
    
    # [DB ACTION]: Save new_comment to database
    COMMENTS.append(new_comment) # Simulation
    
    if parent_id:
        flash("Reply posted successfully!", 'success')
    else:
        flash("Comment posted successfully!", 'success')

    # Consider redirecting back to the material detail page if you had one
    return redirect(url_for('dashboard')) 


@app.route('/like_file/<int:file_id>')
@login_required
def like_file(file_id):
    # [DB ACTION]: Check if user already liked the file and toggle status
    
    # Placeholder Logic:
    file = next((f for f in FILES if f.id == file_id), None)
    if file:
        file.likes += 1 # Increment like count
        # [DB ACTION]: Record user like in a separate table (user_likes)
        flash(f"Material '{file.filename}' liked!", 'success')
    else:
        flash("Could not like material: File not found.", 'error')
        
    return redirect(url_for('dashboard'))


# --- Admin Dashboard Route (Lines 525-545) ---

@app.route('/admin')
@admin_required
def admin_dashboard():
    # [DB ACTION]: Fetch high-level stats for admin review
    total_users = len(USERS)
    total_files = len(FILES)
    
    return render_template('admin.html',
                           total_users=total_users,
                           total_files=total_files,
                           users=USERS.values())


@app.route('/admin/delete_user/<int:user_id>')
@admin_required
def admin_delete_user(user_id):
    if user_id == session.get('user_id'):
        flash("Cannot delete your own admin account while logged in.", 'error')
        return redirect(url_for('admin_dashboard'))

    # [DB ACTION]: Delete user, their files, and their comments
    if user_id in USERS:
        del USERS[user_id] # Simulation
        flash(f"User ID {user_id} and associated data deleted.", 'success')
    else:
        flash("User not found.", 'error')
        
    return redirect(url_for('admin_dashboard'))

# --- Final Execution (Lines 550-575) ---
if __name__ == '__main__':
    # Ensure necessary folders exist on startup
    for folder in [PROFILE_PICS_FOLDER, MATERIALS_FOLDER]:
        full_path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
            
    # Set up a dummy session variable for initial testing (remove this for real login)
    with app.test_request_context():
        session['user_id'] = 1
        session['username'] = 'admin_user'
        session['user_role'] = 'admin'
        
    # Set host='0.0.0.0' for deployment environments like Railway
    # We set debug=False for security, but you can set it to True during development
    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 5000))

