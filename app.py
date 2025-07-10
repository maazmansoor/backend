from flask import Flask, request, send_file, jsonify, url_for
import os
from werkzeug.utils import secure_filename
import datetime

# Import the analyze_video function from main.py
from main import analyze_video

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# Ensure the upload and output directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/analyze', methods=['POST'])
def handle_analysis_request():
    """Handles the video upload, analysis, and returns stats and video URL."""
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    video = request.files['video']
    
    if video.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if not video.filename or not allowed_file(video.filename):
        return jsonify({'error': 'Unsupported file type'}), 400
    
    # Create a unique filename to avoid conflicts
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    original_filename = secure_filename(video.filename)
    input_filename = f"{timestamp}_{original_filename}"
    output_filename = f"{timestamp}_processed_{original_filename}"
    
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
    
    video.save(input_path)
    
    try:
        # Call the refactored analysis function
        analysis_stats = analyze_video(input_path, output_path)
    except Exception as e:
        # Log the full error for debugging
        print(f"Error during video processing: {e}")
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500
    
    if not os.path.exists(output_path):
        return jsonify({'error': 'Analysis ran, but the output file was not created.'}), 500
        
    # Generate the full URL for the processed video
    video_url = url_for('get_processed_video', filename=output_filename, _external=True)

    # Combine stats and video URL into a single response
    response_data = {
        'message': 'Analysis complete',
        'processed_video_url': video_url,
        'analysis_data': analysis_stats
    }
    
    return jsonify(response_data), 200

@app.route('/videos/<filename>')
def get_processed_video(filename):
    """Serves the processed video files."""
    return send_file(os.path.join(app.config['OUTPUT_FOLDER'], filename), as_attachment=True)

@app.route('/')
def index():
    return 'Cricket Ball Tracking API. POST a video to /analyze.'

if __name__ == '__main__':
    # Use 0.0.0.0 to make the app accessible on your local network
    # use_reloader=False is important to prevent the server from restarting
    # due to the AI model loading, which can cause connection issues.
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False) 