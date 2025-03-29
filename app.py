from flask import Flask, render_template, request, redirect, url_for, session, flash
import requests
from flask_mysqldb import MySQL
from flask_scss import Scss
import os
from functools import wraps


import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
Scss(app, static_dir='static', asset_dir='assets')

# Configure MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'  # Your MySQL username
app.config['MYSQL_PASSWORD'] = 'password'  # Your MySQL password (empty if no password)
app.config['MYSQL_DB'] = 'database name'


mysql = MySQL(app)

# Set a secret key for sessions
app.secret_key = os.urandom(24)

UPLOAD_FOLDER = 'static/uploads/avatars'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):  # Check if the user is logged in
            return redirect(url_for('login'))  # Redirect to login page if not logged in
        return f(*args, **kwargs)
    return decorated_function

# Route: Homepage
@app.route('/')
def home():
    if 'user_id' in session:  # If user is logged in
        return render_template('index.html', logged_in=True)
    else:
        return render_template('index.html', logged_in=False)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))
# Route: Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Check user credentials
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, email, avatar_path FROM users WHERE email = %s AND password = %s", (email, password))
        user = cur.fetchone()
        cur.close()

        if user:
            # Store user info in session
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['email'] = user[2]
            session['avatar'] = user[3] if user[3] else 'images/default-avatar.jpg'  # Default avatar
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'error')
            return redirect(url_for('login'))

    return render_template('login.html')


# Directory to save uploaded avatars

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        avatar = request.files['avatar']

        # Save the avatar if it is valid
        avatar_path = None
        if avatar and allowed_file(avatar.filename):
            filename = secure_filename(avatar.filename)
            avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            avatar.save(avatar_path)
        
        # Save user data in the database
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cur.fetchone()

        if existing_user:
            return render_template('signup.html', error="User already exists with this email!")

        # Store the avatar's relative path in the database
        avatar_relative_path = avatar_path.replace('static/', '') if avatar_path else None
        cur.execute("INSERT INTO users (username, email, password, avatar_path) VALUES (%s, %s, %s, %s)", 
                    (username, email, password, avatar_relative_path))
        mysql.connection.commit()
        cur.close()

        return redirect(url_for('login'))

    return render_template('signup.html')

# Route: index (placeholder)
@app.route('/index')
def index():
    return render_template('index.html')



@app.route('/jobs', methods=['GET'])
@login_required
def jobs():
    try:
        # Get all search parameters
        what = request.args.get('what', '')
        where = request.args.get('where', '')
        salary_min = request.args.get('salary_min', '')
        contract_type = request.args.get('contract_type', '')
        
        # Build base API URL
        url = "https://api.adzuna.com/v1/api/jobs/gb/search/1"
        params = {
            'app_id': 'api id',
            'app_key': 'api key',
            'results_per_page': 20
        }
        
        # Add filters if provided
        if what:
            params['what'] = what
        if where:
            params['where'] = where
        if salary_min:
            params['salary_min'] = salary_min
        if contract_type:
            params['contract_type'] = contract_type
        
        # Make API request
        headers = {'User-Agent': 'SuJob/1.0'}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        jobs_list = data.get('results', [])
        
        return render_template('jobs.html', 
                            jobs=jobs_list,
                            search_what=what,
                            search_where=where,
                            search_salary=salary_min,
                            selected_contract_type=contract_type)
        
    except requests.exceptions.RequestException as e:
        print(f"API Error: {str(e)}")
        return render_template('jobs.html', 
                            jobs=[], 
                            error="Failed to fetch jobs. Please try again later.")

@app.route('/contact_us')
@login_required
def contact_us():
    return render_template('contact_us.html')







if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=3000)

