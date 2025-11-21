from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, Response
)
from flask_pymongo import PyMongo
from bson import ObjectId
from datetime import datetime
import csv
from io import StringIO

from config import config

app = Flask(__name__)
app.config.from_object(config["default"])
mongo = PyMongo(app)

# Collections
students_col = mongo.db.students
classes_col = mongo.db.classes
sections_col = mongo.db.sections
attendance_col = mongo.db.attendance


# ---------- Helpers ----------

def login_required(f):
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin_logged_in" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ---------- Auth Routes ----------

@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    from config import Config
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            session["admin_name"] = username
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Dashboard ----------

@app.route("/dashboard")
@login_required
def dashboard():
    total_students = students_col.count_documents({})
    total_classes = classes_col.count_documents({})
    total_sections = sections_col.count_documents({})

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_attendance = list(attendance_col.find({"date": today_str}))

    present_count = sum(1 for a in today_attendance if a.get("status") == "Present")
    absent_count = sum(1 for a in today_attendance if a.get("status") == "Absent")

    today_display = datetime.now().strftime("%d/%m/%Y")

    return render_template(
        "dashboard.html",
        total_students=total_students,
        total_classes=total_classes,
        total_sections=total_sections,
        present_count=present_count,
        absent_count=absent_count,
        today=today_display
    )


# ---------- Take Attendance ----------

@app.route("/attendance/take", methods=["GET", "POST"])
@login_required
def take_attendance():
    classes = list(classes_col.find())
    sections = list(sections_col.find())

    selected_date = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    selected_class = request.args.get("class_id") or ""
    selected_section = request.args.get("section_id") or ""

    students = []
    existing_attendance = {}

    if selected_class and selected_section:
        students = list(students_col.find({
            "class_id": ObjectId(selected_class),
            "section_id": ObjectId(selected_section)
        }).sort("roll_no", 1))

        records = list(attendance_col.find({
            "date": selected_date,
            "class_id": ObjectId(selected_class),
            "section_id": ObjectId(selected_section)
        }))
        for rec in records:
            existing_attendance[str(rec["student_id"])] = rec["status"]

    if request.method == "POST":
        selected_date = request.form.get("date")
        selected_class = request.form.get("class_id")
        selected_section = request.form.get("section_id")

        attendance_col.delete_many({
            "date": selected_date,
            "class_id": ObjectId(selected_class),
            "section_id": ObjectId(selected_section)
        })

        for key in request.form:
            if key.startswith("status_"):
                student_id = key.split("_", 1)[1]
                status = request.form.get(key)
                attendance_col.insert_one({
                    "date": selected_date,
                    "class_id": ObjectId(selected_class),
                    "section_id": ObjectId(selected_section),
                    "student_id": ObjectId(student_id),
                    "status": status
                })

        flash("Attendance saved successfully.", "success")
        return redirect(
            url_for("take_attendance", date=selected_date,
                    class_id=selected_class, section_id=selected_section)
        )

    return render_template(
        "attendance_take.html",
        classes=classes,
        sections=sections,
        students=students,
        selected_date=selected_date,
        selected_class=selected_class,
        selected_section=selected_section,
        existing_attendance=existing_attendance
    )


# ---------- Attendance Summary (New) ----------

@app.route("/attendance/summary", methods=["GET"])
@login_required
def attendance_summary():
    selected_date = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")

    # Fetch all classes and sections
    classes = {str(c["_id"]): c["class_name"] for c in classes_col.find()}
    sections = list(sections_col.find())

    # Fetch all attendance for the selected date
    attendance_records = list(attendance_col.find({"date": selected_date}))

    summary_data = []
    has_data = False

    # Organize data structure
    # Iterate through every section to ensure we show 0s for sections with no attendance
    for sec in sections:
        class_id = str(sec["class_id"])
        section_id = str(sec["_id"])
        
        # Get Class Name (skip if orphan section)
        class_name = classes.get(class_id)
        if not class_name:
            continue

        # Count stats for this specific section
        section_records = [
            r for r in attendance_records 
            if str(r["class_id"]) == class_id and str(r["section_id"]) == section_id
        ]

        total_present = sum(1 for r in section_records if r["status"] == "Present")
        total_absent = sum(1 for r in section_records if r["status"] == "Absent")
        
        if len(section_records) > 0:
            has_data = True

        summary_data.append({
            "class_name": class_name,
            "section_name": sec["section_name"],
            "present": total_present,
            "absent": total_absent,
            "total": len(section_records)
        })

    # Sort by Class Name then Section Name
    summary_data.sort(key=lambda x: (x["class_name"], x["section_name"]))

    return render_template(
        "attendance_summary.html",
        summary=summary_data,
        selected_date=selected_date,
        has_data=has_data
    )


# ---------- View Attendance ----------

@app.route("/attendance/view", methods=["GET"])
@login_required
def view_attendance():
    date = request.args.get("date", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    class_id = request.args.get("class_id", "")
    section_id = request.args.get("section_id", "")
    search = request.args.get("search", "").strip()

    query = {}
    if date:
        query["date"] = date
    elif date_from and date_to:
        query["date"] = {"$gte": date_from, "$lte": date_to}

    if class_id:
        query["class_id"] = ObjectId(class_id)
    if section_id:
        query["section_id"] = ObjectId(section_id)

    records = list(attendance_col.find(query))

    class_map = {str(c["_id"]): c["class_name"] for c in classes_col.find()}
    section_map = {str(s["_id"]): s["section_name"] for s in sections_col.find()}
    student_map = {str(s["_id"]): s for s in students_col.find()}

    rows = []
    for rec in records:
        s_id = str(rec["student_id"])
        student = student_map.get(s_id)
        if not student:
            continue

        if search:
            if search.lower() not in student["name"].lower() and search not in str(student.get("roll_no", "")):
                continue
        
        display_date = rec["date"]
        try:
            d_obj = datetime.strptime(rec["date"], "%Y-%m-%d")
            display_date = d_obj.strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            pass

        rows.append({
            "date": display_date,
            "class_name": class_map.get(str(rec["class_id"]), ""),
            "section_name": section_map.get(str(rec["section_id"]), ""),
            "roll_no": student.get("roll_no"),
            "student_name": student["name"],
            "status": rec["status"]
        })

    classes = list(classes_col.find())
    sections = list(sections_col.find())

    return render_template(
        "attendance_view.html",
        rows=rows,
        classes=classes,
        sections=sections,
        date=date,
        date_from=date_from,
        date_to=date_to,
        selected_class=class_id,
        selected_section=section_id,
        search=search
    )


# ---------- Download Reports ----------

@app.route("/attendance/reports", methods=["GET", "POST"])
@login_required
def attendance_reports():
    classes = list(classes_col.find())
    sections = list(sections_col.find())

    if request.method == "POST":
        report_type = request.form.get("report_type")
        date = request.form.get("date", "")
        date_from = request.form.get("date_from", "")
        date_to = request.form.get("date_to", "")
        class_id = request.form.get("class_id", "")
        section_id = request.form.get("section_id", "")

        query = {}
        if date:
            query["date"] = date
        elif date_from and date_to:
            query["date"] = {"$gte": date_from, "$lte": date_to}

        if class_id and class_id != "all":
            query["class_id"] = ObjectId(class_id)
        if section_id and section_id != "all":
            query["section_id"] = ObjectId(section_id)

        records = list(attendance_col.find(query))

        class_map = {str(c["_id"]): c["class_name"] for c in classes_col.find()}
        section_map = {str(s["_id"]): s["section_name"] for s in sections_col.find()}
        student_map = {str(s["_id"]): s for s in students_col.find()}

        output = StringIO()
        writer = csv.writer(output)

        writer.writerow(["Date", "Class", "Section", "Roll No", "Student Name", "Status"])

        for rec in records:
            student = student_map.get(str(rec["student_id"]))
            if not student:
                continue
            
            display_date = rec["date"]
            try:
                d_obj = datetime.strptime(rec["date"], "%Y-%m-%d")
                display_date = d_obj.strftime("%d/%m/%Y")
            except (ValueError, TypeError):
                pass
                
            writer.writerow([
                display_date,
                class_map.get(str(rec["class_id"]), ""),
                section_map.get(str(rec["section_id"]), ""),
                student.get("roll_no", ""),
                student["name"],
                rec["status"]
            ])

        filename = f"attendance_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        resp = Response(output.getvalue(), mimetype="text/csv")
        resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return resp

    return render_template("reports.html", classes=classes, sections=sections)


# ---------- Manage Students (CRUD) ----------

@app.route("/students")
@login_required
def students():
    students_list = list(students_col.find())
    classes = {str(c["_id"]): c["class_name"] for c in classes_col.find()}
    sections = {str(s["_id"]): s["section_name"] for s in sections_col.find()}
    return render_template(
        "students.html",
        students=students_list,
        classes=classes,
        sections=sections
    )


@app.route("/students/add", methods=["POST"])
@login_required
def add_student():
    name = request.form.get("name").strip()
    class_id = request.form.get("class_id")
    section_id = request.form.get("section_id")
    roll_no = request.form.get("roll_no")

    students_col.insert_one({
        "name": name,
        "class_id": ObjectId(class_id),
        "section_id": ObjectId(section_id),
        "roll_no": int(roll_no)
    })

    flash("Student added successfully.", "success")
    return redirect(url_for("students"))


@app.route("/students/edit/<id>", methods=["POST"])
@login_required
def edit_student(id):
    name = request.form.get("name").strip()
    class_id = request.form.get("class_id")
    section_id = request.form.get("section_id")
    roll_no = request.form.get("roll_no")

    students_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "name": name,
            "class_id": ObjectId(class_id),
            "section_id": ObjectId(section_id),
            "roll_no": int(roll_no)
        }}
    )
    flash("Student updated successfully.", "success")
    return redirect(url_for("students"))


@app.route("/students/delete/<id>", methods=["POST"])
@login_required
def delete_student(id):
    students_col.delete_one({"_id": ObjectId(id)})
    attendance_col.delete_many({"student_id": ObjectId(id)})
    flash("Student deleted successfully.", "success")
    return redirect(url_for("students"))


# ---------- Manage Classes & Sections (CRUD) ----------

@app.route("/classes-sections")
@login_required
def classes_sections():
    classes = list(classes_col.find())
    sections = list(sections_col.find())
    return render_template(
        "classes_sections.html",
        classes=classes,
        sections=sections
    )


@app.route("/classes/add", methods=["POST"])
@login_required
def add_class():
    class_name = request.form.get("class_name").strip()
    classes_col.insert_one({"class_name": class_name})
    flash("Class added successfully.", "success")
    return redirect(url_for("classes_sections"))


@app.route("/classes/edit/<id>", methods=["POST"])
@login_required
def edit_class(id):
    class_name = request.form.get("class_name").strip()
    classes_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"class_name": class_name}}
    )
    flash("Class updated successfully.", "success")
    return redirect(url_for("classes_sections"))


@app.route("/classes/delete/<id>", methods=["POST"])
@login_required
def delete_class(id):
    linked_students = students_col.count_documents({"class_id": ObjectId(id)})
    linked_sections = sections_col.count_documents({"class_id": ObjectId(id)})
    if linked_students > 0 or linked_sections > 0:
        flash("Cannot delete class. It is linked to students/sections.", "danger")
        return redirect(url_for("classes_sections"))

    classes_col.delete_one({"_id": ObjectId(id)})
    flash("Class deleted successfully.", "success")
    return redirect(url_for("classes_sections"))


@app.route("/sections/add", methods=["POST"])
@login_required
def add_section():
    section_name = request.form.get("section_name").strip()
    class_id = request.form.get("class_id")
    sections_col.insert_one({
        "section_name": section_name,
        "class_id": ObjectId(class_id)
    })
    flash("Section added successfully.", "success")
    return redirect(url_for("classes_sections"))


@app.route("/sections/edit/<id>", methods=["POST"])
@login_required
def edit_section(id):
    section_name = request.form.get("section_name").strip()
    class_id = request.form.get("class_id")
    sections_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "section_name": section_name,
            "class_id": ObjectId(class_id)
        }}
    )
    flash("Section updated successfully.", "success")
    return redirect(url_for("classes_sections"))


@app.route("/sections/delete/<id>", methods=["POST"])
@login_required
def delete_section(id):
    linked_students = students_col.count_documents({"section_id": ObjectId(id)})
    if linked_students > 0:
        flash("Cannot delete section. It is linked to students.", "danger")
        return redirect(url_for("classes_sections"))

    sections_col.delete_one({"_id": ObjectId(id)})
    flash("Section deleted successfully.", "success")
    return redirect(url_for("classes_sections"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)