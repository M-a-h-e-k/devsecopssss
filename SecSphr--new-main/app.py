import os
import csv
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timezone

# Add import for generating random tokens
import secrets
from datetime import timedelta

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey-change-in-production')

# Database Configuration - Professional Setup
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "instance", "securesphere.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_timeout': 20,
    'pool_recycle': -1,
    'pool_pre_ping': True
}
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'csv', 'txt', 'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'xlsx', 'zip'}

# Email Configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@securesphere.com')

# Ensure instance and upload directories exist
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
mail = Mail(app)

# ==================== DATABASE MODELS ====================

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='client')  # client, lead, superuser
    organization = db.Column(db.String(200))
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    first_login = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime)

    # Relationships
    products = db.relationship('Product', backref='owner', lazy=True, cascade='all, delete-orphan')
    responses = db.relationship('QuestionnaireResponse', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    product_url = db.Column(db.String(500), nullable=False)
    programming_language = db.Column(db.String(100), nullable=False)
    cloud_platform = db.Column(db.String(100), nullable=False)
    cloud_platform_other = db.Column(db.String(200))
    cicd_platform = db.Column(db.String(100), nullable=False)
    additional_details = db.Column(db.Text)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    responses = db.relationship('QuestionnaireResponse', backref='product', lazy=True, cascade='all, delete-orphan')
    statuses = db.relationship('ProductStatus', backref='product', lazy=True, cascade='all, delete-orphan')
    scores = db.relationship('ScoreHistory', backref='product', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Product {self.name}>'

class ProductStatus(db.Model):
    __tablename__ = 'product_statuses'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(50), default='in_progress')  # in_progress, questions_done, under_review, review_done, completed, needs_client_response
    questions_completed = db.Column(db.Integer, default=0)
    total_questions = db.Column(db.Integer, default=0)
    completion_percentage = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Composite index for better performance
    __table_args__ = (db.Index('idx_product_user', 'product_id', 'user_id'),)

    def __repr__(self):
        return f'<ProductStatus {self.product_id}-{self.user_id}: {self.status}>'

class QuestionnaireResponse(db.Model):
    __tablename__ = 'questionnaire_responses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    section = db.Column(db.String(100), nullable=False)
    question = db.Column(db.Text, nullable=False)
    question_index = db.Column(db.Integer)  # For ordering
    answer = db.Column(db.String(500))
    client_comment = db.Column(db.Text)
    evidence_path = db.Column(db.String(500))
    score = db.Column(db.Integer, default=0)
    max_score = db.Column(db.Integer, default=0)
    is_reviewed = db.Column(db.Boolean, default=False)
    needs_client_response = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    lead_comments = db.relationship('LeadComment', backref='response', lazy=True, cascade='all, delete-orphan')

    # Composite indexes for better performance
    __table_args__ = (
        db.Index('idx_user_product', 'user_id', 'product_id'),
        db.Index('idx_section', 'section'),
        db.Index('idx_needs_response', 'needs_client_response'),
    )

    def __repr__(self):
        return f'<Response {self.id}: {self.section}>'

class LeadComment(db.Model):
    __tablename__ = 'lead_comments'

    id = db.Column(db.Integer, primary_key=True)
    response_id = db.Column(db.Integer, db.ForeignKey('questionnaire_responses.id'))
    lead_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, needs_revision, rejected, client_reply
    parent_comment_id = db.Column(db.Integer, db.ForeignKey('lead_comments.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    parent_comment = db.relationship('LeadComment', remote_side=[id], backref='replies')
    lead = db.relationship('User', foreign_keys=[lead_id], backref='lead_comments_made')
    client = db.relationship('User', foreign_keys=[client_id], backref='lead_comments_received')
    product = db.relationship('Product', backref='lead_comments')

    # Indexes for better performance
    __table_args__ = (
        db.Index('idx_client_read', 'client_id', 'is_read'),
        db.Index('idx_status', 'status'),
    )

    def __repr__(self):
        return f'<LeadComment {self.id}: {self.status}>'

class ScoreHistory(db.Model):
    __tablename__ = 'score_history'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    section_name = db.Column(db.String(100), nullable=False)
    total_score = db.Column(db.Integer, default=0)
    max_score = db.Column(db.Integer, default=0)
    percentage = db.Column(db.Float, default=0.0)
    questions_answered = db.Column(db.Integer, default=0)
    questions_total = db.Column(db.Integer, default=0)
    calculated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Composite index for better performance
    __table_args__ = (db.Index('idx_product_user_section', 'product_id', 'user_id', 'section_name'),)

    def __repr__(self):
        return f'<ScoreHistory {self.product_id}-{self.section_name}: {self.percentage}%>'

class SystemSettings(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<SystemSettings {self.key}: {self.value}>'

class InvitationToken(db.Model):
    __tablename__ = 'invitation_tokens'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)  # client or lead
    organization = db.Column(db.String(200))
    invited_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    used_at = db.Column(db.DateTime)

    # Relationships
    inviter = db.relationship('User', backref='sent_invitations')

    def is_expired(self):
        # Ensure both datetimes are timezone-aware for comparison
        now = datetime.now(timezone.utc)
        expires_at = self.expires_at

        # Handle timezone conversion more robustly
        if expires_at is None:
            return True  # If no expiration date, consider it expired

        # If expires_at is naive, make it timezone-aware (assume UTC)
        if expires_at.tzinfo is None or expires_at.tzinfo.utcoffset(expires_at) is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Convert both to UTC for comparison
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

        if expires_at.tzinfo != timezone.utc:
            expires_at = expires_at.astimezone(timezone.utc)

        return now > expires_at

    def __repr__(self):
        return f'<InvitationToken {self.email}: {self.role}>'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_invitation_email(email, role, invitation_link, inviter_name):
    """Send invitation email to new user"""
    try:
        subject = f"Invitation to join SecureSphere as {role.title()}"

        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Inter', Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
                .btn {{ display: inline-block; background: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
                .btn:hover {{ background: #1e40af; }}
                .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 14px; color: #6b7280; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🛡️ SecureSphere</h1>
                    <h2>You're Invited!</h2>
                </div>
                <div class="content">
                    <p>Hello,</p>
                    <p><strong>{inviter_name}</strong> has invited you to join <strong>SecureSphere</strong> as a <strong>{role.title()}</strong>.</p>
                    <p>SecureSphere is a comprehensive security assessment platform that helps organizations evaluate and improve their security posture.</p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{invitation_link}" class="btn">Accept Invitation & Register</a>
                    </div>

                    <p><strong>What happens next?</strong></p>
                    <ul>
                        <li>Click the button above to access the registration page</li>
                        <li>Create your account with your preferred username and password</li>
                        <li>Start using SecureSphere immediately</li>
                    </ul>

                    <p><strong>Note:</strong> This invitation link will expire in 7 days for security purposes.</p>

                    <div class="footer">
                        <p>If you're having trouble with the button above, copy and paste this link into your browser:</p>
                        <p><a href="{invitation_link}">{invitation_link}</a></p>
                        <p>This invitation was sent to {email}. If you didn't expect this invitation, you can safely ignore this email.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        SecureSphere Invitation

        Hello,

        {inviter_name} has invited you to join SecureSphere as a {role.title()}.

        To accept this invitation and create your account, please visit:
        {invitation_link}

        This invitation link will expire in 7 days.

        If you didn't expect this invitation, you can safely ignore this email.

        Best regards,
        The SecureSphere Team
        """

        msg = Message(
            subject=subject,
            sender=app.config['MAIL_DEFAULT_SENDER'],
            recipients=[email],
            body=text_body,
            html=html_body
        )

        mail.send(msg)
        return True

    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        return False

def load_questionnaire():
    sections = {}
    # Try different file paths and encodings
    possible_paths = [
        'static/devweb.csv',
        'devweb.csv',
        os.path.join('static', 'devweb.csv'),
        os.path.join(os.path.dirname(__file__), 'static', 'devweb.csv'),
        os.path.join(os.path.dirname(__file__), 'devweb.csv')
    ]
    
    possible_encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1']
    
    csv_file = None
    encoding_used = None
    
    # Try to find the file with different paths and encodings
    for file_path in possible_paths:
        if os.path.exists(file_path):
            for encoding in possible_encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        # Test if we can read the first line
                        first_line = f.readline()
                        f.seek(0)  # Reset file pointer
                        reader = csv.DictReader(f)
                        # Test if we can read the header
                        fieldnames = reader.fieldnames
                        if fieldnames and 'Dimensions' in fieldnames:
                            csv_file = file_path
                            encoding_used = encoding
                            break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            if csv_file:
                break
    
    if not csv_file:
        print("Warning: CSV file not found or unreadable. Using fallback questionnaire.")
        return get_fallback_questionnaire()
    
    try:
        with open(csv_file, 'r', encoding=encoding_used) as f:
            reader = csv.DictReader(f)
            current_dimension = None
            current_question_obj = None
            
            for row in reader:
                try:
                    dimension = row.get('Dimensions', '').strip()
                    question = row.get('Questions', '').strip()
                    description = row.get('Description', '').strip()
                    option = row.get('Options', '').strip()
                    
                    # New dimension starts
                    if dimension:
                        current_dimension = dimension
                        if current_dimension not in sections:
                            sections[current_dimension] = []
                    
                    # New question starts
                    if question:
                        # Save previous question to section (if exists)
                        if current_question_obj:
                            sections[current_dimension].append(current_question_obj)
                        current_question_obj = {
                            'question': question,
                            'description': description,
                            'options': []
                        }
                    
                    # Add option to current question
                    if current_question_obj is not None and option:
                        current_question_obj['options'].append(option)
                        
                except KeyError as e:
                    print(f"Warning: Missing column in CSV: {e}")
                    continue
                except Exception as e:
                    print(f"Warning: Error processing row: {e}")
                    continue
            
            # Add last question
            if current_question_obj:
                sections[current_dimension].append(current_question_obj)
                
        print(f"Successfully loaded questionnaire from {csv_file} using {encoding_used} encoding")
        return sections
        
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        return get_fallback_questionnaire()

def get_fallback_questionnaire():
    """Fallback questionnaire in case CSV file cannot be loaded"""
    return {
        "Build and Deployment": [
            {
                "question": "Do you have a defined and documented build and deployment process?",
                "description": "A build process defines how source code is compiled, tested, and packaged.",
                "options": [
                    "A) No defined process; builds and deployment are manual or ad hoc.",
                    "B) Some projects have defined processes, but these are undocumented and inconsistent.",
                    "C) A documented process exists but lacks adoption in all teams.",
                    "D) All teams follow a consistent, well-documented process.",
                    "E) Processes are optimized, automated, and integrated with CI/CD."
                ]
            }
        ],
        "Information Gathering": [
            {
                "question": "Do you perform threat modeling or security risk assessments?",
                "description": "Systematic approach to identifying and evaluating security threats.",
                "options": [
                    "A) No formal threat modeling or risk assessment is performed.",
                    "B) Ad hoc security considerations without formal process.",
                    "C) Basic threat modeling performed for some projects.",
                    "D) Comprehensive threat modeling for all major projects.",
                    "E) Advanced threat modeling integrated into development lifecycle."
                ]
            }
        ],
        "Implementation": [
            {
                "question": "Do you follow secure coding practices?",
                "description": "Implementation of security-focused programming practices.",
                "options": [
                    "A) No formal secure coding practices.",
                    "B) Basic awareness but inconsistent application.",
                    "C) Documented guidelines with some enforcement.",
                    "D) Well-established practices with regular training.",
                    "E) Advanced secure coding with automated enforcement."
                ]
            }
        ],
        "Test and Verification": [
            {
                "question": "Do you perform security testing?",
                "description": "Systematic testing to identify security vulnerabilities.",
                "options": [
                    "A) No dedicated security testing.",
                    "B) Basic manual security checks.",
                    "C) Some automated security testing tools.",
                    "D) Comprehensive security testing program.",
                    "E) Advanced testing with continuous security validation."
                ]
            }
        ],
        "Response": [
            {
                "question": "Do you have an incident response plan?",
                "description": "Documented procedures for handling security incidents.",
                "options": [
                    "A) No formal incident response plan.",
                    "B) Basic informal response procedures.",
                    "C) Documented plan with limited testing.",
                    "D) Well-tested incident response procedures.",
                    "E) Advanced response capabilities with regular drills."
                ]
            }
        ]
    }

# Load questionnaire data
QUESTIONNAIRE = load_questionnaire()
SECTION_IDS = list(QUESTIONNAIRE.keys())

# Database initialization
def init_database():
    """Initialize database and create tables if they don't exist"""
    with app.app_context():
        try:
            db.create_all()
            print("✅ Database tables initialized")
        except Exception as e:
            print(f"❌ Error initializing database: {e}")

        # Fix any existing naive datetime entries
        try:
            fix_naive_datetimes()
        except Exception as e:
            print(f"⚠️ Warning: Could not fix naive datetimes: {e}")

        # Ensure default admin user exists
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            print("Creating default admin user...")
            admin = User(
                username='admin',
                email='admin@securesphere.com',
                role='superuser',
                organization='SecureSphere Inc.',
                first_name='System',
                last_name='Administrator'
            )
            admin.set_password('AdminPass123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Default admin user created")

def fix_naive_datetimes():
    """Fix any naive datetime entries in the database"""
    print("🔧 Checking for naive datetime entries...")

    # Fix InvitationToken entries
    invitations = InvitationToken.query.all()
    fixed_count = 0

    for invitation in invitations:
        needs_update = False

        # Fix expires_at if it's naive
        if invitation.expires_at and (invitation.expires_at.tzinfo is None or
                                    invitation.expires_at.tzinfo.utcoffset(invitation.expires_at) is None):
            invitation.expires_at = invitation.expires_at.replace(tzinfo=timezone.utc)
            needs_update = True

        # Fix created_at if it's naive
        if invitation.created_at and (invitation.created_at.tzinfo is None or
                                    invitation.created_at.tzinfo.utcoffset(invitation.created_at) is None):
            invitation.created_at = invitation.created_at.replace(tzinfo=timezone.utc)
            needs_update = True

        # Fix used_at if it's naive
        if invitation.used_at and (invitation.used_at.tzinfo is None or
                                 invitation.used_at.tzinfo.utcoffset(invitation.used_at) is None):
            invitation.used_at = invitation.used_at.replace(tzinfo=timezone.utc)
            needs_update = True

        if needs_update:
            fixed_count += 1

    if fixed_count > 0:
        db.session.commit()
        print(f"✅ Fixed {fixed_count} naive datetime entries")
    else:
        print("✅ No naive datetime entries found")

def get_csv_score_for_answer(dimension, question, answer):
    """Get score from CSV for a specific dimension, question, and answer"""
    # Try different file paths and encodings
    possible_paths = [
        'static/devweb.csv',
        'devweb.csv',
        os.path.join('static', 'devweb.csv'),
        os.path.join(os.path.dirname(__file__), 'static', 'devweb.csv'),
        os.path.join(os.path.dirname(__file__), 'devweb.csv')
    ]
    
    possible_encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1']
    
    for file_path in possible_paths:
        if os.path.exists(file_path):
            for encoding in possible_encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        reader = csv.DictReader(f)
                        current_dimension = None
                        current_question = None
                        
                        for row in reader:
                            try:
                                dim = row.get('Dimensions', '').strip()
                                q = row.get('Questions', '').strip()
                                option = row.get('Options', '').strip()
                                score_text = row.get('Scores', '').strip()
                                
                                if dim:
                                    current_dimension = dim
                                if q:
                                    current_question = q
                                    
                                # Check if we found the right combination
                                if (current_dimension == dimension and 
                                    current_question == question and 
                                    option == answer and score_text):
                                    try:
                                        return int(score_text)
                                    except (ValueError, TypeError):
                                        pass
                            except Exception:
                                continue
                                        
                    # If we got here, we successfully read the file but didn't find the answer
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            if encoding:
                break
    
    # Default scoring based on option letter if CSV parsing fails
    if answer.startswith('A)'):
        return 1
    elif answer.startswith('B)'):
        return 2
    elif answer.startswith('C)'):
        return 3
    elif answer.startswith('D)'):
        return 4
    elif answer.startswith('E)'):
        return 5
    else:
        return 1  # Default minimum score

def calculate_score_for_answer(question, answer):
    """Calculate score for a specific question-answer pair based on CSV data"""
    # Try different file paths and encodings
    possible_paths = [
        'static/devweb.csv',
        'devweb.csv',
        os.path.join('static', 'devweb.csv'),
        os.path.join(os.path.dirname(__file__), 'static', 'devweb.csv'),
        os.path.join(os.path.dirname(__file__), 'devweb.csv')
    ]
    
    possible_encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1']
    
    for file_path in possible_paths:
        if os.path.exists(file_path):
            for encoding in possible_encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        reader = csv.DictReader(f)
                        current_question = None
                        question_scores = {}

                        for row in reader:
                            try:
                                q = row.get('Questions', '').strip()
                                option = row.get('Options', '').strip()
                                scores_text = row.get('Scores', '').strip()

                                # Track current question
                                if q:
                                    current_question = q
                                    question_scores = {}

                                # Store score for each option of current question
                                if current_question and option and scores_text:
                                    try:
                                        score = int(scores_text)
                                        question_scores[option] = score
                                    except (ValueError, TypeError):
                                        pass

                                # Check if we found a match for our question and answer
                                if current_question == question and answer in question_scores:
                                    return question_scores[answer] * 20  # Scale 1-5 to 20-100 scoring system
                            except Exception:
                                continue

                    # If we got here, we successfully read the file but didn't find the answer
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            if encoding:
                break

    # Default scoring based on option letter if CSV parsing fails
    if answer.startswith('A)'):
        return 20  # Lowest score (1*20)
    elif answer.startswith('B)'):
        return 40  # (2*20)
    elif answer.startswith('C)'):
        return 60  # (3*20)
    elif answer.startswith('D)'):
        return 80  # (4*20)
    elif answer.startswith('E)'):
        return 100  # Highest score (5*20)
    else:
        # Fallback to original logic
        if answer.lower() in ['yes', 'fully implemented', 'high']:
            return 100
        elif answer.lower() in ['partially', 'medium']:
            return 50
        elif answer.lower() in ['no', 'not implemented', 'low']:
            return 20
        else:
            return 25

def calculate_dimension_scores(product_id, user_id):
    """Calculate dimension-wise scores using the new logic: sum of option scores / total questions in dimension"""
    try:
        responses = QuestionnaireResponse.query.filter_by(
            product_id=product_id, user_id=user_id
        ).all()
        
        # Group responses by dimension
        dimension_data = {}
        
        for response in responses:
            try:
                dimension = response.section
                if dimension not in dimension_data:
                    dimension_data[dimension] = {
                        'total_score': 0,
                        'question_count': 0,
                        'questions': []
                    }
                
                # Get score from CSV
                score = get_csv_score_for_answer(dimension, response.question, response.answer)
                if score is not None and isinstance(score, (int, float)):
                    dimension_data[dimension]['total_score'] += score
                    dimension_data[dimension]['question_count'] += 1
                    dimension_data[dimension]['questions'].append({
                        'question': response.question,
                        'answer': response.answer,
                        'score': score
                    })
            except (TypeError, AttributeError):
                continue
        
        # Calculate average score for each dimension
        dimension_scores = {}
        for dimension, data in dimension_data.items():
            try:
                if data['question_count'] > 0:
                    avg_score = data['total_score'] / data['question_count']
                    dimension_scores[dimension] = {
                        'average_score': round(avg_score, 2),
                        'total_score': data['total_score'],
                        'question_count': data['question_count'],
                        'questions': data['questions']
                    }
                else:
                    dimension_scores[dimension] = {
                        'average_score': 0,
                        'total_score': 0,
                        'question_count': 0,
                        'questions': []
                    }
            except (TypeError, ZeroDivisionError):
                dimension_scores[dimension] = {
                    'average_score': 0,
                    'total_score': 0,
                    'question_count': 0,
                    'questions': []
                }
        
        return dimension_scores
    except Exception:
        return {}

def calculate_maturity_score(dimension_scores):
    """Calculate overall maturity score: sum of all dimension averages / total dimensions"""
    if not dimension_scores:
        return 0
    
    try:
        valid_scores = []
        for dim_data in dimension_scores.values():
            if dim_data and isinstance(dim_data, dict) and 'average_score' in dim_data:
                score = dim_data['average_score']
                if score is not None and isinstance(score, (int, float)):
                    valid_scores.append(score)
        
        if not valid_scores:
            return 0
            
        total_avg = sum(valid_scores)
        maturity_score = total_avg / len(valid_scores)
        return round(maturity_score)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0

def get_section_wise_dimensions(product_id, user_id):
    """Get dimension scores organized by section with detailed breakdown"""
    try:
        responses = QuestionnaireResponse.query.filter_by(
            product_id=product_id, user_id=user_id
        ).all()
        
        section_dimensions = {}
        
        for response in responses:
            section = response.section
            if section not in section_dimensions:
                section_dimensions[section] = {
                    'total_score': 0,
                    'max_possible_score': 0,
                    'question_count': 0,
                    'percentage': 0,
                    'questions': []
                }
            
            # Get score from CSV
            score = get_csv_score_for_answer(section, response.question, response.answer)
            if score is not None and isinstance(score, (int, float)):
                section_dimensions[section]['total_score'] += score
                section_dimensions[section]['max_possible_score'] += 5  # Assuming max score is 5
                section_dimensions[section]['question_count'] += 1
                section_dimensions[section]['questions'].append({
                    'question': response.question,
                    'answer': response.answer,
                    'score': score
                })
        
        # Calculate percentages
        for section, data in section_dimensions.items():
            if data['max_possible_score'] > 0:
                data['percentage'] = round((data['total_score'] / data['max_possible_score']) * 100, 1)
            else:
                data['percentage'] = 0
        
        return section_dimensions
    except Exception:
        return {}

def update_product_status(product_id, user_id):
    """Update product status based on current responses and reviews"""
    status_record = ProductStatus.query.filter_by(product_id=product_id, user_id=user_id).first()
    if not status_record:
        status_record = ProductStatus(product_id=product_id, user_id=user_id)
        db.session.add(status_record)

    # Count total questions and answered questions
    total_questions = sum(len(questions) for questions in QUESTIONNAIRE.values())
    answered_questions = QuestionnaireResponse.query.filter_by(
        product_id=product_id, user_id=user_id
    ).count()

    # Count reviewed questions (with safety check for is_reviewed column)
    try:
        reviewed_questions = QuestionnaireResponse.query.filter_by(
            product_id=product_id, user_id=user_id, is_reviewed=True
        ).count()
    except Exception:
        # If is_reviewed column doesn't exist yet, assume no questions are reviewed
        reviewed_questions = 0

    # Update status based on progress
    if answered_questions == 0:
        status_record.status = 'in_progress'
    elif answered_questions == total_questions and reviewed_questions == 0:
        status_record.status = 'questions_done'
    elif reviewed_questions > 0 and reviewed_questions < answered_questions:
        status_record.status = 'under_review'
    elif reviewed_questions == answered_questions and answered_questions == total_questions:
        # Check if all reviews are approved
        approved_count = db.session.query(LeadComment).join(QuestionnaireResponse).filter(
            QuestionnaireResponse.product_id == product_id,
            QuestionnaireResponse.user_id == user_id,
            LeadComment.status == 'approved'
        ).count()

        if approved_count == answered_questions:
            status_record.status = 'completed'
        else:
            status_record.status = 'review_done'
    else:
        status_record.status = 'in_progress'

    status_record.questions_completed = answered_questions
    status_record.total_questions = total_questions
    status_record.last_updated = datetime.utcnow()

    db.session.commit()
    return status_record.status

def calculate_and_store_scores(product_id, user_id):
    """Calculate scores for all sections and store in ScoreHistory"""
    responses = QuestionnaireResponse.query.filter_by(
        product_id=product_id, user_id=user_id
    ).all()

    section_scores = {}
    section_max_scores = {}

    # Calculate scores by section
    for response in responses:
        section = response.section
        if section not in section_scores:
            section_scores[section] = 0
            section_max_scores[section] = 0

        # Calculate score for this response
        score = calculate_score_for_answer(response.question, response.answer)
        try:
            response.score = score
        except Exception:
            # If score column doesn't exist yet, skip setting it
            pass
        section_scores[section] += score

        # Calculate max possible score for this question
        max_score = 100  # Default max score per question
        section_max_scores[section] += max_score

    # Store scores in ScoreHistory
    for section, total_score in section_scores.items():
        max_score = section_max_scores.get(section, 1)
        percentage = (total_score / max_score * 100) if max_score > 0 else 0

        # Remove old score record for this section
        ScoreHistory.query.filter_by(
            product_id=product_id, user_id=user_id, section_name=section
        ).delete()

        # Add new score record
        score_record = ScoreHistory(
            product_id=product_id,
            user_id=user_id,
            section_name=section,
            total_score=total_score,
            max_score=max_score,
            percentage=percentage
        )
        db.session.add(score_record)

    db.session.commit()
    return section_scores

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash('Access denied!')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Get invitation token from URL
    token = request.args.get('token')
    invitation = None

    if token:
        invitation = InvitationToken.query.filter_by(token=token, is_used=False).first()
        if not invitation:
            flash('Invalid invitation link.')
            return redirect(url_for('login'))

        # Check if invitation is expired with error handling
        try:
            if invitation.is_expired():
                flash('Expired invitation link.')
                return redirect(url_for('login'))
        except Exception as e:
            print(f"Error checking invitation expiration: {e}")
            # If there's an error checking expiration, try to fix the datetime and check again
            try:
                if invitation.expires_at and invitation.expires_at.tzinfo is None:
                    invitation.expires_at = invitation.expires_at.replace(tzinfo=timezone.utc)
                    db.session.commit()
                if invitation.is_expired():
                    flash('Expired invitation link.')
                    return redirect(url_for('login'))
            except Exception as e2:
                print(f"Could not fix invitation datetime: {e2}")
                flash('There was an issue with your invitation link. Please request a new one.')
                return redirect(url_for('login'))
    else:
        flash('Registration requires a valid invitation.')
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        organization = request.form.get('organization', '')

        # Validate invitation token
        if not invitation:
            flash('Registration requires a valid invitation.')
            return redirect(url_for('login'))

        # Ensure email matches invitation
        if email != invitation.email:
            flash('Email must match the invitation.')
            return redirect(url_for('register', token=token))

        # Server-side validation
        if not username or not email or not password or not confirm_password:
            flash('Please fill in all fields.')
            return redirect(url_for('register', token=token))

        # Check password confirmation
        if password != confirm_password:
            flash('Password and confirm password do not match.')
            return redirect(url_for('register', token=token))

        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('register', token=token))

        import re
        if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
            flash('Invalid email format.')
            return redirect(url_for('register', token=token))

        if len(password) < 8 or not re.search(r'[A-Z]', password) or not re.search(r'[a-z]', password) or not re.search(r'\d', password):
            flash('Password must be at least 8 characters and include uppercase, lowercase, and number.')
            return redirect(url_for('register', token=token))

        # Create user with invitation details
        user = User(
            username=username,
            email=email,
            role=invitation.role,  # Use role from invitation
            organization=organization or invitation.organization
        )
        user.set_password(password)
        db.session.add(user)

        # Mark invitation as used
        invitation.is_used = True
        invitation.used_at = datetime.now(timezone.utc)

        db.session.commit()
        flash('Registration successful. Please login.')
        return redirect(url_for('login'))

    return render_template('register.html', invitation=invitation)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash('Invalid credentials.')
            return redirect(url_for('login'))
        session['user_id'] = user.id
        session['role'] = user.role
        user.last_login = datetime.now(timezone.utc)
        
        # Check if this is first login for lead users
        if user.role == 'lead' and user.first_login:
            db.session.commit()
            return redirect(url_for('change_password_first_login'))
        
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required()
def dashboard():
    role = session['role']
    user_id = session['user_id']
    if role == 'client':
        products = Product.query.filter_by(owner_id=user_id).all()
        # Check assessment completion for each product
        products_with_status = []
        for product in products:
            # Get product status
            status_record = ProductStatus.query.filter_by(product_id=product.id, user_id=user_id).first()
            if not status_record:
                # Create initial status record
                status_record = ProductStatus(product_id=product.id, user_id=user_id)
                db.session.add(status_record)
                db.session.commit()

            # Get responses and calculate progress
            responses = QuestionnaireResponse.query.filter_by(product_id=product.id, user_id=user_id).all()
            completed_sections = set([r.section for r in responses])
            total_sections = len(SECTION_IDS)
            completed_sections_count = len(completed_sections)

            # Check for rejected questions that need client attention
            rejected_responses = QuestionnaireResponse.query.filter_by(
                product_id=product.id, user_id=user_id, needs_client_response=True
            ).all()
            rejected_count = len(rejected_responses)

            # If there are rejected questions, the assessment status should reflect this
            if rejected_count > 0:
                status_record.status = 'needs_client_response'
            elif completed_sections_count == total_sections and not rejected_count:
                # Check if all questions are reviewed
                all_reviewed = all(r.is_reviewed for r in responses)
                if all_reviewed:
                    status_record.status = 'completed'
                else:
                    status_record.status = 'under_review'

            # Find next section to continue
            next_section_idx = 0
            for i, section in enumerate(SECTION_IDS):
                if section not in completed_sections:
                    next_section_idx = i
                    break

            # Calculate new dimension scores and maturity score
            dimension_scores = calculate_dimension_scores(product.id, user_id)
            maturity_score = calculate_maturity_score(dimension_scores)
            section_dimensions = get_section_wise_dimensions(product.id, user_id)
            
            # Get latest scores for backward compatibility
            latest_scores = ScoreHistory.query.filter_by(
                product_id=product.id, user_id=user_id
            ).order_by(ScoreHistory.calculated_at.desc()).all()

            total_score = sum(score.total_score for score in latest_scores)
            max_possible_score = sum(score.max_score for score in latest_scores)
            overall_percentage = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0

            product_info = {
                'id': product.id,
                'name': product.name,
                'owner_id': product.owner_id,
                'status': status_record.status,
                'status_display': status_record.status.replace('_', ' ').title(),
                'completed_sections': completed_sections_count,
                'total_sections': total_sections,
                'next_section_idx': next_section_idx,
                'progress_percentage': round((completed_sections_count / total_sections) * 100, 1),
                'answered_questions': status_record.questions_completed,
                'total_questions': status_record.total_questions,
                'overall_score': round(overall_percentage, 1),
                'last_updated': status_record.last_updated,
                'rejected_count': rejected_count,
                'dimension_scores': dimension_scores,
                'maturity_score': maturity_score,
                'section_dimensions': section_dimensions
            }
            products_with_status.append(product_info)

        # Get unread comments count for this client
        unread_comments = LeadComment.query.filter_by(client_id=user_id, is_read=False).count()

        return render_template('dashboard_client.html', products=products_with_status, unread_comments=unread_comments)
    elif role == 'lead':
        # Get all responses with user and product information - only for completed assessments
        resps = db.session.query(QuestionnaireResponse, User, Product).join(
            User, QuestionnaireResponse.user_id == User.id
        ).join(
            Product, QuestionnaireResponse.product_id == Product.id
        ).all()

        # Organize responses by client and product - filter for complete assessments only
        clients_data = {}
        for resp, user, product in resps:
            # Check if this product's assessment is complete for this user
            if not is_assessment_complete(product.id, user.id):
                continue  # Skip incomplete assessments

            if user.id not in clients_data:
                clients_data[user.id] = {
                    'user': user,
                    'products': {}
                }
            if product.id not in clients_data[user.id]['products']:
                # Calculate dimension scores and maturity score for this product
                dimension_scores = calculate_dimension_scores(product.id, user.id)
                maturity_score = calculate_maturity_score(dimension_scores)
                section_dimensions = get_section_wise_dimensions(product.id, user.id)
                
                clients_data[user.id]['products'][product.id] = {
                    'product': product,
                    'responses': [],
                    'dimension_scores': dimension_scores,
                    'maturity_score': maturity_score,
                    'section_dimensions': section_dimensions
                }
            clients_data[user.id]['products'][product.id]['responses'].append(resp)

        # Get client replies for lead to see
        client_replies = LeadComment.query.filter_by(
            lead_id=session['user_id'], 
            status='client_reply'
        ).options(
            db.joinedload(LeadComment.client),
            db.joinedload(LeadComment.product),
            db.joinedload(LeadComment.parent_comment)
        ).order_by(LeadComment.created_at.desc()).all()

        return render_template('dashboard_lead.html', clients_data=clients_data, client_replies=client_replies)
    elif role == 'superuser':
        products = Product.query.all()

        # Get detailed product data with responses and scoring
        products_data = []
        for product in products:
            responses = QuestionnaireResponse.query.filter_by(product_id=product.id).all()

            # Calculate scores by dimension
            dimension_scores = {}
            for resp in responses:
                if resp.section not in dimension_scores:
                    dimension_scores[resp.section] = {'total': 0, 'count': 0}

                # Simple scoring based on answer (this can be made more sophisticated)
                score = 0
                if 'yes' in resp.answer.lower() or 'high' in resp.answer.lower():
                    score = 100
                elif 'partially' in resp.answer.lower() or 'medium' in resp.answer.lower():
                    score = 50
                elif 'no' in resp.answer.lower() or 'low' in resp.answer.lower():
                    score = 0
                else:
                    score = 25  # Default for other answers

                dimension_scores[resp.section]['total'] += score
                dimension_scores[resp.section]['count'] += 1

            # Calculate average scores for each dimension
            for dimension in dimension_scores:
                if dimension_scores[dimension]['count'] > 0:
                    dimension_scores[dimension]['average'] = dimension_scores[dimension]['total'] / dimension_scores[dimension]['count']
                else:
                    dimension_scores[dimension]['average'] = 0

            # Get product owner info
            owner = User.query.get(product.owner_id)

            products_data.append({
                'product': product,
                'owner': owner,
                'responses': responses,
                'dimension_scores': dimension_scores,
                'total_responses': len(responses)
            })

        # Get all responses and comments for admin view
        all_responses = db.session.query(QuestionnaireResponse, User, Product).join(
            User, QuestionnaireResponse.user_id == User.id
        ).join(
            Product, QuestionnaireResponse.product_id == Product.id
        ).order_by(QuestionnaireResponse.created_at.desc()).limit(100).all()
        all_comments = LeadComment.query.options(db.joinedload(LeadComment.product), db.joinedload(LeadComment.lead), db.joinedload(LeadComment.client)).order_by(LeadComment.created_at.desc()).limit(50).all()

        return render_template('dashboard_superuser.html', products_data=products_data, all_responses=all_responses, all_comments=all_comments)
    return redirect(url_for('index'))

def is_assessment_complete(product_id, user_id):
    """Check if assessment is complete for a product"""
    completed_sections = set([
        r.section for r in QuestionnaireResponse.query.filter_by(
            product_id=product_id, user_id=user_id
        ).all()
    ])
    return len(completed_sections) == len(SECTION_IDS)

@app.route('/add_product', methods=['GET', 'POST'])
@login_required('client')
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        product_url = request.form['product_url']
        programming_language = request.form['programming_language']
        cloud_platform = request.form['cloud_platform']
        cloud_platform_other = request.form.get('cloud_platform_other', '')
        cicd_platform = request.form['cicd_platform']
        additional_details = request.form.get('additional_details', '')


        if not name or not product_url or not programming_language or not cloud_platform or not cicd_platform:
            flash('Please fill in all required fields.')
            return redirect(url_for('add_product'))

        # If cloud_platform is "Other", use the custom value
        if cloud_platform == 'Other' and cloud_platform_other:
            cloud_platform = cloud_platform_other

        product = Product(
            name=name,

            product_url=product_url,
            programming_language=programming_language,
            cloud_platform=cloud_platform,
            cloud_platform_other=cloud_platform_other,
            cicd_platform=cicd_platform,
            additional_details=additional_details,
            owner_id=session['user_id']
        )
        db.session.add(product)
        db.session.commit()
        flash('Product added. Now fill the questionnaire.')
        return redirect(url_for('fill_questionnaire_section', product_id=product.id, section_idx=0))
    return render_template('add_product.html')

@app.route('/fill_questionnaire/<int:product_id>/section/<int:section_idx>', methods=['GET', 'POST'])
@login_required('client')
def fill_questionnaire_section(product_id, section_idx):
    product = Product.query.get_or_404(product_id)
    sections = SECTION_IDS
    if section_idx >= len(sections):
        flash("All sections complete!")
        return redirect(url_for('dashboard'))
    section_name = sections[section_idx]
    questions = QUESTIONNAIRE[section_name]

    # Get existing responses for this section to pre-populate form
    existing_responses = QuestionnaireResponse.query.filter_by(
        product_id=product_id,
        user_id=session['user_id'],
        section=section_name
    ).all()

    # Create a dictionary for quick lookup of existing responses
    existing_answers = {}
    for resp in existing_responses:
        for i, q in enumerate(questions):
            if q['question'] == resp.question:
                existing_answers[i] = resp
                break

    if request.method == 'POST':
        # Get lead comments for validation
        response_ids = [resp.id for resp in existing_responses]
        lead_comments = {}
        if response_ids:
            comments = LeadComment.query.filter(LeadComment.response_id.in_(response_ids)).all()
            for comment in comments:
                lead_comments[comment.response_id] = comment

        # Delete existing responses for this section before adding new ones (except approved ones)
        responses_to_delete = []
        for resp in existing_responses:
            lead_comment = lead_comments.get(resp.id)
            if not lead_comment or lead_comment.status != 'approved':
                responses_to_delete.append(resp.id)

        if responses_to_delete:
            QuestionnaireResponse.query.filter(QuestionnaireResponse.id.in_(responses_to_delete)).delete()

        for i, q in enumerate(questions):
            # Check if this question is approved
            existing_resp = existing_answers.get(i)
            if existing_resp:
                lead_comment = lead_comments.get(existing_resp.id)
                if lead_comment and lead_comment.status == 'approved':
                    # Keep the approved response as-is, don't update it
                    continue

            answer = request.form.get(f'answer_{i}')
            comment = request.form.get(f'comment_{i}')
            file = request.files.get(f'evidence_{i}')
            evidence_path = ""

            # Keep existing evidence if no new file uploaded
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{product_id}_{section_idx}_{i}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                evidence_path = filepath
            elif i in existing_answers:
                evidence_path = existing_answers[i].evidence_path or ''

            resp = QuestionnaireResponse(
                user_id=session['user_id'],
                product_id=product_id,
                section=section_name,
                question=q['question'],
                answer=answer,
                client_comment=comment,
                evidence_path=evidence_path,
                is_reviewed=False,  # Reset review status for new/updated responses
                needs_client_response=False  # Reset the client response flag when they respond
            )
            db.session.add(resp)
        db.session.commit()

        # Update product status and calculate scores
        status = update_product_status(product_id, session['user_id'])
        calculate_and_store_scores(product_id, session['user_id'])

        if section_idx + 1 < len(sections):
            return redirect(url_for('fill_questionnaire_section', product_id=product_id, section_idx=section_idx+1))
        else:
            if status == 'questions_done':
                flash("Questions completed! Waiting for review.")
            elif status == 'completed':
                flash("Assessment completed successfully!")
            else:
                flash("Section saved successfully!")
            return redirect(url_for('dashboard'))

    completed_sections = [
        s.section for s in QuestionnaireResponse.query.filter_by(product_id=product_id, user_id=session['user_id']).distinct(QuestionnaireResponse.section)
    ]
    progress = [(i, s, (s in completed_sections)) for i, s in enumerate(sections)]

    # Get review status for questions in this section
    question_review_status = {}
    if existing_responses:
        response_ids = [resp.id for resp in existing_responses]
        lead_comments = LeadComment.query.filter(LeadComment.response_id.in_(response_ids)).all()
        for comment in lead_comments:
            for resp in existing_responses:
                if resp.id == comment.response_id:
                    for i, q in enumerate(questions):
                        if q['question'] == resp.question:
                            question_review_status[i] = comment.status
                            break

    return render_template(
        'fill_questionnaire_section.html',
        product=product,
        section_name=section_name,
        questions=questions,
        section_idx=section_idx,
        total_sections=len(sections),
        progress=progress,
        existing_answers=existing_answers,
        question_review_status=question_review_status
    )

@app.route('/product/<int:product_id>/results')
@login_required('client')
def product_results(product_id):
    resps = QuestionnaireResponse.query.filter_by(product_id=product_id, user_id=session['user_id']).all()
    # Get lead comments for this product
    lead_comments = LeadComment.query.options(db.joinedload(LeadComment.product), db.joinedload(LeadComment.lead)).filter_by(product_id=product_id, client_id=session['user_id']).order_by(LeadComment.created_at.desc()).all()
    
    # Calculate dimension scores and maturity score
    dimension_scores = calculate_dimension_scores(product_id, session['user_id'])
    maturity_score = calculate_maturity_score(dimension_scores)
    section_dimensions = get_section_wise_dimensions(product_id, session['user_id'])
    
    # Get product info
    product = Product.query.get_or_404(product_id)
    
    # Get all user products for selection dropdown
    user_products = get_user_products(session['user_id'])
    
    # Convert responses to serializable format
    responses_json = []
    for resp in resps:
        responses_json.append({
            'id': resp.id,
            'section': resp.section,
            'question': resp.question,
            'answer': resp.answer,
            'client_comment': resp.client_comment,
            'score': resp.score,
            'max_score': resp.max_score,
            'is_reviewed': resp.is_reviewed
        })
    
    return render_template('product_results.html', 
                         responses=resps, 
                         responses_json=responses_json,
                         lead_comments=lead_comments,
                         dimension_scores=dimension_scores,
                         maturity_score=maturity_score,
                         section_dimensions=section_dimensions,
                         product=product,
                         current_product=product,
                         user_products=user_products)

@app.route('/client/comments')
@login_required('client')
def client_comments():
    comments = LeadComment.query.options(db.joinedload(LeadComment.product), db.joinedload(LeadComment.lead)).filter_by(client_id=session['user_id']).order_by(LeadComment.created_at.desc()).all()
    return render_template('client_comments.html', comments=comments)

@app.route('/client/comment/<int:comment_id>/read')
@login_required('client')
def mark_comment_read(comment_id):
    comment = LeadComment.query.get_or_404(comment_id)
    if comment.client_id == session['user_id']:
        comment.is_read = True
        db.session.commit()
        flash('Comment marked as read.', 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/client/comment/<int:comment_id>/reply', methods=['POST'])
@login_required('client')
def client_reply_comment(comment_id):
    parent_comment = LeadComment.query.get_or_404(comment_id)
    if parent_comment.client_id != session['user_id']:
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))

    # Check if client has already replied to this comment
    existing_reply = LeadComment.query.filter_by(
        parent_comment_id=comment_id,
        client_id=session['user_id'],
        status='client_reply'
    ).first()
    
    if existing_reply:
        flash('You have already replied to this comment.')
        return redirect(request.referrer or url_for('client_comments'))

    reply_text = request.form['reply']
    evidence_file = request.files.get('evidence')

    if reply_text.strip():
        evidence_path = None
        # Handle evidence upload if provided
        if evidence_file and evidence_file.filename and allowed_file(evidence_file.filename):
            filename = secure_filename(evidence_file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            evidence_path = os.path.join('static', 'uploads', filename)
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            evidence_file.save(full_path)

        # Create a reply comment with evidence information
        reply_comment = LeadComment(
            response_id=parent_comment.response_id,
            lead_id=parent_comment.lead_id,  # Send back to the original lead
            client_id=session['user_id'],
            product_id=parent_comment.product_id,
            comment=reply_text + (f"\n[Evidence File: {evidence_file.filename}]" if evidence_path and evidence_file and evidence_file.filename else ""),
            status='client_reply',
            parent_comment_id=comment_id
        )
        db.session.add(reply_comment)

        # If evidence provided, also update the original response
        if evidence_path and parent_comment.response_id:
            original_response = QuestionnaireResponse.query.get(parent_comment.response_id)
            if original_response:
                original_response.evidence_path = evidence_path
                original_response.client_comment = reply_text
                # Reset needs_client_response flag when they respond with evidence
                original_response.needs_client_response = False

        db.session.commit()
        flash('Reply sent to lead successfully.' + (' Evidence file uploaded.' if evidence_path else ''))

    return redirect(request.referrer or url_for('client_comments'))

@app.route('/api/maturity-heatmap/<int:product_id>')
@login_required('client')
def api_maturity_heatmap(product_id):
    """API endpoint to get maturity heatmap data for a product"""
    product = Product.query.get_or_404(product_id)
    if product.owner_id != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Calculate dimension scores and maturity score
    dimension_scores = calculate_dimension_scores(product_id, session['user_id'])
    maturity_score = calculate_maturity_score(dimension_scores)
    
    # Prepare heatmap data
    heatmap_data = {
        'product_id': product_id,
        'product_name': product.name,
        'overall_maturity_score': maturity_score,
        'overall_maturity_level': get_maturity_level_name(maturity_score),
        'dimensions': []
    }
    
    for dimension, score_data in dimension_scores.items():
        level = round(score_data['average_score'])
        heatmap_data['dimensions'].append({
            'name': dimension,
            'score': score_data['average_score'],
            'level': level,
            'level_name': get_maturity_level_name(level),
            'question_count': score_data['question_count'],
            'total_score': score_data['total_score']
        })
    
    return jsonify(heatmap_data)

def get_maturity_level_name(level):
    """Get the name for a maturity level"""
    level_names = {
        0: 'Not Assessed',
        1: 'Initial',
        2: 'Developing', 
        3: 'Defined',
        4: 'Managed',
        5: 'Optimized'
    }
    return level_names.get(level, 'Unknown')

@app.route('/lead/comments')
@login_required('lead')
def lead_comments():
    # Get all comments where this lead is involved (either as the lead or where client replied)
    comments = LeadComment.query.options(
        db.joinedload(LeadComment.product),
        db.joinedload(LeadComment.client),
        db.joinedload(LeadComment.response)
    ).filter(
        db.or_(
            LeadComment.lead_id == session['user_id'],
            db.and_(
                LeadComment.status == 'client_reply',
                LeadComment.parent_comment_id.in_(
                    db.session.query(LeadComment.id).filter_by(lead_id=session['user_id'])
                )
            )
        )
    ).order_by(LeadComment.created_at.desc()).all()
    
    return render_template('lead_comments.html', comments=comments)

@app.route('/lead/comment/<int:comment_id>/reply', methods=['POST'])
@login_required('lead')
def lead_reply_comment(comment_id):
    parent_comment = LeadComment.query.get_or_404(comment_id)
    
    # Check if this lead has permission to reply
    if parent_comment.lead_id != session['user_id'] and not (
        parent_comment.status == 'client_reply' and 
        LeadComment.query.filter_by(id=parent_comment.parent_comment_id, lead_id=session['user_id']).first()
    ):
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))

    # Check if lead has already replied to this specific comment thread
    if parent_comment.status == 'client_reply':
        # This is a reply to a client reply, check if lead already replied to this client reply
        existing_reply = LeadComment.query.filter_by(
            parent_comment_id=comment_id,
            lead_id=session['user_id'],
            status='lead_reply'
        ).first()
        
        if existing_reply:
            flash('You have already replied to this message.')
            return redirect(request.referrer or url_for('lead_comments'))

    reply_text = request.form['reply']

    if reply_text.strip():
        # Create a reply comment
        reply_comment = LeadComment(
            response_id=parent_comment.response_id,
            lead_id=session['user_id'],
            client_id=parent_comment.client_id,
            product_id=parent_comment.product_id,
            comment=reply_text,
            status='lead_reply',
            parent_comment_id=comment_id
        )
        db.session.add(reply_comment)
        db.session.commit()
        flash('Reply sent to client successfully.')

    return redirect(request.referrer or url_for('lead_comments'))

@app.route('/lead/reply/<int:reply_id>/read', methods=['POST'])
@login_required('lead')
def mark_client_reply_read(reply_id):
    """Mark a client reply as read by the lead"""
    reply = LeadComment.query.get_or_404(reply_id)
    
    # Check if this lead has permission to mark this reply as read
    if reply.lead_id != session['user_id'] or reply.status != 'client_reply':
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Mark as read (we can add an is_read field to the model later if needed)
    # For now, we'll just return success
    return jsonify({'success': True})

@app.route('/api/unread-messages')
@login_required()
def get_unread_messages():
    """Get count of unread messages for the current user"""
    user_role = session['role']
    user_id = session['user_id']
    
    if user_role == 'client':
        # Count unread lead comments for this client
        unread_count = LeadComment.query.filter_by(
            client_id=user_id, 
            is_read=False
        ).filter(
            LeadComment.status.in_(['approved', 'needs_revision', 'rejected', 'lead_reply'])
        ).count()
    elif user_role == 'lead':
        # Count unread client replies for this lead
        unread_count = LeadComment.query.filter_by(
            lead_id=user_id,
            status='client_reply'
        ).filter(
            LeadComment.is_read == False
        ).count()
    else:
        unread_count = 0
    
    return jsonify({'unread_count': unread_count})

@app.route('/api/chat-notifications')
@login_required()
def get_chat_notifications():
    """Get recent chat notifications for the current user"""
    user_role = session['role']
    user_id = session['user_id']
    
    notifications = []
    
    if user_role == 'client':
        # Get recent lead comments for this client
        recent_comments = LeadComment.query.options(
            db.joinedload(LeadComment.product),
            db.joinedload(LeadComment.lead)
        ).filter_by(
            client_id=user_id
        ).filter(
            LeadComment.status.in_(['approved', 'needs_revision', 'rejected', 'lead_reply'])
        ).order_by(LeadComment.created_at.desc()).limit(5).all()
        
        for comment in recent_comments:
            notifications.append({
                'id': comment.id,
                'type': 'lead_comment',
                'message': f"Review from {comment.lead.username}",
                'product': comment.product.name,
                'status': comment.status,
                'timestamp': comment.created_at.isoformat(),
                'is_read': comment.is_read
            })
    
    elif user_role == 'lead':
        # Get recent client replies for this lead
        recent_replies = LeadComment.query.options(
            db.joinedload(LeadComment.product),
            db.joinedload(LeadComment.client)
        ).filter_by(
            lead_id=user_id,
            status='client_reply'
        ).order_by(LeadComment.created_at.desc()).limit(5).all()
        
        for reply in recent_replies:
            notifications.append({
                'id': reply.id,
                'type': 'client_reply',
                'message': f"Reply from {reply.client.username}",
                'product': reply.product.name,
                'timestamp': reply.created_at.isoformat(),
                'is_read': getattr(reply, 'is_read', True)  # Default to read if field doesn't exist
            })
    
    return jsonify({'notifications': notifications})

@app.route('/api/chat-thread/<int:comment_id>')
@login_required()
def get_chat_thread(comment_id):
    """Get full conversation thread for a comment"""
    user_role = session['role']
    user_id = session['user_id']
    
    # Get the root comment
    root_comment = LeadComment.query.get_or_404(comment_id)
    
    # Check permissions
    if user_role == 'client' and root_comment.client_id != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    elif user_role == 'lead' and root_comment.lead_id != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get all comments in this thread
    thread_comments = LeadComment.query.options(
        db.joinedload(LeadComment.lead),
        db.joinedload(LeadComment.client),
        db.joinedload(LeadComment.product)
    ).filter(
        db.or_(
            LeadComment.id == comment_id,
            LeadComment.parent_comment_id == comment_id
        )
    ).order_by(LeadComment.created_at.asc()).all()
    
    thread_data = []
    for comment in thread_comments:
        thread_data.append({
            'id': comment.id,
            'comment': comment.comment,
            'status': comment.status,
            'created_at': comment.created_at.isoformat(),
            'is_read': comment.is_read,
            'author': {
                'id': comment.lead_id if comment.status != 'client_reply' else comment.client_id,
                'username': comment.lead.username if comment.status != 'client_reply' else comment.client.username,
                'role': 'lead' if comment.status != 'client_reply' else 'client'
            }
        })
    
    return jsonify({'thread': thread_data})

@app.route('/api/mark-thread-read/<int:comment_id>', methods=['POST'])
@login_required()
def mark_thread_read(comment_id):
    """Mark all messages in a thread as read"""
    user_role = session['role']
    user_id = session['user_id']
    
    # Get all comments in thread
    if user_role == 'client':
        comments_to_mark = LeadComment.query.filter(
            db.or_(
                LeadComment.id == comment_id,
                LeadComment.parent_comment_id == comment_id
            )
        ).filter(
            LeadComment.client_id == user_id,
            LeadComment.is_read == False
        ).all()
    else:
        comments_to_mark = LeadComment.query.filter(
            db.or_(
                LeadComment.id == comment_id,
                LeadComment.parent_comment_id == comment_id
            )
        ).filter(
            LeadComment.lead_id == user_id,
            LeadComment.status == 'client_reply',
            LeadComment.is_read == False
        ).all()
    
    for comment in comments_to_mark:
        comment.is_read = True
    
    db.session.commit()
    
    return jsonify({'success': True, 'marked_count': len(comments_to_mark)})

@app.route('/api/send-message', methods=['POST'])
@login_required()
def send_message():
    """Send a new message in a conversation thread"""
    user_role = session['role']
    user_id = session['user_id']
    
    data = request.get_json()
    parent_comment_id = data.get('parent_comment_id')
    message_text = data.get('message', '').strip()
    
    if not message_text:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    # Get parent comment to determine context
    parent_comment = LeadComment.query.get_or_404(parent_comment_id)
    
    # Check permissions
    if user_role == 'client' and parent_comment.client_id != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    elif user_role == 'lead' and parent_comment.lead_id != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Create new message
    new_message = LeadComment(
        response_id=parent_comment.response_id,
        lead_id=parent_comment.lead_id if user_role == 'client' else user_id,
        client_id=parent_comment.client_id if user_role == 'lead' else user_id,
        product_id=parent_comment.product_id,
        comment=message_text,
        status='client_reply' if user_role == 'client' else 'lead_reply',
        parent_comment_id=parent_comment_id,
        is_read=False
    )
    
    db.session.add(new_message)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': {
            'id': new_message.id,
            'comment': new_message.comment,
            'status': new_message.status,
            'created_at': new_message.created_at.isoformat(),
            'author': {
                'username': session.get('username', 'Unknown'),
                'role': user_role
            }
        }
    })

@app.route('/change-password-first-login', methods=['GET', 'POST'])
@login_required('lead')
def change_password_first_login():
    user = User.query.get(session['user_id'])
    
    # Only allow this route for first-time login
    if not user.first_login:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Validate current password
        if not user.check_password(current_password):
            flash('Current password is incorrect.', 'error')
            return render_template('change_password_first_login.html')
        
        # Validate new password
        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'error')
            return render_template('change_password_first_login.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return render_template('change_password_first_login.html')
        
        # Update password and mark first login as complete
        user.set_password(new_password)
        user.first_login = False
        db.session.commit()
        
        flash('Password changed successfully! Welcome to SecureSphere.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('change_password_first_login.html')

@app.route('/change-password', methods=['GET', 'POST'])
@login_required()
def change_password():
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Validate current password
        if not user.check_password(current_password):
            flash('Current password is incorrect.', 'error')
            return render_template('change_password.html')
        
        # Validate new password
        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'error')
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return render_template('change_password.html')
        
        # Update password
        user.set_password(new_password)
        db.session.commit()
        
        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('change_password.html')

@app.route('/review/<int:response_id>', methods=['GET', 'POST'])
@login_required('lead')
def review_questionnaire(response_id):
    resp = QuestionnaireResponse.query.get_or_404(response_id)
    if request.method == 'POST':
        comment = request.form['lead_comment']
        status = request.form.get('review_status', 'pending')

        # Create lead comment
        lead_comment = LeadComment(
            response_id=response_id,
            lead_id=session['user_id'],
            client_id=resp.user_id,
            product_id=resp.product_id,
            comment=comment,
            status=status
        )
        db.session.add(lead_comment)

        # Mark response as reviewed (with safety check)
        try:
            if status == 'rejected':
                resp.is_reviewed = False  # Allow client to modify rejected responses
                resp.needs_client_response = True  # Mark for client attention
            else:
                resp.is_reviewed = True
        except Exception:
            # If is_reviewed column doesn't exist yet, skip setting it
            pass

        db.session.commit()

        # Update product status and recalculate scores
        update_product_status(resp.product_id, resp.user_id)
        calculate_and_store_scores(resp.product_id, resp.user_id)

        flash('Review comment sent to client.')
        return redirect(url_for('dashboard'))
    return render_template('review_questionnaire.html', response=resp)

@app.route('/admin/product/<int:product_id>/details')
@login_required('superuser')
def admin_product_details(product_id):
    resps = QuestionnaireResponse.query.filter_by(product_id=product_id).all()
    return render_template('admin_product_details.html', responses=resps, product_id=product_id)

@app.route('/admin/create_product', methods=['GET', 'POST'])
@login_required('superuser')
def admin_create_product():
    if request.method == 'POST':
        product_name = request.form['product_name']
        client_id = request.form['client_id']

        # Verify client exists
        client = User.query.filter_by(id=client_id, role='client').first()
        if not client:
            flash('Invalid client selected.')
            return redirect(url_for('admin_create_product'))

        # Create product
        product = Product(name=product_name, owner_id=client_id)
        db.session.add(product)
        db.session.commit()

        flash(f'Product "{product_name}" created successfully for {client.username}.')
        return redirect(url_for('dashboard'))

    # Get all clients for the form
    clients = User.query.filter_by(role='client').all()
    return render_template('admin_create_product.html', clients=clients)

@app.route('/admin/analytics')
@login_required('superuser')
def admin_analytics():
    # Get all products and their scores for analytics
    products = Product.query.all()
    analytics_data = []

    for product in products:
        responses = QuestionnaireResponse.query.filter_by(product_id=product.id).all()
        if responses:
            # Calculate average score for this product
            total_score = 0
            total_questions = 0
            section_scores = {}

            for response in responses:
                if response.answer.isdigit():
                    score = int(response.answer)
                    total_score += score
                    total_questions += 1

                    if response.section not in section_scores:
                        section_scores[response.section] = []
                    section_scores[response.section].append(score)

            if total_questions > 0:
                avg_score = total_score / total_questions
                owner = User.query.get(product.owner_id)

                analytics_data.append({
                    'product': product,
                    'owner': owner,
                    'avg_score': avg_score,
                    'total_responses': len(responses),
                    'section_scores': {k: sum(v)/len(v) for k, v in section_scores.items()}
                })

    return render_template('admin_analytics.html', analytics_data=analytics_data)

@app.route('/admin/products/delete/<int:product_id>')
@login_required('superuser')
def admin_delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    QuestionnaireResponse.query.filter_by(product_id=product_id).delete()
    db.session.delete(product)
    db.session.commit()
    flash('Product and all responses deleted.')
    return redirect(url_for('dashboard'))

@app.route('/api/product/<int:product_id>/scores')
@login_required()
def api_product_scores(product_id):
    resps = QuestionnaireResponse.query.filter_by(product_id=product_id).all()
    section_scores = {}
    section_max_scores = {}
    section_counts = {}
    total_score = 0
    total_max_score = 0
    csv_map = {}

    # Build scoring map from CSV
    with open('devweb.csv', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        current_question = None
        current_dimension = None
        question_options = {}

        for row in reader:
            dimension = row['Dimensions'].strip()
            question = row['Questions'].strip()
            option = row['Options'].strip()
            score_text = row.get('Scores', '').strip()

            # Track current dimension and question
            if dimension:
                current_dimension = dimension
            if question:
                current_question = question
                question_options = {}
                if current_dimension not in section_max_scores:
                    section_max_scores[current_dimension] = 0

            # Store option and score for current question
            if current_question and option and score_text:
                try:
                    score = int(score_text)
                    question_options[option] = score
                    csv_map[current_question] = question_options.copy()
                except (ValueError, TypeError):
                    pass

        # Calculate max scores per section
        for question, options in csv_map.items():
            if options:
                max_score = max(options.values())
                # Find dimension for this question
                for dimension in section_max_scores:
                    if any(resp.question == question and resp.section == dimension for resp in resps):
                        if section_max_scores[dimension] == 0:  # Only add once per question
                            section_max_scores[dimension] += max_score
                            total_max_score += max_score
                        break

    # Calculate actual scores
    question_scores = {}
    for r in resps:
        sec = r.section
        if sec not in section_scores:
            section_scores[sec] = 0
            section_counts[sec] = 0

        score = csv_map.get(r.question, {}).get(r.answer, 0)
        section_scores[sec] += score
        section_counts[sec] += 1
        total_score += score

        # Store individual question scores
        question_scores[f"{r.question}:{r.answer}"] = score

    # Calculate percentages
    section_labels = list(section_scores.keys())
    section_values = [section_scores[k] for k in section_labels]
    section_percentages = []

    for section in section_labels:
        max_section_score = section_max_scores.get(section, 1)
        percentage = (section_scores[section] / max_section_score * 100) if max_section_score > 0 else 0
        section_percentages.append(round(percentage, 1))

    overall_percentage = (total_score / total_max_score * 100) if total_max_score > 0 else 0

    return jsonify({
        "section_labels": section_labels,
        "section_scores": section_values,
        "section_percentages": section_percentages,
        "section_max_scores": [section_max_scores.get(k, 0) for k in section_labels],
        "total_score": total_score,
        "max_score": total_max_score,
        "overall_percentage": round(overall_percentage, 1),
        "sections_count": len(section_labels),
        "question_scores": question_scores
    })

@app.route('/api/superuser/all_scores')
@login_required('superuser')
def api_all_scores():
    products = Product.query.all()
    all_scores = []

    for product in products:
        product_data = {}
        resps = QuestionnaireResponse.query.filter_by(product_id=product.id).all()

        if resps:
            # Get scores for this product
            section_scores = {}
            section_max_scores = {}
            total_score = 0
            total_max_score = 0
            csv_map = {}

            # Build scoring map
            with open('devweb.csv', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                current_question = None
                current_dimension = None
                question_options = {}

                for row in reader:
                    dimension = row['Dimensions'].strip()
                    question = row['Questions'].strip()
                    option = row['Options'].strip()
                    score_text = row.get('Scores', '').strip()

                    # Track current dimension and question
                    if dimension:
                        current_dimension = dimension
                    if question:
                        current_question = question
                        question_options = {}
                        if current_dimension not in section_max_scores:
                            section_max_scores[current_dimension] = 0

                    # Store option and score for current question
                    if current_question and option and score_text:
                        try:
                            score = int(score_text)
                            question_options[option] = score
                            csv_map[current_question] = question_options.copy()
                        except (ValueError, TypeError):
                            pass

                # Calculate max scores per section
                for question, options in csv_map.items():
                    if options:
                        max_score = max(options.values())
                        # Find dimension for this question
                        for dimension in section_max_scores:
                            if any(resp.question == question and resp.section == dimension for resp in resps):
                                section_max_scores[dimension] += max_score
                                total_max_score += max_score
                                break

            # Calculate scores
            for r in resps:
                sec = r.section
                if sec not in section_scores:
                    section_scores[sec] = 0

                score = csv_map.get(r.question, {}).get(r.answer, 0)
                section_scores[sec] += score
                total_score += score

            overall_percentage = (total_score / total_max_score * 100) if total_max_score > 0 else 0

            # Get owner info
            owner = User.query.get(product.owner_id)

            product_data = {
                'id': product.id,
                'name': product.name,
                'owner': owner.username if owner else 'Unknown',
                'organization': owner.organization if owner else 'Unknown',
                'total_score': total_score,
                'max_score': total_max_score,
                'percentage': round(overall_percentage, 1),
                'section_scores': section_scores,
                'section_percentages': {k: round((v / section_max_scores.get(k, 1) * 100), 1)
                                       for k, v in section_scores.items()}
            }
        else:
            product_data = {
                'id': product.id,
                'name': product.name,
                'owner': 'Unknown',
                'organization': 'Unknown',
                'total_score': 0,
                'max_score': 0,
                'percentage': 0,
                'section_scores': {},
                'section_percentages': {}
            }

        all_scores.append(product_data)

    return jsonify(all_scores)

@app.route('/admin/invite_user', methods=['GET', 'POST'])
@login_required('superuser')
def invite_user():
    if request.method == 'POST':
        email = request.form['email']
        role = request.form['role']
        organization = request.form.get('organization', '')

        # Validate inputs
        if not email or not role:
            flash('Email and role are required.')
            return redirect(url_for('invite_user'))

        if role not in ['client', 'lead']:
            flash('Invalid role. Must be client or lead.')
            return redirect(url_for('invite_user'))

        # Check if user already exists
        if User.query.filter_by(email=email).first():
            flash('User with this email already exists.')
            return redirect(url_for('invite_user'))

        # Check if there's already a pending invitation
        existing_invitation = InvitationToken.query.filter_by(email=email, is_used=False).first()
        if existing_invitation:
            try:
                if not existing_invitation.is_expired():
                    flash('There is already a pending invitation for this email.')
                    return redirect(url_for('invite_user'))
            except Exception as e:
                print(f"Error checking existing invitation expiration: {e}")
                # If there's an error, assume it's expired and continue with new invitation
                pass

        # Generate invitation token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)  # 7 days to accept

        invitation = InvitationToken(
            token=token,
            email=email,
            role=role,
            organization=organization,
            invited_by=session['user_id'],
            expires_at=expires_at
        )

        db.session.add(invitation)
        db.session.commit()

        # Generate invitation link
        invitation_link = url_for('register', token=token, _external=True)

        # Get inviter's name
        inviter = User.query.get(session['user_id'])
        inviter_name = f"{inviter.first_name} {inviter.last_name}".strip() or inviter.username

        # Try to send email invitation
        email_sent = send_invitation_email(email, role, invitation_link, inviter_name)

        if email_sent:
            flash(f'Invitation email sent successfully to {email}! They will receive a registration link via email.', 'success')
        else:
            flash(f'Invitation created but email could not be sent. Registration link: {invitation_link}', 'warning')

        return redirect(url_for('invite_user'))

    return render_template('admin_invite_user.html')

@app.route('/admin/manage_users')
@login_required('superuser')
def manage_users():
    users = User.query.order_by(User.created_at.desc()).all()
    pending_invitations = InvitationToken.query.filter_by(is_used=False).order_by(InvitationToken.created_at.desc()).all()
    return render_template('admin_manage_users.html', users=users, pending_invitations=pending_invitations)

@app.route('/admin/create_lead', methods=['POST'])
@login_required('superuser')
def create_lead():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    organization = request.form.get('organization', '')

    # Validate inputs
    if not username or not email or not password:
        flash('Username, email, and password are required.')
        return redirect(url_for('manage_users'))

    if User.query.filter_by(username=username).first():
        flash('Username already exists.')
        return redirect(url_for('manage_users'))

    if User.query.filter_by(email=email).first():
        flash('Email already exists.')
        return redirect(url_for('manage_users'))

    # Create lead user
    user = User(
        username=username,
        email=email,
        role='lead',
        organization=organization
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    flash(f'Lead user {username} created successfully. Password: {password}')
    return redirect(url_for('manage_users'))

@app.route('/admin/revoke_invitation/<int:invitation_id>')
@login_required('superuser')
def revoke_invitation(invitation_id):
    invitation = InvitationToken.query.get_or_404(invitation_id)
    invitation.is_used = True  # Mark as used to effectively revoke it
    db.session.commit()
    flash('Invitation revoked successfully.')
    return redirect(url_for('manage_users'))

@app.route('/static/uploads/<filename>')
@login_required()
def uploaded_file(filename):
    """Serve uploaded evidence files with authentication"""
    from flask import send_from_directory
    import os
    upload_folder = app.config['UPLOAD_FOLDER']
    file_path = os.path.join(upload_folder, filename)
    
    # Check if file exists
    if not os.path.exists(file_path):
        flash('File not found.')
        return redirect(url_for('dashboard'))
    
    # Additional security: Check if user has access to this file
    # You can add more specific access control here if needed
    
    return send_from_directory(upload_folder, filename)

if __name__ == '__main__':
    print("🚀 Starting SecureSphere Application")
    print("Initializing database...")
    init_database()
    print("✅ Application ready")
    app.run(debug=True, port=5001, host='0.0.0.0')