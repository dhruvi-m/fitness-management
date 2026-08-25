from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    send_from_directory,
    Response
)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from openai import OpenAI
from werkzeug.utils import secure_filename

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    Image as RLImage
)

import os
import re
import json
import csv
import io
import uuid


# ============================================================
# APP / PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fitness-management-secret")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fitness.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads", "clients")
REPORT_FOLDER = os.path.join(BASE_DIR, "reports", "clients")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)


# ============================================================
# HUGGING FACE
# ============================================================

HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen3-8B")

hf_client = None

if HF_TOKEN:
    hf_client = OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=HF_TOKEN
    )


# ============================================================
# MODELS
# ============================================================

class Client(db.Model):
    __tablename__ = "clients"

    client_id = db.Column(db.Integer, primary_key=True)
    client_code = db.Column(db.String(20), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(150), nullable=True)
    height_cm = db.Column(db.Float, nullable=True)
    starting_weight_kg = db.Column(db.Float, nullable=True)
    goal = db.Column(db.Text, nullable=True)
    medical_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkoutPlan(db.Model):
    __tablename__ = "workout_plans"

    workout_plan_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.client_id"), nullable=False)
    plan_name = db.Column(db.String(200), nullable=False)
    plan_type = db.Column(db.String(20), nullable=False)
    goal = db.Column(db.Text)
    experience_level = db.Column(db.String(50))
    days_per_week = db.Column(db.Integer)
    duration_minutes = db.Column(db.Integer)
    equipment = db.Column(db.Text)
    restrictions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    exercises = db.relationship(
        "WorkoutExercise",
        backref="workout_plan",
        cascade="all, delete-orphan",
        lazy=True
    )


class WorkoutExercise(db.Model):
    __tablename__ = "workout_exercises"

    exercise_id = db.Column(db.Integer, primary_key=True)
    workout_plan_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_plans.workout_plan_id"),
        nullable=False
    )
    day_name = db.Column(db.String(50), nullable=False)
    exercise_name = db.Column(db.String(150), nullable=False)
    sets = db.Column(db.Integer)
    reps = db.Column(db.String(50))
    duration_minutes = db.Column(db.Integer)
    rest_seconds = db.Column(db.Integer)
    notes = db.Column(db.Text)
    exercise_order = db.Column(db.Integer)


class DietPlan(db.Model):
    __tablename__ = "diet_plans"

    diet_plan_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.client_id"), nullable=False)
    plan_name = db.Column(db.String(200), nullable=False)
    plan_type = db.Column(db.String(20), nullable=False)
    goal = db.Column(db.Text)
    diet_type = db.Column(db.String(100))
    daily_calories = db.Column(db.Integer)
    protein_g = db.Column(db.Float)
    carbs_g = db.Column(db.Float)
    fat_g = db.Column(db.Float)
    meals_per_day = db.Column(db.Integer)
    cuisine = db.Column(db.String(100))
    restrictions = db.Column(db.Text)
    allergies = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    meals = db.relationship(
        "DietMeal",
        backref="diet_plan",
        cascade="all, delete-orphan",
        lazy=True
    )


class DietMeal(db.Model):
    __tablename__ = "diet_meals"

    meal_id = db.Column(db.Integer, primary_key=True)
    diet_plan_id = db.Column(
        db.Integer,
        db.ForeignKey("diet_plans.diet_plan_id"),
        nullable=False
    )
    day_name = db.Column(db.String(50), nullable=False)
    meal_type = db.Column(db.String(50), nullable=False)
    meal_name = db.Column(db.String(250), nullable=False)
    quantity = db.Column(db.String(100))
    calories = db.Column(db.Float)
    protein_g = db.Column(db.Float)
    carbs_g = db.Column(db.Float)
    fat_g = db.Column(db.Float)
    notes = db.Column(db.Text)
    meal_order = db.Column(db.Integer)


class ProgressUpdate(db.Model):
    __tablename__ = "progress_updates"

    progress_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.client_id"), nullable=False)
    update_type = db.Column(db.String(20), nullable=False)
    period_label = db.Column(db.String(100), nullable=False)
    update_date = db.Column(db.Date, nullable=False)
    weight_kg = db.Column(db.Float)
    body_fat_percent = db.Column(db.Float)
    chest_cm = db.Column(db.Float)
    waist_cm = db.Column(db.Float)
    hip_cm = db.Column(db.Float)
    arm_cm = db.Column(db.Float)
    thigh_cm = db.Column(db.Float)
    workout_adherence = db.Column(db.Float)
    diet_adherence = db.Column(db.Float)
    trainer_notes = db.Column(db.Text)
    include_analysis = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProgressPhoto(db.Model):
    __tablename__ = "progress_photos"

    photo_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.client_id"), nullable=False)
    update_type = db.Column(db.String(20))
    period_label = db.Column(db.String(100))
    photo_type = db.Column(db.String(30))
    file_path = db.Column(db.String(500))
    original_filename = db.Column(db.String(250))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProgressAnalysis(db.Model):
    __tablename__ = "progress_analyses"

    analysis_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.client_id"), nullable=False)
    score = db.Column(db.Float)
    status = db.Column(db.String(50))
    weight_change_kg = db.Column(db.Float)
    weight_change_percent = db.Column(db.Float)
    body_fat_change_percent = db.Column(db.Float)
    waist_change_cm = db.Column(db.Float)
    workout_adherence = db.Column(db.Float)
    diet_adherence = db.Column(db.Float)
    consistency_score = db.Column(db.Float)
    summary = db.Column(db.Text)
    strengths = db.Column(db.Text)
    areas_to_improve = db.Column(db.Text)
    recommendations = db.Column(db.Text)
    ai_generated = db.Column(db.Boolean, default=False)
    include_in_report = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ClientReport(db.Model):
    __tablename__ = "client_reports"

    report_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.client_id"), nullable=False)
    file_name = db.Column(db.String(300), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


# ============================================================
# HELPERS
# ============================================================

def clean_phone(phone):
    if not phone:
        return ""
    phone = re.sub(r"\D", "", phone)
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    return phone


def generate_client_code():
    last = Client.query.order_by(Client.client_id.desc()).first()
    return f"CL{(last.client_id + 1) if last else 1:04d}"


def to_float(value):
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def to_int(value):
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except Exception:
        return None


def parse_date(value):
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return date.today()


def safe_list(value):
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
        return [value] if value.strip() else []
    return []


def clean_ai_json(content):
    if not content:
        raise ValueError("AI returned empty response.")

    content = str(content).strip()

    if "<think>" in content:
        end = content.find("</think>")
        if end != -1:
            content = content[end + len("</think>"):].strip()

    if content.startswith("```json"):
        content = content[7:].strip()
    elif content.startswith("```"):
        content = content[3:].strip()

    if content.endswith("```"):
        content = content[:-3].strip()

    start = content.find("{")
    end = content.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("AI response does not contain JSON.")

    return json.loads(content[start:end + 1])


def normalize_workout_data(data):
    if not isinstance(data, dict):
        data = {}

    days = data.get("days", [])
    if not isinstance(days, list):
        days = []

    clean_days = []

    for day in days:
        if not isinstance(day, dict):
            continue

        exercises = day.get("exercises", [])
        if not isinstance(exercises, list):
            exercises = []

        clean_exercises = []

        for exercise in exercises:
            if not isinstance(exercise, dict):
                continue

            clean_exercises.append({
                "exercise_name": str(exercise.get("exercise_name", "Exercise")),
                "sets": to_int(exercise.get("sets")),
                "reps": str(exercise.get("reps", "")),
                "duration_minutes": to_int(exercise.get("duration_minutes")),
                "rest_seconds": to_int(exercise.get("rest_seconds")),
                "notes": str(exercise.get("notes", ""))
            })

        if clean_exercises:
            clean_days.append({
                "day_name": str(day.get("day_name", "Day")),
                "exercises": clean_exercises
            })

    if not clean_days:
        clean_days = [{
            "day_name": "Day 1",
            "exercises": [{
                "exercise_name": "Walking",
                "sets": None,
                "reps": "20 minutes",
                "duration_minutes": 20,
                "rest_seconds": 60,
                "notes": "Review before use."
            }]
        }]

    return {
        "plan_name": str(data.get("plan_name", "AI Workout Plan")),
        "goal": str(data.get("goal", "General fitness")),
        "days": clean_days
    }


def normalize_diet_data(data):
    if not isinstance(data, dict):
        data = {}

    meals = data.get("meals", [])

    if isinstance(meals, int):
        meals = []

    if isinstance(meals, str):
        try:
            meals = json.loads(meals)
        except Exception:
            meals = []

    if not isinstance(meals, list):
        meals = []

    clean_meals = []

    for meal in meals:
        if not isinstance(meal, dict):
            continue

        clean_meals.append({
            "day_name": str(meal.get("day_name", "Monday")),
            "meal_type": str(meal.get("meal_type", "Meal")),
            "meal_name": str(meal.get("meal_name", "Meal")),
            "quantity": str(meal.get("quantity", "")),
            "calories": to_float(meal.get("calories")),
            "protein_g": to_float(meal.get("protein_g")),
            "carbs_g": to_float(meal.get("carbs_g")),
            "fat_g": to_float(meal.get("fat_g")),
            "notes": str(meal.get("notes", ""))
        })

    if not clean_meals:
        clean_meals = [{
            "day_name": "Monday",
            "meal_type": "Breakfast",
            "meal_name": "AI generated meal",
            "quantity": "",
            "calories": None,
            "protein_g": None,
            "carbs_g": None,
            "fat_g": None,
            "notes": "Review before saving."
        }]

    return {
        "plan_name": str(data.get("plan_name", "AI Diet Plan")),
        "goal": str(data.get("goal", "General fitness")),
        "diet_type": str(data.get("diet_type", "Vegetarian")),
        "daily_calories": to_int(data.get("daily_calories")),
        "protein_g": to_float(data.get("protein_g")),
        "carbs_g": to_float(data.get("carbs_g")),
        "fat_g": to_float(data.get("fat_g")),
        "meals": clean_meals
    }


# ============================================================
# PROGRESS ANALYSIS
# ============================================================

def calculate_progress_analysis(client, records):
    ordered = sorted(records, key=lambda x: x.update_date)

    if not ordered:
        return {
            "score": 0,
            "status": "NO DATA",
            "starting_weight": client.starting_weight_kg,
            "current_weight": client.starting_weight_kg,
            "weight_change": None,
            "weight_percent": None,
            "starting_waist": None,
            "current_waist": None,
            "waist_change": None,
            "body_fat_change": None,
            "workout_average": None,
            "diet_average": None,
            "consistency": 0,
            "summary": "Add progress records to begin analysis.",
            "strengths": [],
            "areas": [],
            "recommendations": [
                "Add regular weekly or monthly progress measurements.",
                "Record weight, waist and adherence consistently."
            ]
        }

    first = ordered[0]
    latest = ordered[-1]

    starting_weight = (
        client.starting_weight_kg
        if client.starting_weight_kg is not None
        else first.weight_kg
    )

    current_weight = latest.weight_kg
    weight_change = None
    weight_percent = None

    if starting_weight is not None and current_weight is not None and starting_weight != 0:
        weight_change = current_weight - starting_weight
        weight_percent = (weight_change / starting_weight) * 100

    waist_values = [x.waist_cm for x in ordered if x.waist_cm is not None]
    starting_waist = waist_values[0] if waist_values else None
    current_waist = waist_values[-1] if waist_values else None
    waist_change = (
        current_waist - starting_waist
        if starting_waist is not None and current_waist is not None
        else None
    )

    bodyfat_values = [
        x.body_fat_percent for x in ordered
        if x.body_fat_percent is not None
    ]
    body_fat_change = (
        bodyfat_values[-1] - bodyfat_values[0]
        if len(bodyfat_values) >= 2
        else None
    )

    workout_values = [
        x.workout_adherence for x in ordered
        if x.workout_adherence is not None
    ]
    diet_values = [
        x.diet_adherence for x in ordered
        if x.diet_adherence is not None
    ]

    workout_average = (
        sum(workout_values) / len(workout_values)
        if workout_values else None
    )
    diet_average = (
        sum(diet_values) / len(diet_values)
        if diet_values else None
    )

    if len(ordered) >= 2:
        days = (ordered[-1].update_date - ordered[0].update_date).days
        expected = max(1, int(days / 7) + 1)
        consistency = min(100, len(ordered) / expected * 100)
    else:
        consistency = 50

    goal = (client.goal or "").lower()
    weight_loss_goal = any(word in goal for word in ["loss", "lose", "fat", "weight loss"])

    weight_score = 12.5

    if weight_percent is not None:
        if weight_loss_goal:
            if weight_percent < 0:
                weight_score = min(25, 12.5 + abs(weight_percent) * 6)
            elif weight_percent > 0:
                weight_score = max(0, 12.5 - weight_percent * 6)

    waist_score = 10
    if waist_change is not None and weight_loss_goal:
        if waist_change < 0:
            waist_score = min(20, 10 + abs(waist_change) * 3)
        elif waist_change > 0:
            waist_score = max(0, 10 - waist_change * 3)

    bodyfat_score = 10
    if body_fat_change is not None:
        if body_fat_change < 0:
            bodyfat_score = min(20, 10 + abs(body_fat_change) * 3)
        elif body_fat_change > 0:
            bodyfat_score = max(0, 10 - body_fat_change * 3)

    workout_score = workout_average * 0.15 if workout_average is not None else 7.5
    diet_score = diet_average * 0.15 if diet_average is not None else 7.5
    consistency_score = consistency * 0.05

    score = round(max(0, min(
        100,
        weight_score + waist_score + bodyfat_score +
        workout_score + diet_score + consistency_score
    )), 1)

    if score >= 90:
        status = "EXCELLENT"
    elif score >= 75:
        status = "VERY GOOD"
    elif score >= 60:
        status = "GOOD"
    elif score >= 40:
        status = "NEEDS IMPROVEMENT"
    else:
        status = "NEEDS ATTENTION"

    strengths = []
    areas = []

    if weight_change is not None:
        if weight_loss_goal and weight_change < 0:
            strengths.append("Weight is decreasing toward the goal.")
        elif weight_loss_goal and weight_change >= 0:
            areas.append("Weight has not decreased from baseline.")

    if waist_change is not None:
        if waist_change < 0:
            strengths.append("Waist measurement has reduced.")
        elif waist_change > 0:
            areas.append("Waist measurement has increased.")

    if body_fat_change is not None:
        if body_fat_change < 0:
            strengths.append("Body-fat percentage has decreased.")
        elif body_fat_change > 0:
            areas.append("Body-fat percentage has increased.")

    if workout_average is not None:
        if workout_average >= 85:
            strengths.append("Workout adherence is strong.")
        elif workout_average < 70:
            areas.append("Workout adherence needs improvement.")

    if diet_average is not None:
        if diet_average >= 85:
            strengths.append("Diet adherence is strong.")
        elif diet_average < 70:
            areas.append("Diet adherence needs improvement.")

    if not strengths:
        strengths.append("Progress tracking has started.")

    if not areas:
        areas.append("Continue monitoring the current trend.")

    recommendations = []

    if weight_loss_goal:
        recommendations.append(
            "Aim for steady, sustainable progress rather than aggressive restriction."
        )
        if diet_average is not None and diet_average < 80:
            recommendations.append(
                "Improve diet consistency before making the plan more restrictive."
            )
        if workout_average is not None and workout_average < 80:
            recommendations.append(
                "Improve workout consistency and progressive training before adding extra volume."
            )
        recommendations.append(
            "Keep recording weight and waist at consistent intervals."
        )
        recommendations.append(
            "Use the latest progress photos alongside measurements to check visual changes."
        )
    else:
        recommendations.extend([
            "Maintain consistent training and nutrition.",
            "Track weight and measurements regularly.",
            "Review the trend every 2-4 weeks."
        ])

    summary_parts = []

    if weight_change is not None:
        summary_parts.append(
            f"Weight changed by {weight_change:+.1f} kg."
        )

    if weight_percent is not None:
        summary_parts.append(
            f"Overall weight change is {weight_percent:+.2f}%."
        )

    if waist_change is not None:
        summary_parts.append(
            f"Waist changed by {waist_change:+.1f} cm."
        )

    summary_parts.append(
        f"Current progress score is {score:.0f}/100."
    )

    return {
        "score": score,
        "status": status,
        "starting_weight": starting_weight,
        "current_weight": current_weight,
        "weight_change": weight_change,
        "weight_percent": weight_percent,
        "starting_waist": starting_waist,
        "current_waist": current_waist,
        "waist_change": waist_change,
        "body_fat_change": body_fat_change,
        "workout_average": workout_average,
        "diet_average": diet_average,
        "consistency": round(consistency, 1),
        "summary": " ".join(summary_parts),
        "strengths": strengths,
        "areas": areas,
        "recommendations": recommendations
    }


def latest_for_client(client_id):
    workout = (
        WorkoutPlan.query
        .filter_by(client_id=client_id)
        .order_by(WorkoutPlan.created_at.desc())
        .first()
    )

    diet = (
        DietPlan.query
        .filter_by(client_id=client_id)
        .order_by(DietPlan.created_at.desc())
        .first()
    )

    progress = (
        ProgressUpdate.query
        .filter_by(client_id=client_id)
        .order_by(ProgressUpdate.update_date.desc())
        .first()
    )

    analysis = (
        ProgressAnalysis.query
        .filter_by(client_id=client_id)
        .order_by(ProgressAnalysis.created_at.desc())
        .first()
    )

    return workout, diet, progress, analysis


# ============================================================
# HOME / PHONE / CLIENT
# ============================================================

@app.route("/")
def home():
    clients = (
        Client.query
        .order_by(Client.created_at.desc())
        .all()
    )
    return render_template("index.html", clients=clients)


@app.route("/check-phone", methods=["POST"])
def check_phone():
    phone = clean_phone(request.form.get("phone", ""))

    if not phone:
        flash("Please enter a phone number.", "error")
        return redirect(url_for("home"))

    client = Client.query.filter_by(phone=phone).first()

    if client:
        return redirect(url_for("client_profile", client_id=client.client_id))

    return redirect(url_for("register_client", phone=phone))


@app.route("/register-client", methods=["GET", "POST"])
def register_client():
    phone = request.args.get("phone", "")

    if request.method == "POST":
        phone = clean_phone(request.form.get("phone", ""))

        existing = Client.query.filter_by(phone=phone).first()

        if existing:
            return redirect(
                url_for(
                    "client_profile",
                    client_id=existing.client_id
                )
            )

        client = Client(
            client_code=generate_client_code(),
            phone=phone,
            full_name=request.form.get("full_name"),
            gender=request.form.get("gender"),
            email=request.form.get("email"),
            height_cm=to_float(request.form.get("height_cm")),
            starting_weight_kg=to_float(
                request.form.get("starting_weight_kg")
            ),
            goal=request.form.get("goal"),
            medical_notes=request.form.get("medical_notes")
        )

        db.session.add(client)
        db.session.commit()

        return redirect(
            url_for(
                "client_profile",
                client_id=client.client_id
            )
        )

    return render_template(
        "register_client.html",
        phone=phone
    )


@app.route(
    "/client/<int:client_id>/edit",
    methods=["GET", "POST"]
)
def edit_client(client_id):
    client = db.get_or_404(Client, client_id)

    if request.method == "POST":
        new_phone = clean_phone(
            request.form.get("phone", "")
        )

        existing = (
            Client.query
            .filter(
                Client.phone == new_phone,
                Client.client_id != client_id
            )
            .first()
        )

        if existing:
            flash(
                "This phone number belongs to another client.",
                "error"
            )
            return redirect(
                url_for(
                    "edit_client",
                    client_id=client_id
                )
            )

        client.phone = new_phone
        client.full_name = request.form.get("full_name")
        client.gender = request.form.get("gender")
        client.email = request.form.get("email")
        client.height_cm = to_float(
            request.form.get("height_cm")
        )
        client.goal = request.form.get("goal")
        client.medical_notes = request.form.get("medical_notes")

        db.session.commit()

        flash(
            "Client information updated.",
            "success"
        )

        return redirect(
            url_for(
                "client_profile",
                client_id=client_id
            )
        )

    return render_template(
        "edit_client.html",
        client=client
    )


@app.post("/client/<int:client_id>/delete")
def delete_client(client_id):
    client = db.get_or_404(Client, client_id)

    WorkoutPlan.query.filter_by(client_id=client_id).delete(
        synchronize_session=False
    )
    DietPlan.query.filter_by(client_id=client_id).delete(
        synchronize_session=False
    )
    ProgressUpdate.query.filter_by(client_id=client_id).delete(
        synchronize_session=False
    )
    ProgressAnalysis.query.filter_by(client_id=client_id).delete(
        synchronize_session=False
    )
    ProgressPhoto.query.filter_by(client_id=client_id).delete(
        synchronize_session=False
    )

    reports = ClientReport.query.filter_by(client_id=client_id).all()

    for report in reports:
        path = os.path.join(BASE_DIR, report.file_path)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    ClientReport.query.filter_by(client_id=client_id).delete(
        synchronize_session=False
    )

    db.session.delete(client)
    db.session.commit()

    flash("Client deleted.", "success")
    return redirect(url_for("home"))


@app.route("/client/<int:client_id>")
def client_profile(client_id):
    client = db.get_or_404(Client, client_id)

    workouts = (
        WorkoutPlan.query
        .filter_by(client_id=client_id)
        .order_by(WorkoutPlan.created_at.desc())
        .all()
    )

    diets = (
        DietPlan.query
        .filter_by(client_id=client_id)
        .order_by(DietPlan.created_at.desc())
        .all()
    )

    progress = (
        ProgressUpdate.query
        .filter_by(client_id=client_id)
        .order_by(ProgressUpdate.update_date.desc())
        .all()
    )

    calculated = calculate_progress_analysis(
        client,
        progress
    )

    reports = (
        ClientReport.query
        .filter_by(client_id=client_id)
        .order_by(ClientReport.created_at.desc())
        .all()
    )

    latest_workout, latest_diet, latest_progress, latest_analysis = (
        latest_for_client(client_id)
    )

    return render_template(
        "client_profile.html",
        client=client,
        workout_plans=workouts,
        diet_plans=diets,
        progress_updates=progress,
        calculated=calculated,
        latest_progress=latest_progress,
        latest_workout=latest_workout,
        latest_diet=latest_diet,
        latest_analysis=latest_analysis,
        reports=reports
    )


# ============================================================
# WORKOUT
# ============================================================

@app.route("/client/<int:client_id>/workout")
def workout_home(client_id):
    client = db.get_or_404(Client, client_id)

    plans = (
        WorkoutPlan.query
        .filter_by(client_id=client_id)
        .order_by(WorkoutPlan.created_at.desc())
        .all()
    )

    return render_template(
        "workout.html",
        client=client,
        workout_plans=plans
    )


@app.route(
    "/client/<int:client_id>/workout/manual",
    methods=["GET", "POST"]
)
def manual_workout(client_id):
    client = db.get_or_404(Client, client_id)

    if request.method == "POST":
        plan = WorkoutPlan(
            client_id=client_id,
            plan_name=request.form.get("plan_name"),
            plan_type="MANUAL",
            goal=request.form.get("goal"),
            experience_level=request.form.get("experience_level"),
            days_per_week=to_int(
                request.form.get("days_per_week")
            ),
            duration_minutes=to_int(
                request.form.get("duration_minutes")
            ),
            equipment=request.form.get("equipment"),
            restrictions=request.form.get("restrictions")
        )

        db.session.add(plan)
        db.session.flush()

        count = to_int(
            request.form.get("exercise_count", "0")
        ) or 0

        for i in range(count):
            name = request.form.get(
                f"exercise_name_{i}"
            )

            if not name:
                continue

            db.session.add(
                WorkoutExercise(
                    workout_plan_id=plan.workout_plan_id,
                    day_name=request.form.get(
                        f"day_name_{i}"
                    ) or "Day",
                    exercise_name=name,
                    sets=to_int(
                        request.form.get(
                            f"sets_{i}"
                        )
                    ),
                    reps=request.form.get(
                        f"reps_{i}"
                    ),
                    duration_minutes=to_int(
                        request.form.get(
                            f"duration_{i}"
                        )
                    ),
                    rest_seconds=to_int(
                        request.form.get(
                            f"rest_{i}"
                        )
                    ),
                    notes=request.form.get(
                        f"notes_{i}"
                    ),
                    exercise_order=i + 1
                )
            )

        db.session.commit()

        flash(
            "Manual workout saved.",
            "success"
        )

        return redirect(
            url_for(
                "workout_home",
                client_id=client_id
            )
        )

    return render_template(
        "manual_workout.html",
        client=client
    )


@app.route(
    "/client/<int:client_id>/workout/ai",
    methods=["GET", "POST"]
)
def ai_workout(client_id):
    client = db.get_or_404(Client, client_id)

    if request.method == "GET":
        return render_template(
            "ai_workout.html",
            client=client
        )

    if not hf_client:
        flash(
            "Hugging Face token is not configured.",
            "error"
        )
        return redirect(
            url_for(
                "ai_workout",
                client_id=client_id
            )
        )

    goal = (
        request.form.get("goal")
        or client.goal
        or "General fitness"
    )

    experience = request.form.get(
        "experience",
        "Beginner"
    )

    days = request.form.get(
        "days_per_week",
        "5"
    )

    duration = request.form.get(
        "duration_minutes",
        "60"
    )

    equipment = request.form.get(
        "equipment",
        "Gym"
    )

    restrictions = request.form.get(
        "restrictions",
        "None"
    )

    prompt = f"""
/no_think

Create a practical workout plan.

Client:
Name: {client.full_name}
Goal: {goal}
Experience: {experience}
Days per week: {days}
Duration: {duration} minutes
Equipment: {equipment}
Restrictions: {restrictions}

Return ONLY JSON:
{{
  "plan_name": "string",
  "goal": "string",
  "days": [
    {{
      "day_name": "Monday",
      "exercises": [
        {{
          "exercise_name": "string",
          "sets": 3,
          "reps": "10-12",
          "duration_minutes": null,
          "rest_seconds": 60,
          "notes": "string"
        }}
      ]
    }}
  ]
}}
"""

    try:
        response = hf_client.chat.completions.create(
            model=HF_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a workout planner. Return JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.4,
            max_tokens=3000,
            response_format={"type": "json_object"}
        )

        data = clean_ai_json(
            response.choices[0].message.content
        )

        data = normalize_workout_data(data)

        return render_template(
            "ai_workout_preview.html",
            client=client,
            workout=data
        )

    except Exception as error:
        print("AI WORKOUT ERROR:", repr(error))

        flash(
            f"AI workout generation failed: {error}",
            "error"
        )

        return redirect(
            url_for(
                "ai_workout",
                client_id=client_id
            )
        )


@app.post("/client/<int:client_id>/workout/ai/save")
def save_ai_workout(client_id):
    try:
        data = json.loads(
            request.form.get("workout_json")
        )

        data = normalize_workout_data(data)

        plan = WorkoutPlan(
            client_id=client_id,
            plan_name=data["plan_name"],
            plan_type="AI",
            goal=data["goal"],
            experience_level="AI",
            days_per_week=len(data["days"])
        )

        db.session.add(plan)
        db.session.flush()

        order = 1

        for day in data["days"]:
            for exercise in day["exercises"]:
                db.session.add(
                    WorkoutExercise(
                        workout_plan_id=plan.workout_plan_id,
                        day_name=day["day_name"],
                        exercise_name=exercise["exercise_name"],
                        sets=exercise["sets"],
                        reps=exercise["reps"],
                        duration_minutes=exercise["duration_minutes"],
                        rest_seconds=exercise["rest_seconds"],
                        notes=exercise["notes"],
                        exercise_order=order
                    )
                )
                order += 1

        db.session.commit()

        flash(
            "AI workout saved.",
            "success"
        )

    except Exception as error:
        db.session.rollback()

        flash(
            f"Could not save AI workout: {error}",
            "error"
        )

    return redirect(
        url_for(
            "workout_home",
            client_id=client_id
        )
    )


@app.route(
    "/workout/<int:plan_id>/edit",
    methods=["GET", "POST"]
)
def edit_workout(plan_id):
    plan = db.get_or_404(WorkoutPlan, plan_id)
    client = db.get_or_404(Client, plan.client_id)

    if request.method == "POST":
        plan.plan_name = request.form.get("plan_name")
        plan.goal = request.form.get("goal")
        plan.experience_level = request.form.get(
            "experience_level"
        )
        plan.days_per_week = to_int(
            request.form.get("days_per_week")
        )
        plan.duration_minutes = to_int(
            request.form.get("duration_minutes")
        )
        plan.equipment = request.form.get("equipment")
        plan.restrictions = request.form.get("restrictions")

        WorkoutExercise.query.filter_by(
            workout_plan_id=plan.workout_plan_id
        ).delete(
            synchronize_session=False
        )

        count = to_int(
            request.form.get(
                "exercise_count",
                "0"
            )
        ) or 0

        for i in range(count):
            name = request.form.get(
                f"exercise_name_{i}"
            )

            if not name:
                continue

            db.session.add(
                WorkoutExercise(
                    workout_plan_id=plan.workout_plan_id,
                    day_name=request.form.get(
                        f"day_name_{i}"
                    ) or "Day",
                    exercise_name=name,
                    sets=to_int(
                        request.form.get(
                            f"sets_{i}"
                        )
                    ),
                    reps=request.form.get(
                        f"reps_{i}"
                    ),
                    duration_minutes=to_int(
                        request.form.get(
                            f"duration_{i}"
                        )
                    ),
                    rest_seconds=to_int(
                        request.form.get(
                            f"rest_{i}"
                        )
                    ),
                    notes=request.form.get(
                        f"notes_{i}"
                    ),
                    exercise_order=i + 1
                )
            )

        db.session.commit()

        flash(
            "Workout updated.",
            "success"
        )

        return redirect(
            url_for(
                "workout_home",
                client_id=client.client_id
            )
        )

    return render_template(
        "edit_workout.html",
        client=client,
        plan=plan
    )


@app.route("/workout/<int:plan_id>/pdf")
def workout_pdf(plan_id):
    plan = db.get_or_404(WorkoutPlan, plan_id)
    client = db.get_or_404(Client, plan.client_id)

    folder = os.path.join(
        REPORT_FOLDER,
        client.client_code
    )

    os.makedirs(folder, exist_ok=True)

    filename = (
        f"{client.client_code}_workout_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    full_path = os.path.join(
        folder,
        filename
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "WorkoutTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=22,
        textColor=colors.HexColor("#2563eb")
    )

    normal_style = ParagraphStyle(
        "WorkoutNormal",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13
    )

    doc = SimpleDocTemplate(
        full_path,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )

    story = [
        Paragraph("WORKOUT PLAN", title_style),
        Spacer(1, 10),
        Paragraph(
            f"<b>Client:</b> {client.full_name}",
            normal_style
        ),
        Paragraph(
            f"<b>Client ID:</b> {client.client_code}",
            normal_style
        ),
        Paragraph(
            f"<b>Phone:</b> {client.phone}",
            normal_style
        ),
        Spacer(1, 12),
        Paragraph(
            f"<b>{plan.plan_name}</b>",
            styles["Heading2"]
        ),
        Paragraph(
            f"Type: {plan.plan_type}",
            normal_style
        ),
        Paragraph(
            f"Goal: {plan.goal or '-'}",
            normal_style
        ),
        Paragraph(
            f"Days/week: {plan.days_per_week or '-'}",
            normal_style
        ),
        Paragraph(
            f"Duration: {plan.duration_minutes or '-'} minutes",
            normal_style
        ),
        Spacer(1, 12)
    ]

    rows = [["Day", "Exercise", "Sets", "Reps", "Rest"]]

    for exercise in sorted(
        plan.exercises,
        key=lambda x: x.exercise_order or 0
    ):
        rows.append([
            exercise.day_name or "-",
            exercise.exercise_name or "-",
            exercise.sets or "-",
            exercise.reps or "-",
            (
                f"{exercise.rest_seconds}s"
                if exercise.rest_seconds
                else "-"
            )
        ])

    table = Table(
        rows,
        repeatRows=1,
        colWidths=[
            28 * mm,
            75 * mm,
            18 * mm,
            28 * mm,
            22 * mm
        ]
    )

    table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#2563eb")
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.grey
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold"
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                8
            )
        ])
    )

    story.append(table)

    if plan.restrictions:
        story.extend([
            Spacer(1, 10),
            Paragraph(
                f"<b>Restrictions:</b> {plan.restrictions}",
                normal_style
            )
        ])

    doc.build(story)

    db.session.add(
        ClientReport(
            client_id=client.client_id,
            file_name=filename,
            file_path=os.path.relpath(
                full_path,
                BASE_DIR
            ).replace("\\", "/")
        )
    )
    db.session.commit()

    return send_file(
        full_path,
        as_attachment=True,
        download_name=filename
    )


@app.post("/workout/<int:plan_id>/delete")
def delete_workout(plan_id):
    plan = db.get_or_404(WorkoutPlan, plan_id)
    client_id = plan.client_id

    db.session.delete(plan)
    db.session.commit()

    flash(
        "Workout deleted.",
        "success"
    )

    return redirect(
        url_for(
            "workout_home",
            client_id=client_id
        )
    )


# ============================================================
# DIET
# ============================================================

@app.route("/client/<int:client_id>/diet")
def diet_home(client_id):
    client = db.get_or_404(Client, client_id)

    plans = (
        DietPlan.query
        .filter_by(client_id=client_id)
        .order_by(DietPlan.created_at.desc())
        .all()
    )

    return render_template(
        "diet.html",
        client=client,
        diet_plans=plans
    )


@app.route(
    "/client/<int:client_id>/diet/manual",
    methods=["GET", "POST"]
)
def manual_diet(client_id):
    client = db.get_or_404(Client, client_id)

    if request.method == "POST":
        plan = DietPlan(
            client_id=client_id,
            plan_name=request.form.get("plan_name"),
            plan_type="MANUAL",
            goal=request.form.get("goal"),
            diet_type=request.form.get("diet_type"),
            daily_calories=to_int(
                request.form.get("daily_calories")
            ),
            protein_g=to_float(
                request.form.get("protein_g")
            ),
            carbs_g=to_float(
                request.form.get("carbs_g")
            ),
            fat_g=to_float(
                request.form.get("fat_g")
            ),
            meals_per_day=to_int(
                request.form.get("meals_per_day")
            ),
            cuisine=request.form.get("cuisine"),
            restrictions=request.form.get("restrictions"),
            allergies=request.form.get("allergies")
        )

        db.session.add(plan)
        db.session.flush()

        count = to_int(
            request.form.get(
                "meal_count",
                "0"
            )
        ) or 0

        for i in range(count):
            name = request.form.get(
                f"meal_name_{i}"
            )

            if not name:
                continue

            db.session.add(
                DietMeal(
                    diet_plan_id=plan.diet_plan_id,
                    day_name=request.form.get(
                        f"meal_day_{i}"
                    ) or "Monday",
                    meal_type=request.form.get(
                        f"meal_type_{i}"
                    ) or "Meal",
                    meal_name=name,
                    quantity=request.form.get(
                        f"quantity_{i}"
                    ),
                    calories=to_float(
                        request.form.get(
                            f"calories_{i}"
                        )
                    ),
                    protein_g=to_float(
                        request.form.get(
                            f"meal_protein_{i}"
                        )
                    ),
                    carbs_g=to_float(
                        request.form.get(
                            f"meal_carbs_{i}"
                        )
                    ),
                    fat_g=to_float(
                        request.form.get(
                            f"meal_fat_{i}"
                        )
                    ),
                    notes=request.form.get(
                        f"meal_notes_{i}"
                    ),
                    meal_order=i + 1
                )
            )

        db.session.commit()

        flash(
            "Manual diet saved.",
            "success"
        )

        return redirect(
            url_for(
                "diet_home",
                client_id=client_id
            )
        )

    return render_template(
        "manual_diet.html",
        client=client
    )


@app.route(
    "/client/<int:client_id>/diet/ai",
    methods=["GET", "POST"]
)
def ai_diet(client_id):
    client = db.get_or_404(Client, client_id)

    if request.method == "GET":
        return render_template(
            "ai_diet.html",
            client=client
        )

    if not hf_client:
        flash(
            "Hugging Face token is not configured.",
            "error"
        )
        return redirect(
            url_for(
                "ai_diet",
                client_id=client_id
            )
        )

    goal = (
        request.form.get("goal")
        or client.goal
        or "General fitness"
    )

    diet_type = request.form.get(
        "diet_type",
        "Vegetarian"
    )

    calories = request.form.get(
        "daily_calories",
        "1800"
    )

    meals_per_day = request.form.get(
        "meals_per_day",
        "5"
    )

    cuisine = request.form.get(
        "cuisine",
        "Indian"
    )

    restrictions = request.form.get(
        "restrictions",
        "None"
    )

    allergies = request.form.get(
        "allergies",
        "None"
    )

    prompt = f"""
/no_think

Create a practical diet plan.

Client:
Name: {client.full_name}
Goal: {goal}
Diet type: {diet_type}
Calories: {calories}
Meals per day: {meals_per_day}
Cuisine: {cuisine}
Restrictions: {restrictions}
Allergies: {allergies}

Return ONLY JSON.
"meals" MUST be an ARRAY.

{{
  "plan_name": "string",
  "goal": "string",
  "diet_type": "string",
  "daily_calories": 1800,
  "protein_g": 120,
  "carbs_g": 180,
  "fat_g": 55,
  "meals": [
    {{
      "day_name": "Monday",
      "meal_type": "Breakfast",
      "meal_name": "Poha",
      "quantity": "1 bowl",
      "calories": 300,
      "protein_g": 8,
      "carbs_g": 45,
      "fat_g": 8,
      "notes": "Low oil"
    }}
  ]
}}
"""

    try:
        response = hf_client.chat.completions.create(
            model=HF_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a diet planner. "
                        "Return valid JSON only."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.4,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )

        data = clean_ai_json(
            response.choices[0].message.content
        )

        data = normalize_diet_data(data)

        return render_template(
            "ai_diet_preview.html",
            client=client,
            diet=data
        )

    except Exception as error:
        print("AI DIET ERROR:", repr(error))

        flash(
            f"AI diet generation failed: {error}",
            "error"
        )

        return redirect(
            url_for(
                "ai_diet",
                client_id=client_id
            )
        )


@app.post("/client/<int:client_id>/diet/ai/save")
def save_ai_diet(client_id):
    try:
        data = json.loads(
            request.form.get("diet_json")
        )

        data = normalize_diet_data(data)

        plan = DietPlan(
            client_id=client_id,
            plan_name=data["plan_name"],
            plan_type="AI",
            goal=data["goal"],
            diet_type=data["diet_type"],
            daily_calories=data["daily_calories"],
            protein_g=data["protein_g"],
            carbs_g=data["carbs_g"],
            fat_g=data["fat_g"],
            meals_per_day=len(data["meals"])
        )

        db.session.add(plan)
        db.session.flush()

        for i, meal in enumerate(data["meals"]):
            db.session.add(
                DietMeal(
                    diet_plan_id=plan.diet_plan_id,
                    day_name=meal["day_name"],
                    meal_type=meal["meal_type"],
                    meal_name=meal["meal_name"],
                    quantity=meal["quantity"],
                    calories=meal["calories"],
                    protein_g=meal["protein_g"],
                    carbs_g=meal["carbs_g"],
                    fat_g=meal["fat_g"],
                    notes=meal["notes"],
                    meal_order=i + 1
                )
            )

        db.session.commit()

        flash(
            "AI diet saved.",
            "success"
        )

    except Exception as error:
        db.session.rollback()

        flash(
            f"Could not save AI diet: {error}",
            "error"
        )

    return redirect(
        url_for(
            "diet_home",
            client_id=client_id
        )
    )


@app.route(
    "/diet/<int:plan_id>/edit",
    methods=["GET", "POST"]
)
def edit_diet(plan_id):
    plan = db.get_or_404(DietPlan, plan_id)
    client = db.get_or_404(Client, plan.client_id)

    if request.method == "POST":
        plan.plan_name = request.form.get("plan_name")
        plan.goal = request.form.get("goal")
        plan.diet_type = request.form.get("diet_type")
        plan.daily_calories = to_int(
            request.form.get("daily_calories")
        )
        plan.protein_g = to_float(
            request.form.get("protein_g")
        )
        plan.carbs_g = to_float(
            request.form.get("carbs_g")
        )
        plan.fat_g = to_float(
            request.form.get("fat_g")
        )
        plan.meals_per_day = to_int(
            request.form.get("meals_per_day")
        )
        plan.cuisine = request.form.get("cuisine")
        plan.restrictions = request.form.get("restrictions")
        plan.allergies = request.form.get("allergies")

        DietMeal.query.filter_by(
            diet_plan_id=plan.diet_plan_id
        ).delete(
            synchronize_session=False
        )

        count = to_int(
            request.form.get(
                "meal_count",
                "0"
            )
        ) or 0

        for i in range(count):
            name = request.form.get(
                f"meal_name_{i}"
            )

            if not name:
                continue

            db.session.add(
                DietMeal(
                    diet_plan_id=plan.diet_plan_id,
                    day_name=request.form.get(
                        f"meal_day_{i}"
                    ) or "Monday",
                    meal_type=request.form.get(
                        f"meal_type_{i}"
                    ) or "Meal",
                    meal_name=name,
                    quantity=request.form.get(
                        f"quantity_{i}"
                    ),
                    calories=to_float(
                        request.form.get(
                            f"calories_{i}"
                        )
                    ),
                    protein_g=to_float(
                        request.form.get(
                            f"meal_protein_{i}"
                        )
                    ),
                    carbs_g=to_float(
                        request.form.get(
                            f"meal_carbs_{i}"
                        )
                    ),
                    fat_g=to_float(
                        request.form.get(
                            f"meal_fat_{i}"
                        )
                    ),
                    notes=request.form.get(
                        f"meal_notes_{i}"
                    ),
                    meal_order=i + 1
                )
            )

        db.session.commit()

        flash(
            "Diet updated.",
            "success"
        )

        return redirect(
            url_for(
                "diet_home",
                client_id=client.client_id
            )
        )

    return render_template(
        "edit_diet.html",
        client=client,
        plan=plan
    )


@app.route("/diet/<int:plan_id>/pdf")
def diet_pdf(plan_id):
    plan = db.get_or_404(DietPlan, plan_id)
    client = db.get_or_404(Client, plan.client_id)

    folder = os.path.join(
        REPORT_FOLDER,
        client.client_code
    )

    os.makedirs(folder, exist_ok=True)

    filename = (
        f"{client.client_code}_diet_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    full_path = os.path.join(folder, filename)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DietTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=22,
        textColor=colors.HexColor("#059669")
    )

    normal_style = ParagraphStyle(
        "DietNormal",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13
    )

    doc = SimpleDocTemplate(
        full_path,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )

    story = [
        Paragraph("DIET PLAN", title_style),
        Spacer(1, 10),
        Paragraph(
            f"<b>Client:</b> {client.full_name}",
            normal_style
        ),
        Paragraph(
            f"<b>Client ID:</b> {client.client_code}",
            normal_style
        ),
        Paragraph(
            f"<b>Phone:</b> {client.phone}",
            normal_style
        ),
        Spacer(1, 12),
        Paragraph(
            f"<b>{plan.plan_name}</b>",
            styles["Heading2"]
        ),
        Paragraph(
            f"Type: {plan.plan_type}",
            normal_style
        ),
        Paragraph(
            f"Goal: {plan.goal or '-'}",
            normal_style
        ),
        Paragraph(
            f"Diet type: {plan.diet_type or '-'}",
            normal_style
        ),
        Paragraph(
            f"Daily calories: {plan.daily_calories or '-'}",
            normal_style
        ),
        Paragraph(
            f"Protein: {plan.protein_g or '-'} g",
            normal_style
        ),
        Paragraph(
            f"Carbs: {plan.carbs_g or '-'} g",
            normal_style
        ),
        Paragraph(
            f"Fat: {plan.fat_g or '-'} g",
            normal_style
        ),
        Spacer(1, 12)
    ]

    rows = [
        [
            "Day",
            "Meal",
            "Food",
            "Quantity",
            "Calories"
        ]
    ]

    for meal in sorted(
        plan.meals,
        key=lambda x: x.meal_order or 0
    ):
        rows.append([
            meal.day_name or "-",
            meal.meal_type or "-",
            meal.meal_name or "-",
            meal.quantity or "-",
            meal.calories or "-"
        ])

    table = Table(
        rows,
        repeatRows=1,
        colWidths=[
            25 * mm,
            28 * mm,
            70 * mm,
            30 * mm,
            25 * mm
        ]
    )

    table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#059669")
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.grey
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                8
            )
        ])
    )

    story.append(table)

    if plan.restrictions:
        story.append(
            Paragraph(
                f"<b>Restrictions:</b> {plan.restrictions}",
                normal_style
            )
        )

    if plan.allergies:
        story.append(
            Paragraph(
                f"<b>Allergies:</b> {plan.allergies}",
                normal_style
            )
        )

    doc.build(story)

    db.session.add(
        ClientReport(
            client_id=client.client_id,
            file_name=filename,
            file_path=os.path.relpath(
                full_path,
                BASE_DIR
            ).replace("\\", "/")
        )
    )
    db.session.commit()

    return send_file(
        full_path,
        as_attachment=True,
        download_name=filename
    )


@app.post("/diet/<int:plan_id>/delete")
def delete_diet(plan_id):
    plan = db.get_or_404(DietPlan, plan_id)
    client_id = plan.client_id

    db.session.delete(plan)
    db.session.commit()

    flash(
        "Diet deleted.",
        "success"
    )

    return redirect(
        url_for(
            "diet_home",
            client_id=client_id
        )
    )


# ============================================================
# PROGRESS
# ============================================================

@app.route(
    "/client/<int:client_id>/progress"
)
def progress_home(client_id):
    client = db.get_or_404(Client, client_id)

    records = (
        ProgressUpdate.query
        .filter_by(client_id=client_id)
        .order_by(ProgressUpdate.update_date.asc())
        .all()
    )

    calculated = calculate_progress_analysis(
        client,
        records
    )

    analysis = (
        ProgressAnalysis.query
        .filter_by(client_id=client_id)
        .order_by(ProgressAnalysis.created_at.desc())
        .first()
    )

    return render_template(
        "progress.html",
        client=client,
        progress_updates=list(reversed(records)),
        calculated=calculated,
        analysis=analysis,
        chart_labels=[
            x.period_label
            for x in records
        ],
        chart_weights=[
            x.weight_kg
            for x in records
        ]
    )


@app.route(
    "/client/<int:client_id>/progress/add",
    methods=["GET", "POST"]
)
def add_progress(client_id):
    client = db.get_or_404(Client, client_id)

    if request.method == "POST":
        record = ProgressUpdate(
            client_id=client_id,
            update_type=request.form.get(
                "update_type",
                "WEEKLY"
            ),
            period_label=request.form.get(
                "period_label"
            ),
            update_date=parse_date(
                request.form.get(
                    "update_date"
                )
            ),
            weight_kg=to_float(
                request.form.get("weight_kg")
            ),
            body_fat_percent=to_float(
                request.form.get("body_fat_percent")
            ),
            chest_cm=to_float(
                request.form.get("chest_cm")
            ),
            waist_cm=to_float(
                request.form.get("waist_cm")
            ),
            hip_cm=to_float(
                request.form.get("hip_cm")
            ),
            arm_cm=to_float(
                request.form.get("arm_cm")
            ),
            thigh_cm=to_float(
                request.form.get("thigh_cm")
            ),
            workout_adherence=to_float(
                request.form.get("workout_adherence")
            ),
            diet_adherence=to_float(
                request.form.get("diet_adherence")
            ),
            trainer_notes=request.form.get(
                "trainer_notes"
            )
        )

        db.session.add(record)
        db.session.commit()

        flash(
            "Progress added.",
            "success"
        )

        return redirect(
            url_for(
                "progress_home",
                client_id=client_id
            )
        )

    return render_template(
        "add_progress.html",
        client=client,
        today=date.today().isoformat()
    )


@app.route(
    "/progress/<int:progress_id>/edit",
    methods=["GET", "POST"]
)
def edit_progress(progress_id):
    record = db.get_or_404(
        ProgressUpdate,
        progress_id
    )

    client = db.get_or_404(
        Client,
        record.client_id
    )

    if request.method == "POST":
        record.update_type = request.form.get(
            "update_type"
        )
        record.period_label = request.form.get(
            "period_label"
        )
        record.update_date = parse_date(
            request.form.get("update_date")
        )
        record.weight_kg = to_float(
            request.form.get("weight_kg")
        )
        record.body_fat_percent = to_float(
            request.form.get("body_fat_percent")
        )
        record.chest_cm = to_float(
            request.form.get("chest_cm")
        )
        record.waist_cm = to_float(
            request.form.get("waist_cm")
        )
        record.hip_cm = to_float(
            request.form.get("hip_cm")
        )
        record.arm_cm = to_float(
            request.form.get("arm_cm")
        )
        record.thigh_cm = to_float(
            request.form.get("thigh_cm")
        )
        record.workout_adherence = to_float(
            request.form.get(
                "workout_adherence"
            )
        )
        record.diet_adherence = to_float(
            request.form.get(
                "diet_adherence"
            )
        )
        record.trainer_notes = request.form.get(
            "trainer_notes"
        )

        db.session.commit()

        flash(
            "Progress updated.",
            "success"
        )

        return redirect(
            url_for(
                "progress_home",
                client_id=client.client_id
            )
        )

    return render_template(
        "edit_progress.html",
        client=client,
        record=record
    )


@app.post(
    "/progress/<int:progress_id>/delete"
)
def delete_progress(progress_id):
    record = db.get_or_404(
        ProgressUpdate,
        progress_id
    )

    client_id = record.client_id

    db.session.delete(record)
    db.session.commit()

    flash(
        "Progress deleted.",
        "success"
    )

    return redirect(
        url_for(
            "progress_home",
            client_id=client_id
        )
    )


@app.post(
    "/client/<int:client_id>/progress/ai-analysis"
)
def generate_ai_analysis(client_id):
    client = db.get_or_404(Client, client_id)

    records = (
        ProgressUpdate.query
        .filter_by(client_id=client_id)
        .order_by(ProgressUpdate.update_date.asc())
        .all()
    )

    if not records:
        flash(
            "Add progress first.",
            "error"
        )
        return redirect(
            url_for(
                "progress_home",
                client_id=client_id
            )
        )

    if not hf_client:
        flash(
            "Hugging Face token is not configured.",
            "error"
        )
        return redirect(
            url_for(
                "progress_home",
                client_id=client_id
            )
        )

    calculated = calculate_progress_analysis(
        client,
        records
    )

    history = []

    for record in records:
        history.append({
            "date": record.update_date.isoformat(),
            "period": record.period_label,
            "weight": record.weight_kg,
            "waist": record.waist_cm,
            "body_fat": record.body_fat_percent,
            "workout": record.workout_adherence,
            "diet": record.diet_adherence,
            "notes": record.trainer_notes
        })

    prompt = f"""
/no_think

Analyze this client's fitness progress.

Goal:
{client.goal or "General fitness"}

Calculated score:
{calculated["score"]}/100

History:
{json.dumps(history, indent=2)}

Return ONLY JSON:
{{
  "status": "string",
  "summary": "string",
  "strengths": ["string"],
  "areas_to_improve": ["string"],
  "recommendations": ["string"]
}}
"""

    try:
        response = hf_client.chat.completions.create(
            model=HF_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Fitness progress analyst. "
                        "Return JSON only."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=1800,
            response_format={"type": "json_object"}
        )

        result = clean_ai_json(
            response.choices[0].message.content
        )

        analysis = ProgressAnalysis(
            client_id=client_id,
            score=calculated["score"],
            status=str(
                result.get(
                    "status",
                    calculated["status"]
                )
            ),
            weight_change_kg=calculated["weight_change"],
            weight_change_percent=calculated["weight_percent"],
            body_fat_change_percent=calculated["body_fat_change"],
            waist_change_cm=calculated["waist_change"],
            workout_adherence=calculated["workout_average"],
            diet_adherence=calculated["diet_average"],
            consistency_score=calculated["consistency"],
            summary=str(
                result.get(
                    "summary",
                    calculated["summary"]
                )
            ),
            strengths=json.dumps(
                safe_list(
                    result.get(
                        "strengths",
                        []
                    )
                )
            ),
            areas_to_improve=json.dumps(
                safe_list(
                    result.get(
                        "areas_to_improve",
                        []
                    )
                )
            ),
            recommendations=json.dumps(
                safe_list(
                    result.get(
                        "recommendations",
                        calculated["recommendations"]
                    )
                )
            ),
            ai_generated=True,
            include_in_report=True
        )

        db.session.add(analysis)
        db.session.commit()

        flash(
            "AI analysis generated.",
            "success"
        )

    except Exception as error:
        print(
            "AI ANALYSIS ERROR:",
            repr(error)
        )

        flash(
            f"AI analysis failed: {error}",
            "error"
        )

    return redirect(
        url_for(
            "progress_home",
            client_id=client_id
        )
    )


# ============================================================
# PHOTOS
# ============================================================

@app.route(
    "/client/<int:client_id>/progress-photos",
    methods=["GET", "POST"]
)
def progress_photos(client_id):
    client = db.get_or_404(Client, client_id)

    if request.method == "POST":
        update_type = request.form.get(
            "update_type",
            "WEEKLY"
        )
        period_label = request.form.get(
            "period_label",
            ""
        )

        fields = {
            "front": "FRONT",
            "back": "BACK",
            "left": "LEFT",
            "right": "RIGHT"
        }

        for field_name, photo_type in fields.items():
            uploaded = request.files.get(field_name)

            if not uploaded or not uploaded.filename:
                continue

            filename = secure_filename(
                uploaded.filename
            )

            if "." not in filename:
                continue

            ext = filename.rsplit(
                ".",
                1
            )[1].lower()

            if ext not in {
                "jpg",
                "jpeg",
                "png",
                "webp"
            }:
                continue

            folder = os.path.join(
                UPLOAD_FOLDER,
                client.client_code,
                update_type.lower(),
                secure_filename(period_label)
            )

            os.makedirs(
                folder,
                exist_ok=True
            )

            unique_name = (
                uuid.uuid4().hex
                + "_"
                + filename
            )

            full_path = os.path.join(
                folder,
                unique_name
            )

            uploaded.save(full_path)

            relative = os.path.relpath(
                full_path,
                UPLOAD_FOLDER
            ).replace("\\", "/")

            db.session.add(
                ProgressPhoto(
                    client_id=client_id,
                    update_type=update_type,
                    period_label=period_label,
                    photo_type=photo_type,
                    file_path=relative,
                    original_filename=filename
                )
            )

        db.session.commit()

        flash(
            "Photos uploaded.",
            "success"
        )

        return redirect(
            url_for(
                "progress_photos",
                client_id=client_id
            )
        )

    photos = (
        ProgressPhoto.query
        .filter_by(client_id=client_id)
        .order_by(ProgressPhoto.uploaded_at.desc())
        .all()
    )

    return render_template(
        "progress_photos.html",
        client=client,
        photos=photos
    )


@app.post("/photo/<int:photo_id>/delete")
def delete_photo(photo_id):
    photo = db.get_or_404(
        ProgressPhoto,
        photo_id
    )

    client_id = photo.client_id

    path = os.path.join(
        UPLOAD_FOLDER,
        photo.file_path
    )

    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

    db.session.delete(photo)
    db.session.commit()

    flash(
        "Photo deleted.",
        "success"
    )

    return redirect(
        url_for(
            "progress_photos",
            client_id=client_id
        )
    )


@app.route(
    "/uploads/clients/<path:filename>"
)
def uploaded_photo(filename):
    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# ============================================================
# COMPREHENSIVE CLIENT PDF
# ============================================================

@app.route(
    "/client/<int:client_id>/report/generate"
)
def generate_report(client_id):
    client = db.get_or_404(Client, client_id)

    workouts = (
        WorkoutPlan.query
        .filter_by(client_id=client_id)
        .order_by(WorkoutPlan.created_at.desc())
        .all()
    )

    diets = (
        DietPlan.query
        .filter_by(client_id=client_id)
        .order_by(DietPlan.created_at.desc())
        .all()
    )

    progress = (
        ProgressUpdate.query
        .filter_by(client_id=client_id)
        .order_by(ProgressUpdate.update_date.asc())
        .all()
    )

    photos = (
        ProgressPhoto.query
        .filter_by(client_id=client_id)
        .order_by(ProgressPhoto.uploaded_at.desc())
        .limit(4)
        .all()
    )

    analysis = (
        ProgressAnalysis.query
        .filter_by(client_id=client_id, include_in_report=True)
        .order_by(ProgressAnalysis.created_at.desc())
        .first()
    )

    calculated = calculate_progress_analysis(
        client,
        progress
    )

    latest_workout = workouts[0] if workouts else None
    latest_diet = diets[0] if diets else None
    latest_progress = progress[-1] if progress else None

    folder = os.path.join(
        REPORT_FOLDER,
        client.client_code
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    filename = (
        f"{client.client_code}_fitness_report_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    full_path = os.path.join(
        folder,
        filename
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=22,
        textColor=colors.HexColor("#4f46e5"),
        spaceAfter=12
    )

    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=15,
        textColor=colors.HexColor("#4f46e5"),
        spaceBefore=10,
        spaceAfter=8
    )

    small_style = ParagraphStyle(
        "Small",
        parent=styles["BodyText"],
        fontSize=8.5,
        leading=12
    )

    normal_style = ParagraphStyle(
        "NormalFitness",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13
    )

    document = SimpleDocTemplate(
        full_path,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm
    )

    story = []

    # --------------------------------------------------------
    # COVER / CLIENT INFO
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "FITNESS CLIENT REPORT",
            title_style
        )
    )

    story.append(
        Paragraph(
            f"<b>Client:</b> {client.full_name}",
            normal_style
        )
    )

    story.append(
        Paragraph(
            f"<b>Client ID:</b> {client.client_code}",
            normal_style
        )
    )

    story.append(
        Paragraph(
            f"<b>Phone:</b> {client.phone}",
            normal_style
        )
    )

    story.append(
        Paragraph(
            f"<b>Joined:</b> "
            f"{client.created_at.strftime('%d-%m-%Y')}",
            normal_style
        )
    )

    story.append(
        Paragraph(
            f"<b>Goal:</b> {client.goal or '-'}",
            normal_style
        )
    )

    story.append(
        Spacer(1, 10)
    )

    # --------------------------------------------------------
    # SUMMARY TABLE
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "1. PROGRESS SUMMARY",
            section_style
        )
    )

    summary_rows = [
        ["Metric", "Value"],

        [
            "Starting Weight",
            (
                f"{calculated['starting_weight']:.1f} kg"
                if calculated["starting_weight"] is not None
                else "-"
            )
        ],

        [
            "Current Weight",
            (
                f"{calculated['current_weight']:.1f} kg"
                if calculated["current_weight"] is not None
                else "-"
            )
        ],

        [
            "Weight Change",
            (
                f"{calculated['weight_change']:+.1f} kg"
                if calculated["weight_change"] is not None
                else "-"
            )
        ],

        [
            "Weight Change %",
            (
                f"{calculated['weight_percent']:+.2f}%"
                if calculated["weight_percent"] is not None
                else "-"
            )
        ],

        [
            "Starting Waist",
            (
                f"{calculated['starting_waist']:.1f} cm"
                if calculated["starting_waist"] is not None
                else "-"
            )
        ],

        [
            "Current Waist",
            (
                f"{calculated['current_waist']:.1f} cm"
                if calculated["current_waist"] is not None
                else "-"
            )
        ],

        [
            "Waist Change",
            (
                f"{calculated['waist_change']:+.1f} cm"
                if calculated["waist_change"] is not None
                else "-"
            )
        ],

        [
            "Workout Adherence",
            (
                f"{calculated['workout_average']:.0f}%"
                if calculated["workout_average"] is not None
                else "-"
            )
        ],

        [
            "Diet Adherence",
            (
                f"{calculated['diet_average']:.0f}%"
                if calculated["diet_average"] is not None
                else "-"
            )
        ],

        [
            "Progress Score",
            f"{calculated['score']:.0f}/100"
        ],

        [
            "Status",
            calculated["status"]
        ]
    ]

    summary_table = Table(
        summary_rows,
        repeatRows=1,
        colWidths=[
            70 * mm,
            95 * mm
        ]
    )

    summary_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#4f46e5")
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold"
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.grey
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                8.5
            )
        ])
    )

    story.append(summary_table)

    story.append(
        Spacer(1, 10)
    )

    story.append(
        Paragraph(
            f"<b>Summary:</b> {calculated['summary']}",
            normal_style
        )
    )

    # --------------------------------------------------------
    # CURRENT WORKOUT
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "2. CURRENT WORKOUT PLAN",
            section_style
        )
    )

    if latest_workout:

        story.append(
            Paragraph(
                f"<b>{latest_workout.plan_name}</b> "
                f"({latest_workout.plan_type})",
                normal_style
            )
        )

        story.append(
            Paragraph(
                f"Goal: {latest_workout.goal or '-'} | "
                f"Days/week: {latest_workout.days_per_week or '-'} | "
                f"Duration: {latest_workout.duration_minutes or '-'} min",
                small_style
            )
        )

        workout_rows = [
            ["Day", "Exercise", "Sets", "Reps", "Rest"]
        ]

        for exercise in sorted(
            latest_workout.exercises,
            key=lambda x: x.exercise_order or 0
        ):
            workout_rows.append([
                exercise.day_name or "-",
                exercise.exercise_name or "-",
                exercise.sets or "-",
                exercise.reps or "-",
                (
                    f"{exercise.rest_seconds}s"
                    if exercise.rest_seconds
                    else "-"
                )
            ])

        workout_table = Table(
            workout_rows,
            repeatRows=1,
            colWidths=[
                24 * mm,
                82 * mm,
                18 * mm,
                24 * mm,
                20 * mm
            ]
        )

        workout_table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#2563eb")
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.grey
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    7.5
                )
            ])
        )

        story.append(workout_table)

    else:

        story.append(
            Paragraph(
                "No workout plan has been saved.",
                normal_style
            )
        )

    # --------------------------------------------------------
    # CURRENT DIET
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "3. CURRENT DIET PLAN",
            section_style
        )
    )

    if latest_diet:

        story.append(
            Paragraph(
                f"<b>{latest_diet.plan_name}</b> "
                f"({latest_diet.plan_type})",
                normal_style
            )
        )

        story.append(
            Paragraph(
                f"Goal: {latest_diet.goal or '-'} | "
                f"Diet type: {latest_diet.diet_type or '-'} | "
                f"Calories: {latest_diet.daily_calories or '-'}",
                small_style
            )
        )

        diet_rows = [
            [
                "Day",
                "Meal",
                "Food",
                "Qty",
                "Calories"
            ]
        ]

        for meal in sorted(
            latest_diet.meals,
            key=lambda x: x.meal_order or 0
        ):
            diet_rows.append([
                meal.day_name or "-",
                meal.meal_type or "-",
                meal.meal_name or "-",
                meal.quantity or "-",
                meal.calories or "-"
            ])

        diet_table = Table(
            diet_rows,
            repeatRows=1,
            colWidths=[
                22 * mm,
                26 * mm,
                78 * mm,
                25 * mm,
                22 * mm
            ]
        )

        diet_table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#059669")
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.grey
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    7.5
                )
            ])
        )

        story.append(diet_table)

    else:

        story.append(
            Paragraph(
                "No diet plan has been saved.",
                normal_style
            )
        )

    # --------------------------------------------------------
    # LATEST PROGRESS
    # --------------------------------------------------------

    story.append(
        PageBreak()
    )

    story.append(
        Paragraph(
            "4. LATEST PROGRESS UPDATE",
            section_style
        )
    )

    if latest_progress:

        latest_rows = [
            ["Field", "Latest value"],
            [
                "Period",
                latest_progress.period_label
            ],
            [
                "Date",
                latest_progress.update_date.strftime(
                    "%d-%m-%Y"
                )
            ],
            [
                "Weight",
                (
                    f"{latest_progress.weight_kg:.1f} kg"
                    if latest_progress.weight_kg is not None
                    else "-"
                )
            ],
            [
                "Body Fat",
                (
                    f"{latest_progress.body_fat_percent:.1f}%"
                    if latest_progress.body_fat_percent is not None
                    else "-"
                )
            ],
            [
                "Waist",
                (
                    f"{latest_progress.waist_cm:.1f} cm"
                    if latest_progress.waist_cm is not None
                    else "-"
                )
            ],
            [
                "Workout Adherence",
                (
                    f"{latest_progress.workout_adherence:.0f}%"
                    if latest_progress.workout_adherence is not None
                    else "-"
                )
            ],
            [
                "Diet Adherence",
                (
                    f"{latest_progress.diet_adherence:.0f}%"
                    if latest_progress.diet_adherence is not None
                    else "-"
                )
            ],
            [
                "Trainer Notes",
                latest_progress.trainer_notes or "-"
            ]
        ]

        latest_table = Table(
            latest_rows,
            repeatRows=1,
            colWidths=[
                60 * mm,
                105 * mm
            ]
        )

        latest_table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#f59e0b")
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.4,
                    colors.grey
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8.5
                )
            ])
        )

        story.append(latest_table)

    else:

        story.append(
            Paragraph(
                "No progress update has been recorded.",
                normal_style
            )
        )

    # --------------------------------------------------------
    # AI ANALYSIS / HOW TO IMPROVE
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "5. PROGRESS ANALYSIS & NEXT STEPS",
            section_style
        )
    )

    if analysis:

        story.append(
            Paragraph(
                f"<b>AI Status:</b> "
                f"{analysis.status or calculated['status']}",
                normal_style
            )
        )

        story.append(
            Paragraph(
                f"<b>AI Summary:</b> "
                f"{analysis.summary or '-'}",
                normal_style
            )
        )

        strengths = safe_list(
            analysis.strengths
        )

        areas = safe_list(
            analysis.areas_to_improve
        )

        recommendations = safe_list(
            analysis.recommendations
        )

    else:

        strengths = calculated["strengths"]
        areas = calculated["areas"]
        recommendations = calculated["recommendations"]

    story.append(
        Paragraph(
            "<b>Strengths</b>",
            normal_style
        )
    )

    for item in strengths:
        story.append(
            Paragraph(
                f"• {item}",
                small_style
            )
        )

    story.append(
        Spacer(1, 5)
    )

    story.append(
        Paragraph(
            "<b>Areas to improve</b>",
            normal_style
        )
    )

    for item in areas:
        story.append(
            Paragraph(
                f"• {item}",
                small_style
            )
        )

    story.append(
        Spacer(1, 5)
    )

    story.append(
        Paragraph(
            "<b>How to improve the next phase</b>",
            normal_style
        )
    )

    for item in recommendations:
        story.append(
            Paragraph(
                f"• {item}",
                small_style
            )
        )

    story.append(
        Spacer(1, 8)
    )

    story.append(
        Paragraph(
            "These recommendations are for fitness-planning purposes; "
            "they are not a medical diagnosis.",
            small_style
        )
    )

    # --------------------------------------------------------
    # FULL PROGRESS HISTORY
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "6. COMPLETE PROGRESS HISTORY",
            section_style
        )
    )

    if progress:

        rows = [[
            "Date",
            "Period",
            "Weight",
            "Waist",
            "Workout",
            "Diet"
        ]]

        for record in progress:
            rows.append([
                record.update_date.strftime(
                    "%d-%m-%Y"
                ),
                record.period_label,
                (
                    f"{record.weight_kg:.1f}"
                    if record.weight_kg is not None
                    else "-"
                ),
                (
                    f"{record.waist_cm:.1f}"
                    if record.waist_cm is not None
                    else "-"
                ),
                (
                    f"{record.workout_adherence:.0f}%"
                    if record.workout_adherence is not None
                    else "-"
                ),
                (
                    f"{record.diet_adherence:.0f}%"
                    if record.diet_adherence is not None
                    else "-"
                )
            ])

        history_table = Table(
            rows,
            repeatRows=1,
            colWidths=[
                25 * mm,
                32 * mm,
                25 * mm,
                25 * mm,
                30 * mm,
                30 * mm
            ]
        )

        history_table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#7c3aed")
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.grey
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    7.5
                )
            ])
        )

        story.append(history_table)

    # --------------------------------------------------------
    # RECENT PHOTOS
    # --------------------------------------------------------

    valid_photo_paths = []

    for photo in photos:
        path = os.path.join(
            UPLOAD_FOLDER,
            photo.file_path
        )
        if os.path.exists(path):
            valid_photo_paths.append(
                (photo, path)
            )

    if valid_photo_paths:

        story.append(
            PageBreak()
        )

        story.append(
            Paragraph(
                "7. RECENT PROGRESS PHOTOS",
                section_style
            )
        )

        for photo, path in valid_photo_paths:

            story.append(
                Paragraph(
                    f"{photo.period_label or '-'} "
                    f"- {photo.photo_type or '-'}",
                    small_style
                )
            )

            try:
                story.append(
                    RLImage(
                        path,
                        width=55 * mm,
                        height=70 * mm
                    )
                )
                story.append(
                    Spacer(1, 8)
                )
            except Exception:
                continue

    # --------------------------------------------------------
    # BUILD
    # --------------------------------------------------------

    document.build(story)

    db.session.add(
        ClientReport(
            client_id=client_id,
            file_name=filename,
            file_path=os.path.relpath(
                full_path,
                BASE_DIR
            ).replace("\\", "/")
        )
    )
    db.session.commit()

    return send_file(
        full_path,
        as_attachment=True,
        download_name=filename
    )


@app.route(
    "/report/<int:report_id>/download"
)
def download_report(report_id):
    report = db.get_or_404(
        ClientReport,
        report_id
    )

    path = os.path.join(
        BASE_DIR,
        report.file_path
    )

    if not os.path.exists(path):
        flash(
            "PDF file not found.",
            "error"
        )
        return redirect(
            url_for(
                "client_profile",
                client_id=report.client_id
            )
        )

    return send_file(
        path,
        as_attachment=True,
        download_name=report.file_name
    )


@app.post(
    "/report/<int:report_id>/delete"
)
def delete_report(report_id):
    report = db.get_or_404(
        ClientReport,
        report_id
    )

    client_id = report.client_id

    path = os.path.join(
        BASE_DIR,
        report.file_path
    )

    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

    db.session.delete(report)
    db.session.commit()

    flash(
        "PDF deleted.",
        "success"
    )

    return redirect(
        url_for(
            "client_profile",
            client_id=client_id
        )
    )


# ============================================================
# DATA CENTER / EXCEL-COMPATIBLE EXPORT
# ============================================================

@app.route("/data-center")
def data_center():
    clients = (
        Client.query
        .order_by(Client.created_at.desc())
        .all()
    )

    total_clients = len(clients)

    month_start = datetime.now().replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    week_start = datetime.now() - timedelta(days=7)

    new_this_month = (
        Client.query
        .filter(Client.created_at >= month_start)
        .count()
    )

    new_last_7_days = (
        Client.query
        .filter(Client.created_at >= week_start)
        .count()
    )

    total_workouts = WorkoutPlan.query.count()
    total_diets = DietPlan.query.count()
    total_progress = ProgressUpdate.query.count()
    total_photos = ProgressPhoto.query.count()
    total_reports = ClientReport.query.count()

    client_rows = []

    for client in clients:
        workout, diet, progress, analysis = latest_for_client(
            client.client_id
        )

        all_progress = (
            ProgressUpdate.query
            .filter_by(client_id=client.client_id)
            .order_by(ProgressUpdate.update_date.asc())
            .all()
        )

        calc = calculate_progress_analysis(
            client,
            all_progress
        )

        progress_count = (
            ProgressUpdate.query
            .filter_by(client_id=client.client_id)
            .count()
        )

        client_rows.append({
            "client": client,
            "latest_workout": workout,
            "latest_diet": diet,
            "latest_progress": progress,
            "score": calc["score"],
            "weight_change": calc["weight_change"],
            "progress_count": progress_count
        })

    return render_template(
        "data_center.html",
        client_rows=client_rows,
        total_clients=total_clients,
        new_this_month=new_this_month,
        new_last_7_days=new_last_7_days,
        total_workouts=total_workouts,
        total_diets=total_diets,
        total_progress=total_progress,
        total_photos=total_photos,
        total_reports=total_reports
    )


@app.route("/data-center/export.csv")
def export_data_csv():
    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Data Type",
        "Client ID",
        "Client Code",
        "Client Name",
        "Phone",
        "Email",
        "Gender",
        "Height CM",
        "Starting Weight KG",
        "Goal",
        "Joined Date",
        "Latest Weight KG",
        "Latest Progress Date",
        "Progress Score",
        "Latest Workout",
        "Latest Workout Date",
        "Latest Diet",
        "Latest Diet Date",
        "Workout Plans Count",
        "Diet Plans Count",
        "Progress Updates Count",
        "Photos Count",
        "PDF Reports Count"
    ])

    clients = (
        Client.query
        .order_by(Client.created_at.desc())
        .all()
    )

    for client in clients:

        latest_workout, latest_diet, latest_progress, _ = (
            latest_for_client(client.client_id)
        )

        progress_records = (
            ProgressUpdate.query
            .filter_by(client_id=client.client_id)
            .order_by(ProgressUpdate.update_date.asc())
            .all()
        )

        photo_count = (
            ProgressPhoto.query
            .filter_by(client_id=client.client_id)
            .count()
        )

        report_count = (
            ClientReport.query
            .filter_by(client_id=client.client_id)
            .count()
        )

        workout_count = (
            WorkoutPlan.query
            .filter_by(client_id=client.client_id)
            .count()
        )

        diet_count = (
            DietPlan.query
            .filter_by(client_id=client.client_id)
            .count()
        )

        calc = calculate_progress_analysis(
            client,
            progress_records
        )

        writer.writerow([
            "CLIENT",
            client.client_id,
            client.client_code,
            client.full_name,
            client.phone,
            client.email or "",
            client.gender or "",
            client.height_cm or "",
            client.starting_weight_kg or "",
            client.goal or "",
            client.created_at.strftime(
                "%Y-%m-%d %H:%M"
            ),
            (
                latest_progress.weight_kg
                if latest_progress
                and latest_progress.weight_kg is not None
                else ""
            ),
            (
                latest_progress.update_date.isoformat()
                if latest_progress
                else ""
            ),
            calc["score"],
            (
                latest_workout.plan_name
                if latest_workout
                else ""
            ),
            (
                latest_workout.created_at.strftime(
                    "%Y-%m-%d"
                )
                if latest_workout
                else ""
            ),
            (
                latest_diet.plan_name
                if latest_diet
                else ""
            ),
            (
                latest_diet.created_at.strftime(
                    "%Y-%m-%d"
                )
                if latest_diet
                else ""
            ),
            workout_count,
            diet_count,
            len(progress_records),
            photo_count,
            report_count
        ])

    filename = (
        f"fitness_data_export_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="{filename}"'
        }
    )


@app.template_filter("from_json")
def from_json(value):
    return safe_list(value)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    app.run(
        debug=True,
        port=5001
    )
