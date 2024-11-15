from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory
import os
from io import BytesIO
from PIL import Image
import base64

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure random key

# Set the authentication password
AUTH_PASSWORD = "simple_use_case_hai_bhai_chatgpt_will_help"

# In-memory store for the text and images/files
shared_content = {
    "text": "",
    "images": [],
    "files": []
}

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
    shared_content['text'] = data.get('text', '')
    return jsonify({"status": "success"}), 200

@app.route('/fetch', methods=['GET'])
def fetch_content():
    """Endpoint to fetch the latest text, images, and files"""
    if 'authenticated' not in session:
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify(shared_content), 200

@app.route('/upload_image', methods=['POST'])
def upload_image():
    """Endpoint to upload an image"""
    if 'authenticated' not in session:
        return jsonify({"error": "Unauthorized"}), 403
    image_data = request.form.get('image')
    if image_data:
        # Decode base64 image
        image_data = image_data.split(",")[1]  # remove "data:image/png;base64,"
        image_bytes = base64.b64decode(image_data)
        image = Image.open(BytesIO(image_bytes))
        image.save(f"{UPLOAD_FOLDER}/screenshot_{len(shared_content['images'])}.png")
        shared_content['images'].append(f"screenshot_{len(shared_content['images'])}.png")
        return jsonify({"status": "success"}), 200
    return jsonify({"error": "No image provided"}), 400

@app.route('/upload_file', methods=['POST'])
def upload_file():
    """Endpoint to upload a file"""
    if 'authenticated' not in session:
        return jsonify({"error": "Unauthorized"}), 403
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files['file']
    filename = f"file_{len(shared_content['files'])}_{file.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    shared_content['files'].append(filename)
    return jsonify({"status": "success"}), 200

@app.route('/uploads/<filename>')
def download_file(filename):
    """Serve uploaded files"""
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == "__main__":
    # Use the dynamic port provided by Heroku or default to 5000 for local testing
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
