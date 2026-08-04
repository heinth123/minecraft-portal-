import os
from datetime import datetime, timezone
from urllib.parse import unquote
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "minecraft_myanmar_super_secret_key_2026")

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
    """Returns True if text contains any banned words or invalid characters."""
    if not text:
        return False
    
    clean_text = text.lower()
    
    # Block dot-only or slash-only usernames/inputs
    if clean_text.strip().replace('.', '') == '' or clean_text.strip().replace('/', '') == '':
        return True

    # Check for banned words inside the text
    for word in BANNED_WORDS:
        if word in clean_text:
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
    
    fake_followers = db.Column(db.String(20), nullable=True, default="0")
    fake_likes = db.Column(db.String(20), nullable=True, default="0")
    like_type_style = db.Column(db.String(50), nullable=True, default="❤️ Classic Red")

    @property
    def safe_pfp(self):
        return self.pfp_url or "https://placehold.co/150/1e293b/22c55e?text=Steve"

    @property
    def safe_like_style(self):
        return self.like_type_style or "❤️ Classic Red"

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
                u = User(username=un, nickname=un, password_hash=generate_password_hash(pw), is_admin=True)
                db.session.add(u)
            else:
                u.is_admin = True

        db.session.commit()

init_database()

# ----------------- ROUTES -----------------

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

    received_mails = Mail.query.filter_by(receiver_id=current_user.id)\
        .order_by(Mail.created_at.desc()).all()
    
    sent_mails = Mail.query.filter_by(sender_id=current_user.id)\
        .order_by(Mail.created_at.desc()).all()

    all_other_users = User.query.filter(User.id != current_user.id).all()
    
    return render_template('mailbox.html', 
                           received_mails=received_mails, 
                           sent_mails=sent_mails, 
                           all_users=all_other_users)

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

        # 🛑 PROFANITY & INVALID CHAR CHECK
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

@app.route('/')
@login_required
def home():
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

    # 🛑 CHECK FOR BANNED WORDS IN POSTS
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
    if not username or username.strip() in ['.', '..', '']:
        flash("Invalid profile username! 😅", "danger")
        return redirect(url_for('home'))

    decoded_username = unquote(username).strip()
    user = User.query.filter(User.username.ilike(decoded_username)).first()
    
    if not user:
        flash(f"User '{decoded_username}' not found!", "danger")
        return redirect(url_for('home'))

    real_followers = Follow.query.filter_by(followed_id=user.id).count()
    real_profile_likes = ProfileLike.query.filter_by(receiver_id=user.id).count()
    is_following = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first() is not None
    user_posts = Post.query.filter_by(user_id=user.id).order_by(Post.id.desc()).all()
    
    friendship = Friendship.query.filter(
        ((Friendship.sender_id == current_user.id) & (Friendship.receiver_id == user.id)) |
        ((Friendship.sender_id == user.id) & (Friendship.receiver_id == current_user.id))
    ).first()
    
    return render_template(
        'profile.html',
        user=user,
        followers_count=user.fake_followers or real_followers,
        profile_likes_count=user.fake_likes or real_profile_likes,
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
    
    if contains_banned_words(nickname) or contains_banned_words(bio):
        flash('Your profile changes contained inappropriate words! 🚫', 'danger')
        return redirect(url_for('profile', username=current_user.username))

    if nickname:
        current_user.nickname = nickname
    if pfp_url:
        current_user.pfp_url = pfp_url
    if bio:
        current_user.bio = bio
        
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
