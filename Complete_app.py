import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from sqlalchemy import desc, func

# --- 1. CONFIGURATION AND SETUP ---
app = Flask(__name__)

# Basic app configuration
app.config['SECRET_KEY'] = 'YOUR_SUPER_SECURE_SECRET_KEY_12345' # **CHANGE THIS!**
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///studyshare.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration (25 MB limit)
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'jpg', 'jpeg', 'png', 'gif'} # Added gif

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' 
login_manager.login_message = 'Please log in to access this page.'

# Ensure the upload and static folders exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists('static'):
    os.makedirs('static')


# --- 2. DATABASE MODELS (Tables) ---

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    profile_pic = db.Column(db.String(256), default='default.png')
    badges = db.Column(db.String(256), default='New Member')
    login_count = db.Column(db.Integer, default=0) # For 'Regular Visitor' badge
    upload_count = db.Column(db.Integer, default=0) # For 'Uploader' badge
    is_admin = db.Column(db.Boolean, default=False)
    
    files = db.relationship('File', backref='uploader', lazy=True, cascade="all, delete-orphan")
    comments = db.relationship('Comment', backref='author', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

def allowed_file(filename):
    """Checks if a file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(256), unique=True, nullable=False)
    description = db.Column(db.String(500), nullable=True)
    subject = db.Column(db.String(100), nullable=False)
    file_type = db.Column(db.String(20), nullable=False) 
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    comments = db.relationship('Comment', backref='file_item', lazy=True, cascade="all, delete-orphan")

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file_id = db.Column(db.Integer, db.ForeignKey('file.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    text = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy=True)


# --- 3. FLASK-LOGIN REQUIREMENTS & UTILITIES ---

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def update_badges(user):
    """Simple logic to update user badges."""
    badges = set(user.badges.split(','))
    
    if user.login_count >= 5 and 'Regular Visitor' not in badges:
        badges.add('Regular Visitor')
    
    if user.upload_count >= 3 and 'Uploader' not in badges:
        badges.add('Uploader')
        
    user.badges = ','.join(b.strip() for b in badges if b.strip())
    db.session.commit()


# --- 4. AUTHENTICATION ROUTES ---

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    # ... (Keep the signup logic from the previous step)
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_exists = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
        
        if user_exists:
            flash('That username is already taken. Please choose another.', 'danger')
            return redirect(url_for('signup'))
            
        new_user = User(username=username)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        # Optional: Make the first user an admin for easy testing
        if db.session.query(func.count(User.id)).scalar() == 1:
             new_user.is_admin = True
             db.session.commit()
        
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    # ... (Keep the login logic from the previous step, adding badge update)
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()

        if user and user.check_password(password):
            login_user(user, remember=True)
            
            # Update login count and badges
            user.login_count += 1
            update_badges(user)
            
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# --- 5. CORE FUNCTIONALITY ROUTES ---

@app.route('/', methods=['GET', 'POST'])
@login_required
def dashboard():
    """Main dashboard: displays files with filtering options."""
    
    # Get all unique subjects and file types for filter dropdowns
    subjects = db.session.query(File.subject).distinct().all()
    file_types = db.session.query(File.file_type).distinct().all()
    
    query = db.select(File).order_by(desc(File.upload_date))
    
    # Filtering logic
    subject_filter = request.args.get('subject')
    type_filter = request.args.get('file_type')
    search_term = request.args.get('search')
    
    if subject_filter:
        query = query.filter(File.subject == subject_filter)
    if type_filter:
        query = query.filter(File.file_type == type_filter)
    if search_term:
        # Simple search across filename and description
        query = query.filter(
            (File.filename.ilike(f'%{search_term}%')) | 
            (File.description.ilike(f'%{search_term}%'))
        )
        
    files = db.session.execute(query).scalars().all()
        
    return render_template('index.html', 
                           files=files, 
                           subjects=[s[0] for s in subjects], 
                           file_types=[t[0] for t in file_types],
                           # Pass back current filters to pre-select dropdowns
                           current_subject=subject_filter,
                           current_type=type_filter,
                           current_search=search_term)


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    """Handles file upload form and logic."""
    if request.method == 'POST':
        # 1. Check for file part and size limit (Flask handles size limit automatically)
        if 'file' not in request.files:
            flash('No file part in the request.', 'danger')
            return redirect(request.url) 
        
        file = request.files['file']
        description = request.form.get('description')
        subject = request.form.get('subject')
        
        # 2. Check if file is selected and allowed
        if file.filename == '' or not allowed_file(file.filename):
            flash('Invalid file selected or file type not allowed.', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            # Extract file extension for database storage
            file_extension = filename.rsplit('.', 1)[1].lower()
            
            # Save the file to the UPLOAD_FOLDER
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            # Create a new File entry in the database
            new_file = File(
                user_id=current_user.id,
                filename=filename,
                description=description,
                subject=subject,
                file_type=file_extension
            )
            
            db.session.add(new_file)
            
            # Update user's upload count and badges
            current_user.upload_count += 1
            update_badges(current_user)
            
            db.session.commit()
            flash(f'File "{filename}" uploaded successfully!', 'success')
            return redirect(url_for('dashboard')) 
    
    return render_template('upload.html')

@app.route('/file/<int:file_id>')
@login_required
def file_detail(file_id):
    """Shows file details, preview, and comment section."""
    file_item = db.session.get(File, file_id)
    if file_item is None:
        abort(404)
        
    # Fetch top-level comments (parent_id is None)
    main_comments = db.session.execute(
        db.select(Comment)
        .filter(Comment.file_id == file_id, Comment.parent_id == None)
        .order_by(desc(Comment.timestamp))
    ).scalars().all()
    
    return render_template('detail.html', file_item=file_item, main_comments=main_comments)


@app.route('/comment/<int:file_id>', methods=['POST'])
@login_required
def add_comment(file_id):
    """Handles adding a comment or a reply to a file."""
    text = request.form.get('comment_text')
    parent_id = request.form.get('parent_id') # Will be None if it's a new main comment
    
    if text:
        new_comment = Comment(
            user_id=current_user.id,
            file_id=file_id,
            text=text,
            parent_id=parent_id if parent_id else None
        )
        db.session.add(new_comment)
        db.session.commit()
        flash('Comment posted!', 'success')
        
    return redirect(url_for('file_detail', file_id=file_id))

@app.route('/file/delete/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    """Allows original uploader or admin to delete a file."""
    file_item = db.session.get(File, file_id)
    
    if file_item is None:
        abort(404)

    # Check for authorization
    if file_item.user_id != current_user.id and not current_user.is_admin:
        flash('You are not authorized to delete this file.', 'danger')
        return redirect(url_for('dashboard'))
    
    # 1. Delete the actual file from the file system
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_item.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        
    # 2. Delete the record from the database (Comments are cascaded and deleted automatically)
    db.session.delete(file_item)
    db.session.commit()
    
    flash(f'File "{file_item.filename}" successfully deleted.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/download/<filename>')
@login_required
def download_file(filename):
    """Allows the user to download the file."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/preview/<filename>')
@login_required
def preview_file(filename):
    """Allows the user to view the file in the browser (if the browser supports it)."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)


# --- 6. RUN THE APPLICATION ---

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
  
