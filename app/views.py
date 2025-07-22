import os, json
from datetime import datetime, timedelta
from flask import (
    Blueprint, request, current_app,
    render_template, redirect, url_for, send_from_directory, jsonify
)
from sqlalchemy import cast, Integer, or_
from app import db
from app.models import Event, Detection

main_bp = Blueprint("main", __name__)

@main_bp.route("/", methods=["GET"])
def index():
    return redirect(url_for("main.search_videos"))

@main_bp.route("/search", methods=["GET"])
def search_videos():
    class_name_str = request.args.get("class_name", type=str)
    min_count = request.args.get("min_count", type=int)
    start_date_str = request.args.get("start_date", type=str)
    end_date_str = request.args.get("end_date", type=str)
    device_id = request.args.get("device_id", type=str)
    events = []
    search_performed = False
    if class_name_str or min_count is not None or start_date_str or end_date_str or device_id:
        search_performed = True
        q = Event.query.join(Detection)

        # Apply class name and min count filters
        if class_name_str:
            class_names = [name.strip() for name in class_name_str.split(',')]
            class_filters = [Detection.classes_detected.any(name) for name in class_names]
            q = q.filter(or_(*class_filters))
            if min_count is not None and len(class_names) == 1:
                q = q.filter(
                    cast(Detection.max_count_per_frame[class_names[0]].astext, Integer) >= min_count
                )
        
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
        
        events = q.all()
    return render_template("search.html", events=events, class_name=class_name_str,
                           min_count=min_count, start_date=start_date_str,end_date=end_date_str,
                           device_id=device_id,
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