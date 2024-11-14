from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure random key

# Set the authentication password
AUTH_PASSWORD = "simple_use_case_hai_bhai_chatgpt_will_help"

# In-memory store for the text
shared_text = {"text": ""}

@app.route('/')
def index():
    """Render the login page if not authenticated, otherwise render the main interface"""
    if 'authenticated' in session:
        return render_template('index.html')
    else:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Render and handle the login form"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == AUTH_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            return "Incorrect password. Please try again.", 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Clear the session and redirect to the login page"""
    session.pop('authenticated', None)
    return redirect(url_for('login'))

@app.route('/update', methods=['POST'])
def update_text():
    """Endpoint to update text from the HTML interface"""
    if 'authenticated' not in session:
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    shared_text['text'] = data.get('text', '')
    return jsonify({"status": "success"}), 200

@app.route('/fetch', methods=['GET'])
def fetch_text():
    """Endpoint to fetch the latest text"""
    if 'authenticated' not in session:
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify({"text": shared_text['text']}), 200

if __name__ == "__main__":
    # Use the dynamic port provided by Heroku or default to 5000 for local testing
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
