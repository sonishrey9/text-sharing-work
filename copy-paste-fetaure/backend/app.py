from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Replace with a secure random key

# Initialize SocketIO with gevent as async mode
socketio = SocketIO(app, async_mode="gevent")

# Set the authentication password
AUTH_PASSWORD = "simple_use_case_hai_bhai_chatgpt_will_help"

# In-memory store for the text
shared_text = {"text": ""}
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    if 'authenticated' in session:
        return render_template('index.html')
    else:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
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

    # Ensure the filename is safe
    filename = file.filename
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    file_url = url_for('uploaded_file', filename=filename)
    return jsonify({"file_url": file_url}), 200

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # Set as_attachment=True to prompt download
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@socketio.on('update_text')
def handle_update_text(data):
    shared_text['text'] = data['text']
    emit('text_update', shared_text['text'], broadcast=True)

@socketio.on('fetch_text')
def handle_fetch_text():
    emit('text_update', shared_text['text'])

@socketio.on('file_uploaded')
def handle_file_uploaded(data):
    emit('file_shared', data, broadcast=True)

# Main block to run the app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
