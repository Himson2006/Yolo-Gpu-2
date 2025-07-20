import os, json
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
    events = []
    if class_name_str:
        
        class_names = [name.strip() for name in class_name_str.split(',')]
        
        q = Event.query.join(Detection)
        class_filters = [Detection.classes_detected.any(name) for name in class_names]
        q = q.filter(or_(*class_filters))
        if min_count is not None and len(class_names) == 1:
            q = q.filter(
                cast(Detection.max_count_per_frame[class_names[0]].astext, Integer) >= min_count
            )
        events = q.all()
    return render_template("search.html", events=events, class_name=class_name_str, min_count=min_count)

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