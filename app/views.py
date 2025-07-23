import os, json
from datetime import datetime, timedelta
from flask import (
    Blueprint, request, current_app,
    render_template, redirect, url_for, send_from_directory, jsonify
)
from sqlalchemy import cast, Integer, or_, extract, and_
from app import db
from app.models import Event, Detection

main_bp = Blueprint("main", __name__)

@main_bp.route("/", methods=["GET"])
def index():
    return redirect(url_for("main.search_videos"))

@main_bp.route("/search", methods=["GET"])
def search_videos():
    class_name_str = request.args.get("class_name", type=str)
    match_type = request.args.get("match_type", "any", type=str)
    min_count = request.args.get("min_count", type=int)
    start_date_str = request.args.get("start_date", type=str)
    end_date_str = request.args.get("end_date", type=str)
    device_id = request.args.get("device_id", type=str)
    time_of_day = request.args.get("time_of_day", type=str)
    min_confidence = request.args.get("min_confidence", type=float)
    sort_by = request.args.get("sort_by", "recent", type=str)
    events = []
    search_performed = False
    if class_name_str or min_count is not None or start_date_str or end_date_str or device_id or time_of_day or min_confidence is not None:
        search_performed = True
        q = Event.query.join(Detection)
        
        class_names = []
        # Apply class name and min count filters
        if class_name_str:
            class_names = [name.strip() for name in class_name_str.split(',') if name.strip()]
        
        if class_names:
            if min_count is not None and match_type == 'any':
                # Build a list of (species AND count) conditions
                individual_conditions = []
                for name in class_names:
                    condition = and_(
                        Detection.classes_detected.any(name),
                        Detection.max_count_per_frame[name].as_float() >= min_count
                    )
                    individual_conditions.append(condition)
                # Combine them with OR
                q = q.filter(or_(*individual_conditions))
            else:
                # Original logic for other cases
                if match_type == 'all':
                    q = q.filter(Detection.classes_detected.contains(class_names))
                else:
                    class_filters = [Detection.classes_detected.any(name) for name in class_names]
                    q = q.filter(or_(*class_filters))
                
                if min_count is not None and len(class_names) == 1:
                    q = q.filter(Detection.max_count_per_frame[class_names[0]].as_float() >= min_count)
        
        # Apply start date filter
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            q = q.filter(Event.timestamp_start_utc >= start_date)
    
        # Apply end date filter
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
            q = q.filter(Event.timestamp_start_utc < end_date)
        
        if device_id:
            q = q.filter(Event.device_id == device_id)
        
        if time_of_day == 'day':
            # Hour 6 (6:00am) up to, but not including, hour 18 (6:00pm)
            q = q.filter(extract('hour', Event.timestamp_start_utc).between(6, 17))
        elif time_of_day == 'night':
            # Hour 18 (6:00pm) or greater, OR hour 5 (5:59am) or less
            q = q.filter(or_(extract('hour', Event.timestamp_start_utc) >= 18, extract('hour', Event.timestamp_start_utc) <= 5))
        
        if min_confidence is not None:
            # This line queries the nested 'max_confidence' value within the JSONB field.
            # .as_float() ensures a numeric comparison.
            q = q.filter(Detection.detection_json['event_summary']['max_confidence'].as_float() >= min_confidence)
        
        if sort_by == 'oldest':
            q = q.order_by(Event.timestamp_start_utc.asc())
        elif sort_by == 'longest':
            q = q.order_by(Event.video_duration_seconds.desc())
        elif sort_by == 'shortest':
            q = q.order_by(Event.video_duration_seconds.asc())
        else: # Default to 'recent'
            q = q.order_by(Event.timestamp_start_utc.desc())
        
        events = q.all()
    return render_template("search.html", events=events, class_name=class_name_str,
                           min_count=min_count, start_date=start_date_str,end_date=end_date_str,
                           device_id=device_id,time_of_day=time_of_day,min_confidence=min_confidence,sort_by=sort_by,
                           match_type=match_type,
                           search_performed=search_performed)

@main_bp.route("/videos", methods=["GET"])
def list_videos():
    class_name_str = request.args.get("class_name", type=str)
    min_count = request.args.get("min_count", type=int)
    q = Event.query.join(Detection)
    events = []
    if class_name_str:
        class_names = [name.strip() for name in class_name_str.split(',') if name.strip()]
        if class_names:
            class_filters = [Detection.classes_detected.any(name) for name in class_names]
            q = q.filter(or_(*class_filters))
            
            if min_count is not None and len(class_names) == 1:
                q = q.filter(
                    cast(Detection.max_count_per_frame[class_names[0]].astext, Integer) >= min_count
                )
            events = q.all()
    else:
        events = Event.query.all()
        
    results = [{"id":e.event_id} for e in events]
    return jsonify(results)

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