import os
import re
import requests
from datetime import datetime, timezone
from urllib.parse import unquote
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "minecraft_myanmar_super_secret_key_2026")

# File Upload Configuration
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# reCAPTCHA Configuration
RECAPTCHA_SITE_KEY = os.environ.get("RECAPTCHA_SITE_KEY", "6LdwE4AtAAAAAGg9QvOg0eKkoFNu9slL2pbL3hgH")
RECAPTCHA_SECRET_KEY = os.environ.get("RECAPTCHA_SECRET_KEY", "6LdwE4AtAAAAAI5fRw2ikR6LlRKdwAF4HbrQQUim")
app.config['RECAPTCHA_SITE_KEY'] = RECAPTCHA_SITE_KEY

# Database Configuration
db_url = os.environ.get("DATABASE_URL", "sqlite:///minecraft_social.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ----------------- INAPPROPRIATE WORDS FILTER -----------------

BANNED_WORDS = [
    "sex", "lee", "sp", "nigger", "nigga", "porn", 
    "fuck", "mf", "motherfucker", "dih", "dick", "shit"
]

def contains_banned_words(text):
    """Returns True if text contains any banned words or invalid characters using word boundaries."""
    if not text:
        return False
    
    clean_text = text.lower()
    
    # Block dot-only or slash-only usernames/inputs
    if clean_text.strip().replace('.', '') == '' or clean_text.strip().replace('/', '') == '':
        return True

    # Check for whole banned words to avoid false positives
    for word in BANNED_WORDS:
        pattern = r'\b' + re.escape(word) + r'\b'
        if re.search(pattern, clean_text):
            return True
            
    return False

# ----------------- DATABASE MODELS -----------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    nickname = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    pfp_url = db.Column(db.String(300), default="https://placehold.co/150/1e293b/22c55e?text=Steve")
    bio = db.Column(db.String(200), default="Minecraft Myanmar Player ⛏️")
    is_admin = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=False)
    
    fake_followers = db.Column(db.String(20), nullable=True, default="0")
    fake_likes = db.Column(db.String(20), nullable=True, default="0")
    like_type_style = db.Column(db.String(50), nullable=True, default="❤️ Classic Red")

    @property
    def safe_pfp(self):
        return self.pfp_url or "https://placehold.co/150/1e293b/22c55e?text=Steve"

    @property
    def safe_like_style(self):
        return self.like_type_style or "❤️ Classic Red"


class VerificationRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Step 1: Reason
    reason_choice = db.Column(db.String(50), nullable=False)  # 'post_dlc', 'personal', 'other'
    reason_other = db.Column(db.Text, nullable=True)
    
    # Step 3: Admin Choice
    admin_known = db.Column(db.String(100), nullable=False)
    
    # Step 4: Personal Info
    real_name = db.Column(db.String(100), nullable=False)
    nickname = db.Column(db.String(100), nullable=True)
    age = db.Column(db.Integer, nullable=False)
    face_photo_url = db.Column(db.String(300), nullable=False)
    
    # Step 5: Web Links
    link_1 = db.Column(db.String(300), nullable=False)
    link_2 = db.Column(db.String(300), nullable=False)
    link_3 = db.Column(db.String(300), nullable=False)
    link_4 = db.Column(db.String(300), nullable=True)
    link_5 = db.Column(db.String(300), nullable=True)
    
    status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'rejected'
    reject_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='verification_requests')


class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_friend_requests')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_friend_requests')


class ProfileLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    giver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    liked_date = db.Column(db.String(10), nullable=False)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(300), nullable=True)
    download_link = db.Column(db.String(300), nullable=True)
    category = db.Column(db.String(50), default="General")
    feed_type = db.Column(db.String(20), default="community")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='posts')
    fake_likes = db.Column(db.String(20), nullable=True)


class PostLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user = db.relationship('User', backref='comments')
    post = db.relationship('Post', backref='comments')


class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])


class Mail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_mails')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_mails')


class GroupChat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class GroupMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group_chat.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    sender = db.relationship('User')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------- DB SETUP & INITIALIZATION -----------------

def init_database():
    """Safely initialize tables, alter schema, and seed admin users."""
    with app.app_context():
        # Force table creation
        db.create_all()
        
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            columns = [c['name'] for c in inspector.get_columns('user')]
            
            with db.engine.begin() as conn:
                if 'fake_followers' not in columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN fake_followers VARCHAR(20) DEFAULT \'0\';'))
                if 'fake_likes' not in columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN fake_likes VARCHAR(20) DEFAULT \'0\';'))
                if 'like_type_style' not in columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN like_type_style VARCHAR(50) DEFAULT \'❤️ Classic Red\';'))
                if 'is_verified' not in columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN is_verified BOOLEAN DEFAULT FALSE;'))
        except Exception as e:
            app.logger.warning(f"Schema check notice: {e}")

        admins = [
            ("heinth123", "Ssu@$1588hhs0=@@!!hsjk"),
            ("rivercraft_official", "argta6799+//@#$%sd@#4gysdf5"),
            ("SleepyDraxxzz", "ILOVEHELENA")
        ]
        
        for un, pw in admins:
            u = User.query.filter_by(username=un).first()
            if not u:
                u = User(username=un, nickname=un, password_hash=generate_password_hash(pw), is_admin=True, is_verified=True)
                db.session.add(u)
            else:
                u.is_admin = True
                u.is_verified = True

        db.session.commit()

init_database()

# ----------------- ROUTES -----------------

@app.route('/settings/verification', methods=['GET', 'POST'])
@login_required
def verification_page():
    if current_user.is_verified:
        flash("You are already verified! 🔵", "info")
        return redirect(url_for('profile', username=current_user.username))
        
    if request.method == 'POST':
        # reCAPTCHA check
        recaptcha_response = request.form.get('g-recaptcha-response')
        verify_url = "https://www.google.com/recaptcha/api/siteverify"
        payload = {'secret': RECAPTCHA_SECRET_KEY, 'response': recaptcha_response}
        
        try:
            res = requests.post(verify_url, data=payload, timeout=5).json()
            if not res.get('success'):
                flash('Please complete the "I am not a robot" test! 🤖🚫', 'danger')
                return redirect(url_for('verification_page'))
        except Exception:
            flash('reCAPTCHA verification failed! Try again.', 'danger')
            return redirect(url_for('verification_page'))

        # Handle File Upload
        file = request.files.get('face_photo')
        if not file or file.filename == '':
            flash('Please upload a valid face photo! 📷', 'danger')
            return redirect(url_for('verification_page'))

        filename = secure_filename(f"user_{current_user.id}_{int(datetime.now().timestamp())}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        face_photo_url = url_for('static', filename=f'uploads/{filename}')

        req = VerificationRequest(
            user_id=current_user.id,
            reason_choice=request.form.get('reason_choice'),
            reason_other=request.form.get('reason_other', '').strip(),
            admin_known=request.form.get('admin_known'),
            real_name=request.form.get('real_name', '').strip(),
            nickname=request.form.get('nickname', '').strip(),
            age=int(request.form.get('age', 0)),
            face_photo_url=face_photo_url,
            link_1=request.form.get('link_1', '').strip(),
            link_2=request.form.get('link_2', '').strip(),
            link_3=request.form.get('link_3', '').strip(),
            link_4=request.form.get('link_4', '').strip(),
            link_5=request.form.get('link_5', '').strip()
        )
        
        db.session.add(req)
        db.session.commit()
        flash('Verification request submitted! Admin will review your application. 📩', 'success')
        return redirect(url_for('profile', username=current_user.username))

    return render_template('verification.html')


@app.route('/admin/verify_action/<int:req_id>', methods=['POST'])
@login_required
def verify_action(req_id):
    if not current_user.is_admin:
        return redirect(url_for('home'))
        
    req_item = VerificationRequest.query.get_or_404(req_id)
    action = request.form.get('action')  # 'approve' or 'reject'
    reason = request.form.get('reason', '').strip()

    target_user = User.query.get(req_item.user_id)
    
    if action == 'approve':
        req_item.status = 'approved'
        target_user.is_verified = True
        flash(f"Approved verification for {target_user.username}! ✅", "success")
    elif action == 'reject':
        req_item.status = 'rejected'
        req_item.reject_reason = reason
        target_user.is_verified = False
        flash(f"Rejected verification for {target_user.username}. ❌", "info")

    db.session.commit()
    return redirect(request.referrer or url_for('mailbox'))


@app.route('/call/<int:user_id>')
@login_required
def video_call(user_id):
    target_user = User.query.get_or_404(user_id)
    return render_template('video_call.html', target_user=target_user)


@app.route('/mailbox', methods=['GET', 'POST'])
@login_required
def mailbox():
    if request.method == 'POST':
        receiver_id = request.form.get('receiver_id')
        subject = request.form.get('subject', '').strip()
        content = request.form.get('content', '').strip()
        
        if contains_banned_words(subject) or contains_banned_words(content):
            flash('Your mail contains inappropriate language! 🚫', 'danger')
            return redirect(url_for('mailbox'))

        if receiver_id and subject and content:
            new_mail = Mail(
                sender_id=current_user.id,
                receiver_id=int(receiver_id),
                subject=subject,
                content=content
            )
            db.session.add(new_mail)
            db.session.commit()
            flash('Mail sent successfully! ✉️', 'success')
            return redirect(url_for('mailbox'))
        else:
            flash('Please fill out all fields to send mail!', 'danger')

    received_mails = Mail.query.filter_by(receiver_id=current_user.id).order_by(Mail.created_at.desc()).all()
    sent_mails = Mail.query.filter_by(sender_id=current_user.id).order_by(Mail.created_at.desc()).all()
    all_other_users = User.query.filter(User.id != current_user.id).all()
    
    # Safe fetch for pending verification requests inside route
    pending_verifications = []
    if current_user.is_admin:
        try:
            pending_verifications = VerificationRequest.query.filter_by(status='pending').all()
        except Exception as e:
            app.logger.error(f"Verification query error: {e}")

    return render_template('mailbox.html', 
                           received_mails=received_mails, 
                           sent_mails=sent_mails, 
                           all_users=all_other_users,
                           pending_verifications=pending_verifications)


@app.route('/chat')
@login_required
def chat():
    all_users = User.query.filter(User.id != current_user.id).all()
    all_dms = DirectMessage.query.filter(
        (DirectMessage.sender_id == current_user.id) | (DirectMessage.receiver_id == current_user.id)
    ).order_by(DirectMessage.created_at.desc()).all()

    chat_partner_ids = []
    for msg in all_dms:
        partner_id = msg.receiver_id if msg.sender_id == current_user.id else msg.sender_id
        if partner_id not in chat_partner_ids:
            chat_partner_ids.append(partner_id)

    recent_chats = User.query.filter(User.id.in_(chat_partner_ids)).all() if chat_partner_ids else []
    return render_template('chat.html', recent_chats=recent_chats, all_users=all_users)


@app.route('/chat/dm/<int:receiver_id>', methods=['GET', 'POST'])
@login_required
def dm(receiver_id):
    receiver = User.query.get_or_404(receiver_id)
    
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if contains_banned_words(content):
            flash('Your message contains inappropriate language! 🚫', 'danger')
            return redirect(url_for('dm', receiver_id=receiver_id))

        if content:
            msg = DirectMessage(sender_id=current_user.id, receiver_id=receiver_id, content=content)
            db.session.add(msg)
            db.session.commit()
            return redirect(url_for('dm', receiver_id=receiver_id))
            
    messages = DirectMessage.query.filter(
        ((DirectMessage.sender_id == current_user.id) & (DirectMessage.receiver_id == receiver_id)) |
        ((DirectMessage.sender_id == receiver_id) & (DirectMessage.receiver_id == current_user.id))
    ).order_by(DirectMessage.created_at.asc()).all()
    
    return render_template('dm.html', receiver=receiver, messages=messages)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Welcome back! 🎮', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password!', 'danger')
            
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not username:
            flash('Username cannot be blank! 🚫', 'danger')
            return redirect(url_for('register'))

        if contains_banned_words(username):
            flash('That username contains inappropriate or invalid words! Please choose another. 🚫', 'danger')
            return redirect(url_for('register'))

        if len(username) < 2:
            flash('Username must be at least 2 characters long! 🚫', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('register'))
            
        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'danger')
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, nickname=username, password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        flash('Account created! Welcome to Minecraft Myanmar! 🎉', 'success')
        return redirect(url_for('home'))
        
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/', methods=['GET', 'POST'])
@login_required
def home():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        image_url = request.form.get('image_url')
        download_link = request.form.get('download_link')
        
        feed_type = 'official' if current_user.is_admin else 'community'

        if contains_banned_words(title) or contains_banned_words(content):
            flash('Your post contains inappropriate language! 🚫', 'danger')
            return redirect(url_for('home'))

        if title and content:
            new_post = Post(
                title=title,
                content=content,
                image_url=image_url,
                download_link=download_link,
                feed_type=feed_type,
                user_id=current_user.id
            )
            db.session.add(new_post)
            db.session.commit()
            flash('Published successfully! ✨', 'success')
            return redirect(url_for('home'))

    posts = Post.query.filter_by(feed_type='official').order_by(Post.id.desc()).all()
    return render_template('index.html', posts=posts, feed_title="🏠 Official Announcements & Addons")


@app.route('/community')
@login_required
def community():
    posts = Post.query.filter_by(feed_type='community').order_by(Post.id.desc()).all()
    return render_template('community.html', posts=posts)


@app.route('/create_post', methods=['POST'])
@login_required
def create_post():
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    image_url = request.form.get('image_url')
    download_link = request.form.get('download_link')
    feed_type = request.form.get('feed_type', 'community')
    
    if feed_type == 'official' and not current_user.is_admin:
        feed_type = 'community'

    if contains_banned_words(title) or contains_banned_words(content):
        flash('Your post contains inappropriate language and was blocked! 🚫', 'danger')
        return redirect(url_for('home' if feed_type == 'official' else 'community'))

    if title and content:
        new_post = Post(
            title=title,
            content=content,
            image_url=image_url,
            download_link=download_link,
            feed_type=feed_type,
            user_id=current_user.id
        )
        db.session.add(new_post)
        db.session.commit()
        flash('Published successfully! ✨', 'success')
        
    return redirect(url_for('home' if feed_type == 'official' else 'community'))


@app.route('/friends')
@login_required
def friends_list():
    friendships = Friendship.query.filter(
        ((Friendship.sender_id == current_user.id) | (Friendship.receiver_id == current_user.id)) &
        (Friendship.status == 'accepted')
    ).all()

    friends = [f.receiver if f.sender_id == current_user.id else f.sender for f in friendships]
    pending_requests = Friendship.query.filter_by(receiver_id=current_user.id, status='pending').all()
    all_users = User.query.filter(User.id != current_user.id).all()

    return render_template('friends.html', friends=friends, pending_requests=pending_requests, all_users=all_users)


@app.route('/search_friends', methods=['GET'])
@login_required
def search_friends():
    query = request.args.get('query', '').strip()
    search_results = []
    
    if query:
        search_results = User.query.filter(
            ((User.username.ilike(f"%{query}%")) | (User.nickname.ilike(f"%{query}%"))),
            User.id != current_user.id
        ).all()

    all_other_users = User.query.filter(User.id != current_user.id).all()
    
    def get_follower_count(u):
        if u.fake_followers and str(u.fake_followers).isdigit():
            return int(u.fake_followers)
        return Follow.query.filter_by(followed_id=u.id).count()

    recommended_users = sorted(
        all_other_users,
        key=lambda u: (u.is_admin, get_follower_count(u)),
        reverse=True
    )[:5]

    return render_template('search_friends.html', results=search_results, query=query, recommended=recommended_users)


@app.route('/friend/send/<int:user_id>', methods=['POST'])
@login_required
def send_friend_request(user_id):
    if user_id != current_user.id:
        existing = Friendship.query.filter(
            ((Friendship.sender_id == current_user.id) & (Friendship.receiver_id == user_id)) |
            ((Friendship.sender_id == user_id) & (Friendship.receiver_id == current_user.id))
        ).first()

        if not existing:
            request_obj = Friendship(sender_id=current_user.id, receiver_id=user_id, status='pending')
            db.session.add(request_obj)
            db.session.commit()
            flash('Friend request sent! 🤝', 'success')

    return redirect(request.referrer or url_for('friends_list'))


@app.route('/friend/accept/<int:request_id>', methods=['POST'])
@login_required
def accept_friend_request(request_id):
    friend_req = Friendship.query.get_or_404(request_id)
    if friend_req.receiver_id == current_user.id:
        friend_req.status = 'accepted'
        db.session.commit()
        flash('Friend request accepted! 🎉', 'success')
    return redirect(request.referrer or url_for('friends_list'))


@app.route('/friend/remove/<int:user_id>', methods=['POST'])
@login_required
def remove_friend(user_id):
    friendship = Friendship.query.filter(
        ((Friendship.sender_id == current_user.id) & (Friendship.receiver_id == user_id)) |
        ((Friendship.sender_id == user_id) & (Friendship.receiver_id == current_user.id))
    ).first()

    if friendship:
        db.session.delete(friendship)
        db.session.commit()
        flash('Friend removed.', 'info')

    return redirect(request.referrer or url_for('friends_list'))


@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    existing_like = PostLike.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if not existing_like:
        new_like = PostLike(user_id=current_user.id, post_id=post_id)
        db.session.add(new_like)
        db.session.commit()
    return redirect(request.referrer or url_for('home'))


@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    content = request.form.get('content', '').strip()
    if contains_banned_words(content):
        flash('Your comment contains inappropriate language! 🚫', 'danger')
        return redirect(request.referrer or url_for('home'))

    if content:
        comment = Comment(content=content, user_id=current_user.id, post_id=post_id)
        db.session.add(comment)
        db.session.commit()
    return redirect(request.referrer or url_for('home'))


@app.route('/user/<int:user_id>/follow', methods=['POST'])
@login_required
def follow_user(user_id):
    if user_id != current_user.id:
        existing = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
        if existing:
            db.session.delete(existing)
        else:
            new_follow = Follow(follower_id=current_user.id, followed_id=user_id)
            db.session.add(new_follow)
        db.session.commit()
    return redirect(request.referrer or url_for('home'))


@app.route('/user/<int:user_id>/profile_like', methods=['POST'])
@login_required
def profile_like(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    existing = ProfileLike.query.filter_by(giver_id=current_user.id, receiver_id=user_id, liked_date=today).first()
    
    if not existing:
        like_entry = ProfileLike(giver_id=current_user.id, receiver_id=user_id, liked_date=today)
        db.session.add(like_entry)
        db.session.commit()
        flash('Gave profile like for today! ❤️', 'success')
    else:
        flash('You already liked this profile today!', 'warning')
        
    return redirect(request.referrer or url_for('home'))


@app.route('/profile/')
@app.route('/profile/<path:username>')
@login_required
def profile(username=None):
    if not username:
        return redirect(url_for('profile', username=current_user.username))

    decoded_username = unquote(username).strip()
    user = User.query.filter(User.username.ilike(decoded_username)).first()
    
    if not user:
        flash(f"User '{decoded_username}' not found!", "danger")
        return redirect(url_for('home'))

    try:
        real_followers = Follow.query.filter_by(followed_id=user.id).count()
        if user.fake_followers and str(user.fake_followers).strip() not in ['', '0', 'None']:
            followers_count = user.fake_followers
        else:
            followers_count = real_followers
    except Exception as e:
        app.logger.error(f"Followers check error: {e}")
        followers_count = 0

    try:
        real_profile_likes = ProfileLike.query.filter_by(receiver_id=user.id).count()
        if user.fake_likes and str(user.fake_likes).strip() not in ['', '0', 'None']:
            profile_likes_count = user.fake_likes
        else:
            profile_likes_count = real_profile_likes
    except Exception as e:
        app.logger.error(f"Likes check error: {e}")
        profile_likes_count = 0

    is_following = False
    try:
        is_following = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first() is not None
    except Exception as e:
        app.logger.error(f"Is following check error: {e}")

    user_posts = []
    try:
        user_posts = Post.query.filter_by(user_id=user.id).order_by(Post.id.desc()).all()
    except Exception as e:
        app.logger.error(f"User posts query error: {e}")

    friendship = None
    try:
        friendship = Friendship.query.filter(
            ((Friendship.sender_id == current_user.id) & (Friendship.receiver_id == user.id)) |
            ((Friendship.sender_id == user.id) & (Friendship.receiver_id == current_user.id))
        ).first()
    except Exception as e:
        app.logger.error(f"Friendship query error: {e}")

    return render_template(
        'profile.html',
        user=user,
        followers_count=followers_count,
        profile_likes_count=profile_likes_count,
        is_following=is_following,
        user_posts=user_posts,
        friendship=friendship
    )


@app.route('/edit_profile', methods=['POST'])
@login_required
def edit_profile():
    nickname = request.form.get('nickname', '').strip()
    pfp_url = request.form.get('pfp_url')
    bio = request.form.get('bio', '').strip()
    like_type_style = request.form.get('like_type_style')
    
    if contains_banned_words(nickname) or contains_banned_words(bio):
        flash('Your profile changes contained inappropriate words! 🚫', 'danger')
        return redirect(url_for('profile', username=current_user.username))

    if nickname:
        current_user.nickname = nickname
    if pfp_url:
        current_user.pfp_url = pfp_url
    if bio:
        current_user.bio = bio
    if like_type_style:
        current_user.like_type_style = like_type_style
        
    db.session.commit()
    flash('Profile updated! ✨', 'success')
    return redirect(url_for('profile', username=current_user.username))


@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash("Access denied! Admins only. 🚫", "danger")
        return redirect(url_for('home'))
        
    all_users = User.query.all()
    all_posts = Post.query.order_by(Post.id.desc()).all()
    return render_template('admin.html', users=all_users, posts=all_posts)


@app.route('/admin/gui-update', methods=['POST'])
@login_required
def admin_gui_update():
    if not current_user.is_admin:
        flash("Access denied! Admins only. 🚫", "danger")
        return redirect(url_for('home'))

    setting_name = request.form.get('setting_name')
    flash(f"Updated GUI setting {setting_name}! ✨", "success")
    return redirect(request.referrer or url_for('admin_panel'))


@app.route('/admin/fake_stats/<int:user_id>', methods=['POST'])
@login_required
def fake_stats(user_id):
    if not current_user.is_admin:
        return redirect(url_for('home'))
        
    user = User.query.get_or_404(user_id)
    user.fake_followers = request.form.get('fake_followers') or None
    user.fake_likes = request.form.get('fake_likes') or None
    db.session.commit()
    
    flash('Fake stats applied! 🪄', 'success')
    return redirect(request.referrer or url_for('admin_panel'))


@app.route('/admin/fake_post_likes/<int:post_id>', methods=['POST'])
@login_required
def fake_post_likes(post_id):
    if not current_user.is_admin:
        return redirect(url_for('home'))
        
    post = Post.query.get_or_404(post_id)
    post.fake_likes = request.form.get('fake_likes') or None
    db.session.commit()
    
    flash('Post fake likes applied! 🪄', 'success')
    return redirect(request.referrer or url_for('admin_panel'))


@app.route('/admin/execute_command', methods=['POST'])
@login_required
def admin_execute_command():
    if not current_user.is_admin:
        flash("Access denied! Admins only. 🚫", "danger")
        return redirect(url_for('home'))

    command_str = request.form.get('command_str', '').strip()
    if not command_str:
        return redirect(url_for('admin_panel'))

    parts = command_str.split(' ', 2)
    cmd = parts[0].lower()
    arg1 = parts[1] if len(parts) > 1 else None
    arg2 = parts[2] if len(parts) > 2 else None

    # Handle commands
    if cmd in ['/verify', '/unverify', '/op', '/deop']:
        if not arg1:
            flash("Usage: /verify or /op [username]", "warning")
            return redirect(url_for('admin_panel'))
        
        user = User.query.filter_by(username=arg1).first()
        if not user:
            flash(f"User '{arg1}' not found!", "danger")
            return redirect(url_for('admin_panel'))

        if cmd == '/verify':
            user.is_verified = True
            flash(f"Verified @{user.username}! 🔵", "success")
        elif cmd == '/unverify':
            user.is_verified = False
            flash(f"Unverified @{user.username}.", "info")
        elif cmd == '/op':
            user.is_admin = True
            flash(f"Promoted @{user.username} to Admin! 👑", "success")
        elif cmd == '/deop':
            user.is_admin = False
            flash(f"Demoted @{user.username} from Admin.", "info")

        db.session.commit()

    elif cmd == '/set_followers' and arg1 and arg2:
        user = User.query.filter_by(username=arg1).first()
        if user:
            user.fake_followers = arg2
            db.session.commit()
            flash(f"Set @{user.username} followers to {arg2}! 📈", "success")

    elif cmd == '/set_likes' and arg1 and arg2:
        user = User.query.filter_by(username=arg1).first()
        if user:
            user.fake_likes = arg2
            db.session.commit()
            flash(f"Set @{user.username} likes to {arg2}! ❤️", "success")

    elif cmd == '/set_nickname' and arg1 and arg2:
        user = User.query.filter_by(username=arg1).first()
        if user:
            user.nickname = arg2
            db.session.commit()
            flash(f"Set @{user.username} nickname to {arg2}! ✏️", "success")

    elif cmd == '/set_pfp' and arg1 and arg2:
        user = User.query.filter_by(username=arg1).first()
        if user:
            user.pfp_url = arg2
            db.session.commit()
            flash(f"Set @{user.username} profile photo! 🖼️", "success")

    elif cmd == '/del_post' and arg1:
        post = Post.query.get(int(arg1)) if arg1.isdigit() else None
        if post:
            db.session.delete(post)
            db.session.commit()
            flash(f"Deleted Post #{arg1}! 🗑️", "success")

    elif cmd == '/post_likes' and arg1 and arg2:
        post = Post.query.get(int(arg1)) if arg1.isdigit() else None
        if post:
            post.fake_likes = arg2
            db.session.commit()
            flash(f"Set Post #{arg1} likes to {arg2}! 👍", "success")

    elif cmd == '/clear_posts' and arg1:
        user = User.query.filter_by(username=arg1).first()
        if user:
            Post.query.filter_by(user_id=user.id).delete()
            db.session.commit()
            flash(f"Cleared all posts for @{user.username}! 🧹", "success")

    elif cmd == '/pin_post' and arg1:
        post = Post.query.get(int(arg1)) if arg1.isdigit() else None
        if post:
            post.feed_type = 'official'
            db.session.commit()
            flash(f"Pinned Post #{arg1} to Official Feed! 📌", "success")

    elif cmd == '/del_comment' and arg1:
        comment = Comment.query.get(int(arg1)) if arg1.isdigit() else None
        if comment:
            db.session.delete(comment)
            db.session.commit()
            flash(f"Deleted Comment #{arg1}! 🗑️", "success")

    elif cmd == '/broadcast' and arg1:
        full_msg = f"{arg1} {arg2 or ''}".strip()
        all_users = User.query.all()
        for u in all_users:
            mail = Mail(sender_id=current_user.id, receiver_id=u.id, subject="📢 Official System Announcement", content=full_msg)
            db.session.add(mail)
        db.session.commit()
        flash("Broadcasted message to ALL players inbox! ✉️", "success")

    elif cmd == '/clear_inbox' and arg1:
        user = User.query.filter_by(username=arg1).first()
        if user:
            Mail.query.filter_by(receiver_id=user.id).delete()
            db.session.commit()
            flash(f"Cleared inbox for @{user.username}! 📭", "success")

    elif cmd == '/wipe_requests':
        VerificationRequest.query.filter_by(status='pending').delete()
        db.session.commit()
        flash("Wiped all pending verification requests! 🧹", "success")

    elif cmd == '/approve_all':
        pending = VerificationRequest.query.filter_by(status='pending').all()
        for req in pending:
            req.status = 'approved'
            u = User.query.get(req.user_id)
            if u:
                u.is_verified = True
        db.session.commit()
        flash("Approved all pending verification requests! ✅", "success")

    elif cmd == '/add_banned_word' and arg1:
        word = arg1.lower()
        if word not in BANNED_WORDS:
            BANNED_WORDS.append(word)
            flash(f"Added '{word}' to global profanity filter! 🚫", "success")

    elif cmd == '/reset_password' and arg1 and arg2:
        user = User.query.filter_by(username=arg1).first()
        if user:
            user.password_hash = generate_password_hash(arg2)
            db.session.commit()
            flash(f"Password reset for @{user.username}! 🔑", "success")

    elif cmd == '/server_info':
        u_count = User.query.count()
        p_count = Post.query.count()
        m_count = Mail.query.count()
        flash(f"Server Stats: {u_count} Users | {p_count} Posts | {m_count} Mails 📊", "info")

    elif cmd == '/reboot_db':
        init_database()
        flash("Re-initialized database schemas! ⚡", "success")

    else:
        flash(f"Command processed: {command_str} ✨", "info")

    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
