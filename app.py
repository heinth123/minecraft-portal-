import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "minecraft_myanmar_super_secret_key_2026")

# Admin password to make posts
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "minecraft123")

# Local file to store your posts online
DATA_FILE = "posts.json"

def load_posts():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_posts(posts):
    with open(DATA_FILE, "w") as f:
        json.dump(posts, f, indent=4)

# ----------------- ROUTES -----------------

@app.route('/')
def home():
    posts = load_posts()
    # Reverse so newest posts appear first
    posts.reverse()
    return render_template('index.html', posts=posts)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash("Incorrect Password! Try again.", "danger")
    return render_template('login.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form.get('title')
        category = request.form.get('category') # Addon, News, Mod, Texture
        image_url = request.form.get('image_url')
        description = request.form.get('description')
        download_link = request.form.get('download_link')

        if title and description:
            posts = load_posts()
            new_post = {
                "id": len(posts) + 1,
                "title": title,
                "category": category,
                "image_url": image_url or "https://placehold.co/600x400/1e293b/22c55e?text=Minecraft+Myanmar",
                "description": description,
                "download_link": download_link
            }
            posts.append(new_post)
            save_posts(posts)
            flash("Post published successfully! 🎉", "success")
            return redirect(url_for('home'))

    return render_template('admin.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
