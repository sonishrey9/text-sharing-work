from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import os
from werkzeug.utils import secure_filename

# Flask app initialization
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Replace with a secure random key

# SocketIO initialization with eventlet
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# Authentication password
AUTH_PASSWORD = "simple_use_case_hai_bhai_chatgpt_will_help"

# Shared text state
shared_text = {"text": ""}

# File upload configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'txt', 'pdf', 'docx'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Helper function to check allowed file types
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@app.route('/')
def index():
    if 'authenticated' in session:
        return render_template('index.html')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == AUTH_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        return "Incorrect password. Please try again.", 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'authenticated' not in session:
        return jsonify({"error": "Unauthorized"}), 403
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        file_url = url_for('uploaded_file', filename=filename)
        socketio.emit('file_shared', {"file_url": file_url, "file_name": filename})
        return jsonify({"file_url": file_url}), 200
    return jsonify({"error": "Invalid file type"}), 400

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# SocketIO events
@socketio.on('update_text')
def handle_update_text(data):
    shared_text['text'] = data.get('text', "")
    emit('text_update', shared_text['text'], broadcast=True)

@socketio.on('fetch_text')
def handle_fetch_text():
    emit('text_update', shared_text['text'])

@socketio.on('file_uploaded')
def handle_file_uploaded(data):
    emit('file_shared', data, broadcast=True)

# Main block to run the app
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
