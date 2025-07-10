import cv2
import numpy as np
from ultralytics import YOLO
from collections import deque
import math

# --- Model Loading ---
# Load YOLO models for bat, ball, stump, and pose detection
bat_model = YOLO('runs/detect/train/weights/best.pt')  # Path to bat detection model
ball_model = YOLO('runs/detect/train/weights/besst.pt')  # Path to ball detection model (ensure 'besst.pt' is correct)
stump_model = YOLO('runs/detect/train_stumps/weights/best.pt')  # Path to stump detection model
pose_model = YOLO('yolov8n-pose.pt')  # Pre-trained YOLOv8 pose model

# --- Dynamically Find Class Indices ---
# Find class indices for 'Stumps' and 'Ball' in their respective models
stump_class_index = next((k for k, v in stump_model.names.items() if v.lower() in ['stumps', 'stump']), 0)
ball_class_index = next((k for k, v in ball_model.names.items() if v.lower() in ['sports ball', 'ball', 'cricket_ball', 'cricket-ball']), -1)

print(f"Stump class index: {stump_class_index}, Ball class index: {ball_class_index}")

# --- Constants ---
STUMP_HEIGHT_METERS = 0.711  # Standard cricket stump height in meters
IMPACT_DISPLAY_FRAMES = 30  # Frames to display impact information
IMPACT_COOLDOWN_FRAMES = 15  # Minimum frames between consecutive impacts
FONT = cv2.FONT_HERSHEY_SIMPLEX  # Font for text overlay
MIN_SPEED_THRESHOLD = 15  # Minimum speed in km/h to consider an impact valid
MAX_SPEED_THRESHOLD = 250  # Maximum plausible speed in km/h
POWER_HIT_THRESHOLD = 100 # Speed in km/h to classify a "Power Hit"

# --- Global State (Reset for each analysis) ---
# It's better to manage state via a class or pass it through functions,
# but we'll reset globals for this refactoring.
def reset_analysis_state():
    """Resets all global variables to their initial state."""
    global pixels_per_meter, bat_history, ball_history, left_wrist_history, right_wrist_history
    global last_impact_frame, last_impact_speed, impact_count, last_impact_location, processing_stats
    
    pixels_per_meter = None
    bat_history = deque(maxlen=10)
    ball_history = deque(maxlen=10)
    left_wrist_history = deque(maxlen=10)
    right_wrist_history = deque(maxlen=10)
    last_impact_frame = -IMPACT_COOLDOWN_FRAMES - 1
    last_impact_speed = 0
    impact_count = 0
    last_impact_location = None
    processing_stats = {"frame_count": 0, "impacts": []}

# Initialize state
reset_analysis_state()


# --- Helper Functions ---

def get_power_hit_category(speed_kmh):
    """Categorizes the speed of a hit."""
    if speed_kmh > 150:
        return "Brutal Power"
    elif speed_kmh > 120:
        return "Excellent"
    elif speed_kmh > 80:
        return "Well-Timed Power"
    elif speed_kmh >= MIN_SPEED_THRESHOLD:
        return "Timing Shot"
    return "N/A"

def calculate_distance(p1, p2):
    """Calculate Euclidean distance between two points."""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def calculate_peak_speed(history, fps):
    """
    Calculates the PEAK speed from the last few frames to find the true power of a swing.
    This is more robust than averaging or using only two points.
    """
    if len(history) < 2 or pixels_per_meter is None:
        return 0
    
    max_speed = 0
    # Iterate through consecutive pairs of points in the history
    for i in range(len(history) - 1):
        (frame1, pos1), (frame2, pos2) = history[i], history[i+1]
        
        frame_diff = frame2 - frame1
        if frame_diff <= 0:
            continue
            
        pixel_dist = calculate_distance(pos1, pos2)
        time_interval = frame_diff / fps
        
        if time_interval <= 0:
            continue

        pixel_speed_per_sec = pixel_dist / time_interval
        meter_speed_per_sec = pixel_speed_per_sec / pixels_per_meter
        kmh = meter_speed_per_sec * 3.6
        
        if kmh > max_speed:
            max_speed = kmh
            
    return max_speed

def detect_stumps(frame):
    """Detect stumps in the frame and return the height of the best detection."""
    results = stump_model(frame, conf=0.25, verbose=False)
    if results and results[0].boxes:
        stump_boxes = [b for b in results[0].boxes if int(b.cls) == stump_class_index]
        if stump_boxes:
            best_stump = max(stump_boxes, key=lambda x: x.conf)
            return best_stump.xywh[0][3].item()  # Height in pixels
    return None

def setup_scaling_factor(cap):
    """Set up the scaling factor by detecting stumps in the first 150 frames."""
    print("--- Searching for stumps to set scale... ---")
    for i in range(150):
        success, frame = cap.read()
        if not success:
            break
        stump_height = detect_stumps(frame)
        if stump_height and stump_height > 20:  # Ensure detection is reasonable
            ppm = stump_height / STUMP_HEIGHT_METERS
            print(f"--- Scale Established (frame {i}): {ppm:.2f} px/m ---")
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Reset video to start
            return ppm
    print("--- Could not find stumps. Using default scale. ---")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return 100.0  # Default scale if stumps not found

def draw_scoreboard(frame, fps, current_speed, min_dist):
    """Draw a scoreboard overlay on the frame with analysis information."""
    h, w, _ = frame.shape
    overlay = np.zeros((70, w, 3), dtype=np.uint8)
    frame[0:70, 0:w] = cv2.addWeighted(frame[0:70, 0:w], 0.3, overlay, 0.7, 0)
    scale_status = "SET" if pixels_per_meter else "NOT SET"
    scale_color = (0, 255, 0) if pixels_per_meter else (0, 0, 255)
    impact_active = (processing_stats['frame_count'] - last_impact_frame) < IMPACT_DISPLAY_FRAMES
    impact_status = "IMPACT!" if impact_active else "---"
    impact_color = (0, 0, 255) if impact_active else (255, 255, 255)
    cv2.putText(frame, f"Scale: {scale_status}", (20, 25), FONT, 0.7, scale_color, 2)
    cv2.putText(frame, f"Impact: {impact_status}", (220, 25), FONT, 0.7, impact_color, 2)
    cv2.putText(frame, f"Speed: {current_speed:.1f} km/h", (420, 25), FONT, 0.7, (255, 255, 0), 2)
    cv2.putText(frame, f"Impact Speed: {last_impact_speed:.1f} km/h", (20, 55), FONT, 0.7, (50, 205, 255), 2)
    cv2.putText(frame, f"Shots: {impact_count}", (420, 55), FONT, 0.7, (255, 255, 255), 2)
    
    # Display "POWER HIT" if applicable
    if impact_active and last_impact_speed > POWER_HIT_THRESHOLD:
        cv2.putText(frame, "POWER HIT!", (650, 55), FONT, 0.7, (0, 0, 255), 2)

    if min_dist is not None:
        cv2.putText(frame, f"Min Dist: {min_dist:.1f}px", (650, 25), FONT, 0.7, (255, 0, 255), 2)

def detect_impact(bat_centers, ball_centers, fps, bat_history, left_wrist_history, right_wrist_history, threshold):
    """Detect bat-ball impact and calculate speed, with fallback to bat speed."""
    global last_impact_frame, last_impact_speed, impact_count, last_impact_location, processing_stats
    if not bat_centers or not ball_centers:
        return False, None
        
    frame_count = processing_stats['frame_count']
    if (frame_count - last_impact_frame) < IMPACT_COOLDOWN_FRAMES:
        return False, None
        
    min_distance = float('inf')
    impact_location = None
    for bat_center in bat_centers:
        for ball_center in ball_centers:
            distance = calculate_distance(bat_center, ball_center)
            if distance < min_distance:
                min_distance = distance
                impact_location = bat_center
                
    if min_distance < threshold:
        # Prioritize wrist speed, but fall back to bat speed for robustness
        speed_left = calculate_peak_speed(left_wrist_history, fps)
        speed_right = calculate_peak_speed(right_wrist_history, fps)
        
        # Always consider bat speed as a potential source for the hit's power
        bat_speed = calculate_peak_speed(bat_history, fps)
        
        current_speed = max(speed_left, speed_right, bat_speed)

        if MIN_SPEED_THRESHOLD < current_speed < MAX_SPEED_THRESHOLD:
            last_impact_speed = current_speed
            last_impact_frame = frame_count
            impact_count += 1
            last_impact_location = impact_location
            
            # Store detailed impact data
            impact_data = {
                "frame": frame_count,
                "speed_kmh": round(current_speed, 2),
                "category": get_power_hit_category(current_speed),
                "location": impact_location
            }
            processing_stats["impacts"].append(impact_data)

            print(f"\n>>> IMPACT! Speed: {last_impact_speed:.1f} km/h at frame {frame_count}")
            # Clear histories to prevent immediate re-triggering
            left_wrist_history.clear()
            right_wrist_history.clear()
            bat_history.clear()
            return True, min_distance
            
    return False, min_distance

def analyze_video(input_path, output_path):
    """
    Process the video, save annotated video, and return analysis statistics.
    """
    # Reset state for a new analysis run
    reset_analysis_state()
    
    global pixels_per_meter, last_impact_frame, last_impact_speed, impact_count, last_impact_location, processing_stats
    
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"ERROR: Could not open video file {input_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Video Info: {w}x{h} @ {fps:.2f} FPS")
    
    out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))

    pixels_per_meter = setup_scaling_factor(cap)
    impact_distance_threshold = 0.5 * pixels_per_meter # Reduced for more precise impact timing

    print("--- Starting video processing ---")
    processing_stats['frame_count'] = 0
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        
        processing_stats['frame_count'] += 1
        annotated_frame = frame.copy()
        bat_centers, ball_centers = [], []
          
        # Bat Detection
        results_bat = bat_model(frame, conf=0.25, verbose=False) # Lowered confidence
        if results_bat and results_bat[0].boxes:
            for box in results_bat[0].boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                bat_center = ((x1 + x2) // 2, (y1 + y2) // 2)
                bat_centers.append(bat_center)
                bat_history.append((processing_stats['frame_count'], bat_center))
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 165, 255), 2)
                cv2.putText(annotated_frame, f"Bat ({box.conf.item():.2f})", (x1, y1 - 10), FONT, 0.5, (0, 165, 255), 2)
          
        # Ball Detection
        results_ball = ball_model(frame, conf=0.15, verbose=False) # Lowered confidence
        if results_ball and results_ball[0].boxes:
            detections = [b for b in results_ball[0].boxes if ball_class_index == -1 or int(b.cls) == ball_class_index]
            for box in detections:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                ball_center = ((x1 + x2) // 2, (y1 + y2) // 2)
                ball_centers.append(ball_center)
                # No need to add ball to history unless we track its trajectory
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                cv2.putText(annotated_frame, f"Ball ({box.conf.item():.2f})", (x1, y1 - 10), FONT, 0.5, (0, 255, 255), 2)
          
        # Pose Detection (Wrist Tracking)
        results_pose = pose_model(frame, verbose=False)
        if results_pose and results_pose[0].keypoints is not None and bat_centers:
            bat_center = bat_centers[0] # Assume primary bat
            min_dist_to_bat = float('inf')
            best_batsman_idx = -1

            # Find the person closest to the bat
            for i, person_kps_obj in enumerate(results_pose[0].keypoints):
                person_kps = person_kps_obj.data[0]
                left_wrist_conf = person_kps[9, 2] if len(person_kps) > 9 else 0
                right_wrist_conf = person_kps[10, 2] if len(person_kps) > 10 else 0
                
                dist = float('inf')
                if left_wrist_conf > 0.5:
                    dist = calculate_distance(bat_center, person_kps[9, :2])
                elif right_wrist_conf > 0.5:
                    dist = calculate_distance(bat_center, person_kps[10, :2])
                
                if dist < min_dist_to_bat:
                    min_dist_to_bat = dist
                    best_batsman_idx = i

            # If a batsman is linked, track their wrists
            if best_batsman_idx != -1:
                batsman_kps_tensor = results_pose[0].keypoints[best_batsman_idx].data[0]
                left_wrist = batsman_kps_tensor[9, :2] if len(batsman_kps_tensor) > 9 and batsman_kps_tensor[9, 2] > 0.5 else None
                right_wrist = batsman_kps_tensor[10, :2] if len(batsman_kps_tensor) > 10 and batsman_kps_tensor[10, 2] > 0.5 else None
                
                if left_wrist is not None:
                    left_wrist_history.append((processing_stats['frame_count'], left_wrist))
                    cv2.circle(annotated_frame, (int(left_wrist[0]), int(left_wrist[1])), 5, (255, 0, 0), -1)
                if right_wrist is not None:
                    right_wrist_history.append((processing_stats['frame_count'], right_wrist))
                    cv2.circle(annotated_frame, (int(right_wrist[0]), int(right_wrist[1])), 5, (0, 255, 0), -1)
        
        # Impact Detection
        impact_detected, min_dist = detect_impact(bat_centers, ball_centers, fps, bat_history, left_wrist_history, right_wrist_history, impact_distance_threshold)
        if impact_detected and last_impact_location:
            cv2.circle(annotated_frame, last_impact_location, 40, (0, 255, 0), 3)
        
        # Calculate current bat speed for display
        current_bat_speed = calculate_peak_speed(bat_history, fps)
        
        # Print live speed to CLI
        print(f"\rFrame: {processing_stats['frame_count']}, Live Bat Speed: {current_bat_speed:.1f} km/h", end="")

        # Draw scoreboard and annotations
        draw_scoreboard(annotated_frame, fps, current_bat_speed, min_dist)

        out.write(annotated_frame)
        # Only show window if running as script
        if __name__ == "__main__":
            cv2.imshow("Cricket Analysis", annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    # Cleanup
    cap.release()
    out.release()
    if __name__ == "__main__":
        cv2.destroyAllWindows()
    print(f"\nProcessing complete. Output saved to {output_path}")

    # --- Final Statistics ---
    final_stats = {
        "total_frames": processing_stats['frame_count'],
        "total_shots": impact_count,
        "impacts": processing_stats["impacts"]
    }

    if impact_count > 0:
        speeds = [imp['speed_kmh'] for imp in processing_stats['impacts']]
        final_stats["average_speed_kmh"] = round(sum(speeds) / len(speeds), 2)
        final_stats["max_speed_kmh"] = round(max(speeds), 2)
        final_stats["power_hit_category"] = get_power_hit_category(final_stats["max_speed_kmh"])
    
    return final_stats

def main():
    """Standalone script entry point."""
    input_path = 'Virat Kohli batting on a Green wicket _ Bold Diaries.mp4'
    output_path = 'cricket_analysis_final_4.mp4'
    stats = analyze_video(input_path, output_path)
    print("\n--- Analysis Report ---")
    import json
    print(json.dumps(stats, indent=4))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user.")



        