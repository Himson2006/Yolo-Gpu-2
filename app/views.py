import os, json
import io
from datetime import datetime, timedelta
from flask import (
    Blueprint, request, current_app,
    render_template, redirect, url_for, send_from_directory, jsonify, send_file, session
)
from sqlalchemy import cast, Integer, or_, extract, and_, func
from app import db
from app.models import Event, Detection
import zipfile
from app import login_required

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

    q = Event.query.join(Detection)

    # --- Step 3: Conditionally apply filters ONLY if criteria are provided ---
    if class_name_str:
        class_names_original = [name.strip() for name in class_name_str.split(',') if name.strip()]
        class_names_lower = [name.lower() for name in class_names_original]
        if class_names_lower:
            subq = db.session.query(Detection.event_id).distinct()
            unnested_func = func.unnest(Detection.classes_detected)
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

    # --- Step 4: Apply sorting to the final query ---
    if sort_by == 'oldest':
        q = q.order_by(Event.timestamp_start_utc.asc())
    elif sort_by == 'longest':
        q = q.order_by(Event.video_duration_seconds.desc())
    elif sort_by == 'shortest':
        q = q.order_by(Event.video_duration_seconds.asc())
    else: # Default to 'recent'
        q = q.order_by(Event.timestamp_start_utc.desc())

    pagination = q.paginate(page=page, per_page=30, error_out=False)
    events = pagination.items
    
    search_args = request.args.copy()
    search_args.pop('page', None)

    # --- Step 6: Render the template ---
    # The template will now correctly handle all cases:
    # 1. Initial Load: search_performed=False, events=[] -> Shows "Please enter criteria"
    # 2. Empty Search: search_performed=True, events=[all] -> Shows all results
    # 3. No Results:   search_performed=True, events=[] -> Shows "No videos were found"
    return render_template("search.html", events=events, class_name=class_name_str, pagination=pagination,
                           min_duration=min_duration, start_date=start_date_str,end_date=end_date_str,
                           device_id=device_id,time_of_day=time_of_day,min_confidence=min_confidence,sort_by=sort_by,
                           match_type=match_type, search_args=search_args,
                           search_performed=search_performed)

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