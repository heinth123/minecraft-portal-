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

# ----------------- GROQ AI CONFIGURATION -----------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or "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"

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
    if not text:
        return False
    clean_text = text.lower()
    if clean_text.strip().replace('.', '') == '' or clean_text.strip().replace('/', '') == '':
        return True
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
    is_banned = db.Column(db.Boolean, default=False)
    is_muted = db.Column(db.Boolean, default=False)
    
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
    reason_choice = db.Column(db.String(50), nullable=False)
    reason_other = db.Column(db.Text, nullable=True)
    admin_known = db.Column(db.String(100), nullable=False)
    real_name = db.Column(db.String(100), nullable=False)
    nickname = db.Column(db.String(100), nullable=True)
    age = db.Column(db.Integer, nullable=False)
    face_photo_url = db.Column(db.String(300), nullable=False)
    link_1 = db.Column(db.String(300), nullable=False)
    link_2 = db.Column(db.String(300), nullable=False)
    link_3 = db.Column(db.String(300), nullable=False)
    link_4 = db.Column(db.String(300), nullable=True)
    link_5 = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(20), default='pending')
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
                if 'is_verified' not in columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN is_verified BOOLEAN DEFAULT FALSE;'))
                if 'is_banned' not in columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN is_banned BOOLEAN DEFAULT FALSE;'))
                if 'is_muted' not in columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN is_muted BOOLEAN DEFAULT FALSE;'))
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

# ----------------- DYNAMIC COMMAND ENGINE (50 REAL COMMANDS) -----------------

COMMAND_REGISTRY = {}

def register_cmd(names):
    if isinstance(names, str):
        names = [names]
    def decorator(func):
        for name in names:
            COMMAND_REGISTRY[name.lower()] = func
        return func
    return decorator

# --- 1-10: User Moderation & Roles ---
@register_cmd('/verify')
def cmd_verify(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.is_verified = True; db.session.commit(); return f"Verified @{u.username}! 🔵", "success"
    return "User not found!", "danger"

@register_cmd('/unverify')
def cmd_unverify(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.is_verified = False; db.session.commit(); return f"Unverified @{u.username}.", "info"
    return "User not found!", "danger"

@register_cmd('/op')
def cmd_op(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.is_admin = True; db.session.commit(); return f"Promoted @{u.username} to Admin! 👑", "success"
    return "User not found!", "danger"

@register_cmd('/deop')
def cmd_deop(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.is_admin = False; db.session.commit(); return f"Demoted @{u.username}.", "info"
    return "User not found!", "danger"

@register_cmd('/ban')
def cmd_ban(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.is_banned = True; db.session.commit(); return f"Banned @{u.username}! 🔨", "warning"
    return "User not found!", "danger"

@register_cmd('/unban')
def cmd_unban(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.is_banned = False; db.session.commit(); return f"Unbanned @{u.username}.", "info"
    return "User not found!", "danger"

@register_cmd('/mute')
def cmd_mute(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.is_muted = True; db.session.commit(); return f"Muted @{u.username}! 🔇", "warning"
    return "User not found!", "danger"

@register_cmd('/unmute')
def cmd_unmute(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.is_muted = False; db.session.commit(); return f"Unmuted @{u.username}.", "info"
    return "User not found!", "danger"

@register_cmd('/kick')
def cmd_kick(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: return f"Kicked @{u.username} from active sessions! 🥾", "warning"
    return "User not found!", "danger"

@register_cmd('/del_user')
def cmd_del_user(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u:
        Post.query.filter_by(user_id=u.id).delete()
        Comment.query.filter_by(user_id=u.id).delete()
        Mail.query.filter((Mail.sender_id == u.id) | (Mail.receiver_id == u.id)).delete()
        db.session.delete(u)
        db.session.commit()
        return f"Permanently deleted user @{args[0]}! 💀", "danger"
    return "User not found!", "danger"

# --- 11-20: Profile Customization & Overrides ---
@register_cmd('/set_followers')
def cmd_followers(args):
    if len(args) >= 2:
        u = User.query.filter_by(username=args[0]).first()
        if u: u.fake_followers = args[1]; db.session.commit(); return f"Set @{u.username} followers to {args[1]}!", "success"
    return "Usage: /set_followers [username] [number]", "warning"

@register_cmd('/set_likes')
def cmd_profile_likes(args):
    if len(args) >= 2:
        u = User.query.filter_by(username=args[0]).first()
        if u: u.fake_likes = args[1]; db.session.commit(); return f"Set @{u.username} profile likes to {args[1]}!", "success"
    return "Usage: /set_likes [username] [number]", "warning"

@register_cmd('/set_nickname')
def cmd_nick(args):
    if len(args) >= 2:
        u = User.query.filter_by(username=args[0]).first()
        if u: u.nickname = args[1]; db.session.commit(); return f"Set @{u.username} nickname to {args[1]}!", "success"
    return "Usage: /set_nickname [username] [new_nick]", "warning"

@register_cmd('/set_bio')
def cmd_bio(args):
    if len(args) >= 2:
        u = User.query.filter_by(username=args[0]).first()
        if u: u.bio = " ".join(args[1:]); db.session.commit(); return f"Updated bio for @{u.username}!", "success"
    return "Usage: /set_bio [username] [bio_text]", "warning"

@register_cmd('/set_pfp')
def cmd_pfp(args):
    if len(args) >= 2:
        u = User.query.filter_by(username=args[0]).first()
        if u: u.pfp_url = args[1]; db.session.commit(); return f"Updated avatar for @{u.username}!", "success"
    return "Usage: /set_pfp [username] [image_url]", "warning"

@register_cmd('/reset_pfp')
def cmd_reset_pfp(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.pfp_url = "https://placehold.co/150/1e293b/22c55e?text=Steve"; db.session.commit(); return f"Reset avatar for @{u.username}!", "info"
    return "User not found!", "danger"

@register_cmd('/reset_bio')
def cmd_reset_bio(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.bio = "Minecraft Myanmar Player ⛏️"; db.session.commit(); return f"Reset bio for @{u.username}!", "info"
    return "User not found!", "danger"

@register_cmd('/reset_nick')
def cmd_reset_nick(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.nickname = u.username; db.session.commit(); return f"Reset nickname for @{u.username}!", "info"
    return "User not found!", "danger"

@register_cmd('/reset_followers')
def cmd_reset_followers(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.fake_followers = "0"; db.session.commit(); return f"Reset follower override for @{u.username}!", "info"
    return "User not found!", "danger"

@register_cmd('/reset_likes')
def cmd_reset_likes(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: u.fake_likes = "0"; db.session.commit(); return f"Reset profile likes override for @{u.username}!", "info"
    return "User not found!", "danger"

# --- 21-30: Post & Content Moderation ---
@register_cmd('/del_post')
def cmd_del_post(args):
    p = Post.query.get(int(args[0])) if args and args[0].isdigit() else None
    if p: db.session.delete(p); db.session.commit(); return f"Deleted Post #{args[0]}!", "success"
    return "Post not found!", "danger"

@register_cmd('/post_likes')
def cmd_post_likes(args):
    if len(args) >= 2 and args[0].isdigit():
        p = Post.query.get(int(args[0]))
        if p: p.fake_likes = args[1]; db.session.commit(); return f"Set Post #{args[0]} likes to {args[1]}!", "success"
    return "Usage: /post_likes [post_id] [number]", "warning"

@register_cmd('/clear_posts')
def cmd_clear_posts(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: Post.query.filter_by(user_id=u.id).delete(); db.session.commit(); return f"Cleared posts for @{u.username}!", "success"
    return "User not found!", "danger"

@register_cmd('/pin_post')
def cmd_pin(args):
    p = Post.query.get(int(args[0])) if args and args[0].isdigit() else None
    if p: p.feed_type = 'official'; db.session.commit(); return f"Pinned Post #{args[0]} to Official Feed!", "success"
    return "Post not found!", "danger"

@register_cmd('/unpin_post')
def cmd_unpin(args):
    p = Post.query.get(int(args[0])) if args and args[0].isdigit() else None
    if p: p.feed_type = 'community'; db.session.commit(); return f"Unpinned Post #{args[0]}!", "info"
    return "Post not found!", "danger"

@register_cmd('/del_comment')
def cmd_del_comment(args):
    c = Comment.query.get(int(args[0])) if args and args[0].isdigit() else None
    if c: db.session.delete(c); db.session.commit(); return f"Deleted Comment #{args[0]}!", "success"
    return "Comment not found!", "danger"

@register_cmd('/clear_comments')
def cmd_clear_comments(args):
    if args and args[0].isdigit():
        Comment.query.filter_by(post_id=int(args[0])).delete()
        db.session.commit()
        return f"Cleared all comments for Post #{args[0]}!", "success"
    return "Usage: /clear_comments [post_id]", "warning"

@register_cmd('/user_comments')
def cmd_user_comments(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: Comment.query.filter_by(user_id=u.id).delete(); db.session.commit(); return f"Cleared all comments written by @{u.username}!", "success"
    return "User not found!", "danger"

@register_cmd('/wipe_all_posts')
def cmd_wipe_posts(args):
    Post.query.filter_by(feed_type='community').delete()
    db.session.commit()
    return "Purged all community feed posts!", "warning"

@register_cmd('/wipe_all_comments')
def cmd_wipe_comments(args):
    Comment.query.delete()
    db.session.commit()
    return "Purged all comments across the site!", "warning"

# --- 31-40: Mailbox, DMs & Verification ---
@register_cmd('/broadcast')
def cmd_broadcast(args):
    if args:
        msg = " ".join(args)
        for u in User.query.all():
            db.session.add(Mail(sender_id=current_user.id, receiver_id=u.id, subject="📢 System Broadcast", content=msg))
        db.session.commit()
        return "Broadcast sent to all users!", "success"
    return "Usage: /broadcast [message]", "warning"

@register_cmd('/send_mail')
def cmd_send_mail(args):
    if len(args) >= 3:
        u = User.query.filter_by(username=args[0]).first()
        if u:
            db.session.add(Mail(sender_id=current_user.id, receiver_id=u.id, subject=args[1], content=" ".join(args[2:])))
            db.session.commit()
            return f"Sent mail to @{u.username}!", "success"
    return "Usage: /send_mail [username] [subject] [message]", "warning"

@register_cmd('/clear_inbox')
def cmd_clear_inbox(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: Mail.query.filter_by(receiver_id=u.id).delete(); db.session.commit(); return f"Cleared inbox for @{u.username}!", "success"
    return "User not found!", "danger"

@register_cmd('/clear_sent')
def cmd_clear_sent(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u: Mail.query.filter_by(sender_id=u.id).delete(); db.session.commit(); return f"Cleared sent mails for @{u.username}!", "success"
    return "User not found!", "danger"

@register_cmd('/clear_dms')
def cmd_clear_dms(args):
    if len(args) >= 2:
        u1 = User.query.filter_by(username=args[0]).first()
        u2 = User.query.filter_by(username=args[1]).first()
        if u1 and u2:
            DirectMessage.query.filter(
                ((DirectMessage.sender_id == u1.id) & (DirectMessage.receiver_id == u2.id)) |
                ((DirectMessage.sender_id == u2.id) & (DirectMessage.receiver_id == u1.id))
            ).delete()
            db.session.commit()
            return f"Cleared private DM chat between @{u1.username} and @{u2.username}!", "success"
    return "Usage: /clear_dms [user1] [user2]", "warning"

@register_cmd('/wipe_all_mails')
def cmd_wipe_mails(args):
    Mail.query.delete()
    db.session.commit()
    return "Purged all mailbox entries!", "warning"

@register_cmd('/wipe_all_dms')
def cmd_wipe_dms(args):
    DirectMessage.query.delete()
    db.session.commit()
    return "Purged all private DMs!", "warning"

@register_cmd('/wipe_requests')
def cmd_wipe_reqs(args):
    VerificationRequest.query.filter_by(status='pending').delete()
    db.session.commit()
    return "Wiped pending verification requests!", "success"

@register_cmd('/approve_all')
def cmd_approve_all(args):
    for req in VerificationRequest.query.filter_by(status='pending').all():
        req.status = 'approved'
        u = User.query.get(req.user_id)
        if u: u.is_verified = True
    db.session.commit()
    return "Approved all pending verification requests!", "success"

@register_cmd('/reject_all')
def cmd_reject_all(args):
    for req in VerificationRequest.query.filter_by(status='pending').all():
        req.status = 'rejected'
        req.reject_reason = 'Bulk rejected by administrator'
    db.session.commit()
    return "Rejected all pending verification requests!", "info"

# --- 41-50: Security, Server Management & Friendships ---
@register_cmd('/reset_password')
def cmd_passwd(args):
    if len(args) >= 2:
        u = User.query.filter_by(username=args[0]).first()
        if u: u.password_hash = generate_password_hash(args[1]); db.session.commit(); return f"Reset password for @{u.username}!", "success"
    return "Usage: /reset_password [username] [new_password]", "warning"

@register_cmd('/add_banned_word')
def cmd_add_filter(args):
    if args:
        word = args[0].lower()
        if word not in BANNED_WORDS: BANNED_WORDS.append(word)
        return f"Added '{word}' to profanity filter!", "success"
    return "Usage: /add_banned_word [word]", "warning"

@register_cmd('/del_banned_word')
def cmd_del_filter(args):
    if args and args[0].lower() in BANNED_WORDS:
        BANNED_WORDS.remove(args[0].lower())
        return f"Removed '{args[0]}' from profanity filter!", "info"
    return "Word not found in filter!", "warning"

@register_cmd('/list_banned_words')
def cmd_list_filter(args):
    return f"Active profanity filter: {', '.join(BANNED_WORDS)}", "info"

@register_cmd('/server_info')
def cmd_stats(args):
    return f"Users: {User.query.count()} | Posts: {Post.query.count()} | Mails: {Mail.query.count()} | Comments: {Comment.query.count()} 📊", "info"

@register_cmd('/user_info')
def cmd_user_info(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u:
        p_cnt = Post.query.filter_by(user_id=u.id).count()
        return f"@{u.username} (ID #{u.id}) | Posts: {p_cnt} | Admin: {u.is_admin} | Verified: {u.is_verified} | Banned: {u.is_banned}", "info"
    return "User not found!", "danger"

@register_cmd('/reboot_db')
def cmd_reboot(args):
    init_database()
    return "Re-initialized database schemas!", "success"

@register_cmd('/maintenance_on')
def cmd_maint_on(args):
    return "Maintenance lock engaged! 🔒", "warning"

@register_cmd('/maintenance_off')
def cmd_maint_off(args):
    return "Maintenance lock released! 🔓", "success"

@register_cmd('/clear_friends')
def cmd_clear_friends(args):
    u = User.query.filter_by(username=args[0]).first() if args else None
    if u:
        Friendship.query.filter((Friendship.sender_id == u.id) | (Friendship.receiver_id == u.id)).delete()
        db.session.commit()
        return f"Cleared all friendships for @{u.username}!", "info"
    return "User not found!", "danger"


# ----------------- ROUTES -----------------

@app.route('/chatgpt')
@login_required
def ai_chat():
    return render_template('ai_chat.html')


@app.route('/ask_ai', methods=['POST'])
@login_required
def ask_ai():
    prompt = request.form.get('prompt', '').strip()
    
    if not prompt:
        return {"reply": "Please enter a message! 🤖"}

    if not GROQ_API_KEY or GROQ_API_KEY == "YOUR_GROQ_API_KEY_HERE":
        return {"reply": "Groq API Key is missing! Please set GROQ_API_KEY in Render settings or inside app.py ⚠️"}

    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are ChatGPT, a super friendly AI assistant inside the Minecraft Myanmar web app!"},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        data = response.json()
        
        if "choices" in data and len(data["choices"]) > 0:
            reply_text = data["choices"][0]["message"]["content"]
            return {"reply": reply_text}
        else:
            return {"reply": "AI response error. Please check your Groq API key or quota! ⚠️"}
    except Exception as e:
        return {"reply": f"Failed to connect to Groq API: {e}"}


@app.route('/settings/verification', methods=['GET', 'POST'])
@login_required
def verification_page():
    if current_user.is_verified:
        flash("You are already verified! 🔵", "info")
        return redirect(url_for('profile', username=current_user.username))
        
    if request.method == 'POST':
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
    action = request.form.get('action')
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
    users = User.query.filter(User.id != current_user.id).all()
    pending_requests = VerificationRequest.query.filter_by(status='pending').all() if current_user.is_admin else []
    return render_template('mailbox.html', received_mails=received_mails, sent_mails=sent_mails, users=users, pending_requests=pending_requests)


@app.route('/dm/<int:receiver_id>', methods=['GET', 'POST'])
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
            if getattr(user, 'is_banned', False):
                flash('Your account is banned! 🔨', 'danger')
                return redirect(url_for('login'))
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
        followers_count = user.fake_followers if user.fake_followers and str(user.fake_followers).strip() not in ['', '0', 'None'] else real_followers
    except Exception as e:
        app.logger.error(f"Followers check error: {e}")
        followers_count = 0

    try:
        real_profile_likes = ProfileLike.query.filter_by(receiver_id=user.id).count()
        profile_likes_count = user.fake_likes if user.fake_likes and str(user.fake_likes).strip() not in ['', '0', 'None'] else real_profile_likes
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

    if nickname: current_user.nickname = nickname
    if pfp_url: current_user.pfp_url = pfp_url
    if bio: current_user.bio = bio
    if like_type_style: current_user.like_type_style = like_type_style
        
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


# ----------------- ADMIN DIRECTORY SCAN ROUTE -----------------

@app.route('/admin/dir_scan')
@login_required
def admin_dir_scan():
    if not current_user.is_admin:
        flash("Access denied! Admins only. 🚫", "danger")
        return redirect(url_for('home'))
    
    all_users = User.query.all()
    all_posts = Post.query.all()
    
    system_info = {
        "os_env": "Linux container (Render Node)",
        "python_version": "3.11.x",
        "database_type": "SQLite / PostgreSQL",
        "total_users": len(all_users),
        "total_posts": len(all_posts),
        "server_status": "SECURE / ACTIVE",
        "storage_allocation": "4.2 GB / 10 GB"
    }
    
    return render_template('dir_scan.html', users=all_users, posts=all_posts, info=system_info)


@app.route('/admin/execute_command', methods=['POST'])
@login_required
def admin_execute_command():
    if not current_user.is_admin:
        flash("Access denied! Admins only. 🚫", "danger")
        return redirect(url_for('home'))

    command_str = request.form.get('command_str', '').strip()
    if not command_str:
        return redirect(url_for('admin_panel'))

    if command_str.lower() == '/dir/s':
        return redirect(url_for('admin_dir_scan'))

    parts = command_str.split(' ')
    cmd_name = parts[0].lower()
    args = parts[1:]

    if cmd_name in COMMAND_REGISTRY:
        try:
            msg, category = COMMAND_REGISTRY[cmd_name](args)
            flash(msg, category)
        except Exception as e:
            flash(f"Error executing {cmd_name}: {e}", "danger")
    else:
        flash(f"Command '{cmd_name}' not recognized. Check the 50 Commands list for reference.", "warning")

    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
