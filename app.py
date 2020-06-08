import sqlite3
import os
from colour import Color
from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, session, send_from_directory
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import login_required, allowed_file
import imgpro

app = Flask(__name__)

# UPLOAD_FOLDER
app.config['UPLOAD_FOLDER'] = 'uploads/images'
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Create database file if it doesn't exist
DATABASE_NAME = 'main.db'
if not os.path.exists(DATABASE_NAME):
    with open(DATABASE_NAME, 'w'):
        pass

# Create table and index in database if it doesn't exist
conn = sqlite3.connect(DATABASE_NAME)
db = conn.cursor()
db.execute("\
    CREATE TABLE IF NOT EXISTS users (\
        username    TEXT    NOT NULL    UNIQUE,\
        hash        TEXT    NOT NULL\
        )\
;")
db.execute("\
    CREATE TABLE IF NOT EXISTS images (\
        user_rowid  INTEGER NOT NULL,\
        filename    TEXT    NOT NULL,\
        FOREIGN KEY(user_rowid) REFERENCES users(rowid)\
        )\
;")
conn.close()


@app.route('/')
def index():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    db = conn.cursor()
    rows = db.execute(
        "SELECT username, filename FROM users JOIN images ON users.rowid = images.user_rowid;"
    ).fetchall()
    conn.close()
    if session.get('user_id') is None:
        flash('Login or register to be able to upload')
    return render_template('index.html', data=rows)


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # Check if there is a file part
        if 'imagefile' not in request.files:
            flash('No file part')
            return render_template('upload.html')
        image_file = request.files['imagefile']
        # Check if there is a selected file
        if image_file.filename == '':
            flash('No selected file')
            return render_template('upload.html')
        # Check if file type is allowed
        if not allowed_file(image_file.filename):
            flash('file type not supported')
            return render_template('upload.html')
        if image_file:
            # Rename
            extension = image_file.filename.rsplit('.', 1)[1].lower()
            filename = "{}.{}".format(hash(datetime.now().timestamp()),
                                      extension)
            # Save file
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(path)
            image_file.close()
            # Process file
            color = request.form.get('imagebgcolor')
            color = Color(color)
            imgpro.centerSquareCrop(path)
            imgpro.asciiArt(path, path, bg=color.get_rgb())
            # Save filename and owner to database
            conn = sqlite3.connect(DATABASE_NAME)
            db = conn.cursor()
            db.execute(
                "INSERT INTO images(user_rowid, filename) VALUES (?, ?);",
                (session['user_id'], filename))
            conn.commit()
            conn.close()
            # Redirect to browse
            return redirect('/')
        flash('unknown error')

    return render_template('upload.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register user"""
    if request.method == 'POST':
        error = None
        # Get data
        username = request.form.get('username')
        password = request.form.get('password')
        confirmation = request.form.get('confirmation')

        # Data validation
        if not username:
            flash('must provide username')
            error = 'username'
        if password != confirmation:
            flash('password doesn\'t match confirmation')
            error = 'match'
        if not password:
            flash('must provide password')
            error = 'password'

        if error is not None:
            return render_template('register.html', error=error)

        # User registration is valid
        conn = sqlite3.connect(DATABASE_NAME)
        db = conn.cursor()

        db.execute("SELECT * FROM users WHERE username = ?;", (username, ))
        rows = db.fetchall()
        # Check if user already exists
        if len(rows) != 0:
            flash('Username is already taken. Please try again.')
            # Close connection
            conn.close()
            return render_template('register.html', error='duplicate')

        # Add user to database
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?);",
                   (username, generate_password_hash(password)))

        # Commit changes and close connection
        conn.commit()
        conn.close()

        # Success and redirect to login page
        return redirect('/login')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    if request.method == 'POST':
        # Get data
        username = request.form.get('username')
        password = request.form.get('password')

        error = None

        # Ensure username was submitted
        if not username:
            flash('must provide username')
            error = 'username'

        # Ensure password was submitted
        elif not password:
            flash('must provide password')
            error = 'password'

        if error is not None:
            return render_template('login.html', error=error)

        # Query database for username
        conn = sqlite3.connect(DATABASE_NAME)
        conn.row_factory = sqlite3.Row
        db = conn.cursor()
        db.execute('SELECT rowid, * FROM users WHERE username = ?',
                   (username, ))
        rows = db.fetchall()
        db.close()
        conn.close()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]['hash'],
                                                     password):
            flash('invalid username and/or password')
            return render_template('login.html', error='noexist')

        # Remember which user has logged in
        session['user_id'] = rows[0]['rowid']

        # Redirect user to home page
        return redirect('/')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to index
    return redirect('/')


@app.route('/uploads/images/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


if __name__ == '__main__':
    app.run()