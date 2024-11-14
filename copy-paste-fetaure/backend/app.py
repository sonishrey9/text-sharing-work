# app.py
from flask import Flask, request, jsonify, render_template
import os

app = Flask(__name__)

# In-memory store for the text
shared_text = {"text": ""}

@app.route('/')
def index():
    """Render the HTML interface for real-time text sharing"""
    return render_template('index.html')

@app.route('/update', methods=['POST'])
def update_text():
    """Endpoint to update text from the HTML interface"""
    data = request.get_json()
    shared_text['text'] = data.get('text', '')
    return jsonify({"status": "success"}), 200

@app.route('/fetch', methods=['GET'])
def fetch_text():
    """Endpoint to fetch the latest text"""
    return jsonify({"text": shared_text['text']}), 200

if __name__ == "__main__":
    # Use the dynamic port provided by Heroku or default to 5000 for local testing
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

