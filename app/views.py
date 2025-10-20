import os, json
import io
from datetime import datetime, timedelta
from flask import (
    Blueprint, request, current_app,
    render_template, redirect, url_for, send_from_directory, jsonify, send_file, session
)
from sqlalchemy import cast, Integer, or_, extract, and_, func
from app import db
from app.models import Event, Detection, Behavior, BehaviorChoice
import zipfile
from app import login_required, admin_required
import plotly
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from itertools import combinations
from collections import defaultdict, Counter
import itertools

main_bp = Blueprint("main", __name__)

@main_bp.route("/", methods=["GET"])
def index():
    return redirect(url_for("main.search_videos"))

@main_bp.route("/search", methods=["GET"])
def search_videos():
    page = request.args.get("page", 1, type=int)
    class_name_str = request.args.get("class_name", type=str)
    match_type = request.args.get("match_type", "any", type=str)
    min_duration = request.args.get("min_duration", type=float)
    start_date_str = request.args.get("start_date", type=str)
    end_date_str = request.args.get("end_date", type=str)
    device_id = request.args.get("device_id", type=str)
    time_of_day = request.args.get("time_of_day", type=str)
    min_confidence = request.args.get("min_confidence", type=float)
    sort_by = request.args.get("sort_by", "recent", type=str)
    search_performed = bool(request.args)
    events = []
    
    selected_behavior = request.args.get('behavior', '')
    available_behaviors = db.session.query(Behavior.behavior_description).distinct().order_by(Behavior.behavior_description).all()
    available_behaviors = [b[0] for b in available_behaviors]

    q = Event.query.join(Detection)

    # --- Conditionally apply filters ONLY if criteria are provided ---
    if class_name_str:
        class_names_original = [name.strip() for name in class_name_str.split(',') if name.strip()]
        class_names_lower = [name.lower() for name in class_names_original]
        if class_names_lower:
            subq = db.session.query(Detection.event_id).distinct()
            unnested_func = func.unnest(func.coalesce(Detection.classes_modified, Detection.classes_detected))
            class_alias = unnested_func.label("class_name")
            lateral_join = db.select(class_alias).select_from(unnested_func).lateral()
            conditions = [func.lower(lateral_join.c.class_name).ilike(name) for name in class_names_lower]
            subq = subq.join(lateral_join, db.true()).filter(or_(*conditions))
            if match_type == 'all':
                subq = subq.group_by(Detection.event_id).having(func.count(func.distinct(func.lower(lateral_join.c.class_name))) == len(class_names_lower))
            q = q.filter(Event.event_id.in_(subq))

    if min_duration is not None:
        q = q.filter(Event.video_duration_seconds >= min_duration)

    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        q = q.filter(Event.timestamp_start_utc >= start_date)

    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
        q = q.filter(Event.timestamp_start_utc < end_date)

    if device_id:
        q = q.filter(Event.device_id == device_id)

    if time_of_day:
        if time_of_day == 'day':
            q = q.filter(extract('hour', Event.timestamp_start_utc).between(6, 17))
        elif time_of_day == 'night':
            q = q.filter(or_(extract('hour', Event.timestamp_start_utc) >= 18, extract('hour', Event.timestamp_start_utc) <= 5))

    if min_confidence is not None:
        q = q.filter(Detection.detection_json['event_summary']['max_confidence'].as_float() >= min_confidence)

    # --- Apply sorting to the final query ---
    if sort_by == 'oldest':
        q = q.order_by(Event.timestamp_start_utc.asc())
    elif sort_by == 'longest':
        q = q.order_by(Event.video_duration_seconds.desc())
    elif sort_by == 'shortest':
        q = q.order_by(Event.video_duration_seconds.asc())
    else: # Default to 'recent'
        q = q.order_by(Event.timestamp_start_utc.desc())
    
    if selected_behavior:
        q = q.join(Behavior).filter(Behavior.behavior_description == selected_behavior)

    pagination = q.paginate(page=page, per_page=30, error_out=False)
    events = pagination.items
    
    search_args = request.args.copy()
    search_args.pop('page', None)
    
    available_classes_query = db.session.query(Event.primary_species).distinct().order_by(Event.primary_species)
    available_classes = [item[0] for item in available_classes_query.all()]

    # --- Render the template ---
    return render_template("search.html", events=events, class_name=class_name_str, pagination=pagination,
                           min_duration=min_duration, start_date=start_date_str,end_date=end_date_str,
                           device_id=device_id,time_of_day=time_of_day,min_confidence=min_confidence,sort_by=sort_by,
                           match_type=match_type, search_args=search_args,
                           search_performed=search_performed, available_classes=available_classes, available_behaviors = available_behaviors
                           , selected_behavior=selected_behavior)
    
@main_bp.route("/api/behavior_choices", methods=["GET"])
def get_behavior_choices():
    choices = BehaviorChoice.query.order_by(BehaviorChoice.name).all()
    choices_names = [choice.name for choice in choices]
    return jsonify(choices_names)

@main_bp.route("/api/behavior_choices", methods=["POST"])
@admin_required
def add_behavior_choice():
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"success": False, "error": "Invalid request body"}), 400
    
    new_name = data['name'].strip()
    
    if not new_name:
        return jsonify({"success": False, "error": "Behavior name cannot be empty"}), 400
    
    existing = BehaviorChoice.query.filter_by(name=new_name).first()
    if existing:
        return jsonify({"success": False, "error": "Behavior choice already exists"}), 400
    
    try:
        new_choice = BehaviorChoice(name=new_name)
        db.session.add(new_choice)
        db.session.commit()
        return jsonify({"success": True, "name": new_choice.name}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding behavior choice: {e}")
        return jsonify({"success": False, "error": "Database error"}), 500

@main_bp.route("/add_behavior/<string:event_id>", methods=["POST"])
@admin_required
def add_behavior(event_id: str):
    """Admin-only route to add a behavior annotation to an event."""
    event = Event.query.get(event_id)
    if not event:
        return jsonify({"success": False, "error": "Event not found"}), 404

    data = request.get_json()
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    description = data.get('description')

    if not all([start_time, end_time, description]):
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    try:
        start_time_float = float(start_time)
        end_time_float = float(end_time)
    except ValueError:
        return jsonify({"success": False, "error": "Start and end times must be numbers"}), 400
    
    if end_time_float <= start_time_float:
        return jsonify({"success": False, "error": "End time must be after start time"}), 400

    try:
        new_behavior = Behavior(
            event_id=event_id,
            start_time_seconds=start_time_float,
            end_time_seconds=end_time_float,
            behavior_description=description.strip()
        )
        db.session.add(new_behavior)
        db.session.commit()
        
        ##  saving to JSON file ---
        
        json_filename = f"{event_id}.json"
        
        detections_directory = os.path.join(current_app.root_path, 'uploads', 'incoming', 'detections')
        json_file_path = os.path.join(detections_directory, json_filename)
        
        try:
            with open(json_file_path, 'r') as f:
                event_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return jsonify({"success": False, "error": f"JSON file not found or is invalid for event {event_id}."}), 404

        behavior_list = event_data.get('behaviors', [])
        
        new_behavior_dict = {
            'start_time_seconds': new_behavior.start_time_seconds,
            'end_time_seconds': new_behavior.end_time_seconds,
            'behavior_description': new_behavior.behavior_description
            
        }
        
        behavior_list.append(new_behavior_dict)
        event_data["behaviors"] = behavior_list
        
        with open(json_file_path, 'w') as f:
            json.dump(event_data, f, indent=4)
        
        return jsonify({
            "success": True,
            "message": "Behavior added successfully.",
            "behavior": {
                "id": new_behavior.id,
                "start": new_behavior.start_time_seconds,
                "end": new_behavior.end_time_seconds,
                "description": new_behavior.behavior_description
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding behavior for event {event_id}: {e}")
        return jsonify({"success": False, "error": "Database error"}), 500
    
@main_bp.route("/delete_behavior/<int:behavior_id>", methods = ["DELETE"])
@admin_required
def delete_behavior(behavior_id):
    behavior_to_delete = Behavior.query.get(behavior_id)
    if not behavior_to_delete:
        return jsonify({"success": False, "error": "behavior not found"}), 404
    
    event_id = behavior_to_delete.event_id
    
    try:
        db.session.delete(behavior_to_delete)
        db.session.commit()
        
        json_filename = f"{event_id}.json"
        detections_directory = os.path.join(current_app.root_path, 'uploads', 'incoming', 'detections')
        json_file_path = os.path.join(detections_directory, json_filename)
        
        if os.path.exists(json_file_path):
            with open (json_file_path, 'r') as f:
                event_data = json.load(f)
                
            behavior_list = event_data.get('behaviors', [])
            updated_behaviors = [b for b in behavior_list if not (b.get('start_time_seconds')== behavior_to_delete.start_time_seconds and b.get('behavior_description') == behavior_to_delete.behavior_description)]
            
            event_data['behaviors'] = updated_behaviors
            
            with open(json_file_path, 'w') as f:
                json.dump(event_data, f, indent=4)
                
        return jsonify({"success": True, "message": "Behavior deleted successfully."})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting behavior {behavior_id}: {e}")
        return jsonify({"success": False, "error": "An internal error occurred."}), 500

@main_bp.route("/change_class/<string:event_id>", methods=["POST"])
@admin_required
def change_class(event_id: str):
    """Admin-only route to modify the detected classes for an event."""
    event = Event.query.get(event_id)
    if not event or not event.detections:
        return jsonify({"success": False, "error": "Event not found"}), 404

    data = request.get_json()
    if not data or 'classes' not in data:
        return jsonify({"success": False, "error": "Invalid request body"}), 400

    new_classes_str = data.get('classes', '')
    new_classes_list = [s.strip() for s in new_classes_str.split(',') if s.strip()]

    try:
        event.detections.classes_modified = new_classes_list
        db.session.commit()
        
        json_filename = f"{event_id}.json"
        detections_directory = os.path.join(current_app.root_path, 'uploads', 'incoming', 'detections')
        json_file_path = os.path.join(detections_directory, json_filename)
        
        try:
            with open(json_file_path, 'r') as f:
                event_data = json.load(f)
        
        except (FileNotFoundError, json.JSONDecodeError):
            current_app.logger.error(f"Could not find or read JSON file to update classes for event {event_id}.")
            return jsonify({
                "success": True,
                "message": "Classes updated successfully in DB, but JSON file was not found.",
                "updated_classes": new_classes_list
            })
            
        event_data['classes_modified'] = new_classes_list
        
        with open(json_file_path, 'w') as f:
            json.dump(event_data, f, indent=4)
        
        return jsonify({
            "success": True, 
            "message": "Classes updated successfully.",
            "updated_classes": new_classes_list
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating classes for event {event_id}: {e}")
        return jsonify({"success": False, "error": "Database error"}), 500
    
@main_bp.route("/delete/<string:event_id>", methods=["DELETE"])
@admin_required
def delete_video(event_id: str):
    """Admin-only route to delete a video and its DB records."""
    event = Event.query.get(event_id)
    if not event:
        return jsonify({"success": False, "error": "Event not found"}), 404

    # Delete the video file
    try:
        video_path = os.path.join(current_app.config["WATCH_FOLDER"], f"{event.event_id}.mp4")
        if os.path.exists(video_path):
            os.remove(video_path)
    except OSError as e:
        # Log the error but proceed to delete the DB record anyway
        current_app.logger.error(f"Error deleting video file {video_path}: {e}")

    # Delete the database record (cascades to detections)
    try:
        db.session.delete(event)
        db.session.commit()
        return jsonify({"success": True, "message": f"Event {event_id} deleted."}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting event {event_id} from DB: {e}")
        return jsonify({"success": False, "error": "Database error"}), 500

@main_bp.route("/download/<string:event_id>", methods=["GET"])
@main_bp.route("/download/<string:event_id>.mp4", methods=["GET"])
def download_video(event_id: str):
    event = Event.query.get_or_404(event_id)
    return send_from_directory(
        current_app.config["WATCH_FOLDER"], f"{event.event_id}.mp4"
    )
    
@main_bp.route("/player/<string:event_id>.mp4")
@main_bp.route("/player/<string:event_id>")
def player_page(event_id):
    # renders a tiny HTML page whose only job is to play the video
    return render_template("player.html", event_id=event_id)

@main_bp.route("/download/batch")
def download_batch():
    """
    Takes a comma-separated list of event_ids, creates a zip file
    of the corresponding videos, and sends it to the user.
    """
    event_ids_str = request.args.get("ids")
    if not event_ids_str:
        return "No event IDs provided", 400

    event_ids = event_ids_str.split(',')

    # Use an in-memory file for the zip archive
    memory_file = io.BytesIO()

    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for event_id in event_ids:
            event = Event.query.get(event_id)
            if event:
                video_path = os.path.join(current_app.config["WATCH_FOLDER"], f"{event.event_id}.mp4")
                if os.path.exists(video_path):
                    # Add the file to the zip, using the event_id as the filename
                    zf.write(video_path, arcname=f"{event.event_id}.mp4")

    memory_file.seek(0)

    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='videos.zip'
    )

@main_bp.route('/api/class_distribution', methods=['GET'])
def class_distribution_data():
    """
    This endpoint provides data for the detected class distribution chart.
    It counts how many times each class (e.g., 'Deer', 'Car') has been detected.
    """
    unnested_classes = func.unnest(
        func.coalesce(Detection.classes_modified, Detection.classes_detected)
    ).label("class_name")

    counts = db.session.query(
        unnested_classes,
        func.count()
    ).group_by(unnested_classes).all()

    chart_data = {
        'labels': [item[0] for item in counts],
        'values': [item[1] for item in counts]
    }

    return jsonify(chart_data)

@main_bp.route('/dashboard')
def dashboard():
    """Renders the main dashboard page."""
    return render_template('dashboard.html')

@main_bp.route('/api/detections_over_time')
def detections_over_time_data():
    day_expression = func.date(Event.timestamp_start_utc).label("day")

    counts = db.session.query(
        day_expression,
        func.count(Event.event_id)
    ).group_by(day_expression).order_by(day_expression).all()

    # Using 'x' and 'y' is more conventional for Plotly line charts
    chart_data = {
        'x': [item[0].strftime('%Y-%m-%d') for item in counts],
        'y': [item[1] for item in counts]
    }
    
    return jsonify(chart_data)

@main_bp.route('/api/class_cooccurrence')
def class_cooccurrence_data():
    """
    Provides data for the class co-occurrence heatmap.
    This is a more complex data processing task done in Python.
    """
    # Fetch all class lists from the database.
    # We only care about events where there's more than one class detected.
    query = db.session.query(
        func.coalesce(Detection.classes_modified, Detection.classes_detected)
    ).filter(
        func.array_length(
            func.coalesce(Detection.classes_modified, Detection.classes_detected), 1
        ) > 1
    ).all()
    
    # query result is a list of lists, e.g., [['Deer', 'Squirrel'], ['Car', 'Person', 'Dog']]
    all_class_lists = [row[0] for row in query]

    # Count all pairs.
    # For each list, find all unique combinations of 2 classes.
    # e.g., ['A', 'B', 'C'] -> ('A', 'B'), ('A', 'C'), ('B', 'C')
    pair_counts = Counter()
    for class_list in all_class_lists:
        # Sort the list to ensure ('A', 'B') is the same as ('B', 'A')
        sorted_classes = sorted(list(set(class_list)))
        if len(sorted_classes) > 1:
            pairs = itertools.combinations(sorted_classes, 2)
            pair_counts.update(pairs)

    # Prepare the data structure for the heatmap.
    # We need a list of unique labels and a 2D matrix for the values.
    if not pair_counts:
        return jsonify({'x': [], 'y': [], 'z': []}) # Handle case with no pairs

    all_involved_classes = sorted(list(set(itertools.chain.from_iterable(pair_counts.keys()))))
    class_to_idx = {name: i for i, name in enumerate(all_involved_classes)}
    
    matrix_size = len(all_involved_classes)
    heatmap_matrix = [[0] * matrix_size for _ in range(matrix_size)]

    for pair, count in pair_counts.items():
        idx1 = class_to_idx[pair[0]]
        idx2 = class_to_idx[pair[1]]
        heatmap_matrix[idx1][idx2] = count
        heatmap_matrix[idx2][idx1] = count # The matrix is symmetrical

    chart_data = {
        'x': all_involved_classes,
        'y': all_involved_classes,
        'z': heatmap_matrix
    }

    return jsonify(chart_data)