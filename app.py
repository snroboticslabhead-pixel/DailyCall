from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, Response, g
)
from datetime import datetime
import csv
from io import StringIO
import pymysql
from pymysql.cursors import DictCursor

from config import config

app = Flask(__name__)
app.config.from_object(config["default"])

# MySQL connection function
def get_db():
    if 'db' not in g:
        g.db = pymysql.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            database=app.config['MYSQL_DB'],
            cursorclass=DictCursor
        )
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Initialize database tables
def init_db():
    db = get_db()
    with db.cursor() as cursor:
        # Create classes table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            class_name VARCHAR(255) NOT NULL
        )
        """)
        
        # Create sections table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INT AUTO_INCREMENT PRIMARY KEY,
            section_name VARCHAR(255) NOT NULL,
            class_id INT NOT NULL,
            FOREIGN KEY (class_id) REFERENCES classes(id)
        )
        """)
        
        # Create students table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            class_id INT NOT NULL,
            section_id INT NOT NULL,
            roll_no INT NOT NULL,
            FOREIGN KEY (class_id) REFERENCES classes(id),
            FOREIGN KEY (section_id) REFERENCES sections(id)
        )
        """)
        
        # Create attendance table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INT AUTO_INCREMENT PRIMARY KEY,
            date DATE NOT NULL,
            class_id INT NOT NULL,
            section_id INT NOT NULL,
            student_id INT NOT NULL,
            status ENUM('Present', 'Absent') NOT NULL,
            FOREIGN KEY (class_id) REFERENCES classes(id),
            FOREIGN KEY (section_id) REFERENCES sections(id),
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
        """)
    db.commit()

# Initialize database on startup
with app.app_context():
    init_db()

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
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM students")
        total_students = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM classes")
        total_classes = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM sections")
        total_sections = cursor.fetchone()['count']

        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT * FROM attendance WHERE date = %s", (today_str,))
        today_attendance = cursor.fetchall()

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
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM classes")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT * FROM sections")
        sections = cursor.fetchall()

    selected_date = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    selected_class = request.args.get("class_id") or ""
    selected_section = request.args.get("section_id") or ""

    students = []
    existing_attendance = {}

    if selected_class and selected_section:
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM students 
                WHERE class_id = %s AND section_id = %s 
                ORDER BY roll_no
            """, (selected_class, selected_section))
            students = cursor.fetchall()
            
            cursor.execute("""
                SELECT * FROM attendance 
                WHERE date = %s AND class_id = %s AND section_id = %s
            """, (selected_date, selected_class, selected_section))
            records = cursor.fetchall()
            
            for rec in records:
                existing_attendance[str(rec["student_id"])] = rec["status"]

    if request.method == "POST":
        selected_date = request.form.get("date")
        selected_class = request.form.get("class_id")
        selected_section = request.form.get("section_id")

        db = get_db()
        with db.cursor() as cursor:
            # Delete existing attendance records
            cursor.execute("""
                DELETE FROM attendance 
                WHERE date = %s AND class_id = %s AND section_id = %s
            """, (selected_date, selected_class, selected_section))
            
            # Insert new attendance records
            for key in request.form:
                if key.startswith("status_"):
                    student_id = key.split("_", 1)[1]
                    status = request.form.get(key)
                    cursor.execute("""
                        INSERT INTO attendance 
                        (date, class_id, section_id, student_id, status)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (selected_date, selected_class, selected_section, student_id, status))
            
            db.commit()

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


# ---------- Attendance Summary ----------

@app.route("/attendance/summary", methods=["GET"])
@login_required
def attendance_summary():
    selected_date = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    
    db = get_db()
    with db.cursor() as cursor:
        # Fetch all classes and sections
        cursor.execute("SELECT * FROM classes")
        classes = {str(c["id"]): c["class_name"] for c in cursor.fetchall()}
        
        cursor.execute("SELECT * FROM sections")
        sections = cursor.fetchall()

        # Fetch all attendance for the selected date
        cursor.execute("SELECT * FROM attendance WHERE date = %s", (selected_date,))
        attendance_records = cursor.fetchall()

    summary_data = []
    has_data = False

    # Organize data structure
    for sec in sections:
        class_id = str(sec["class_id"])
        section_id = str(sec["id"])
        
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

    query = "SELECT * FROM attendance WHERE 1=1"
    params = []
    
    if date:
        query += " AND date = %s"
        params.append(date)
    elif date_from and date_to:
        query += " AND date BETWEEN %s AND %s"
        params.extend([date_from, date_to])

    if class_id:
        query += " AND class_id = %s"
        params.append(class_id)
    if section_id:
        query += " AND section_id = %s"
        params.append(section_id)

    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(query, params)
        records = cursor.fetchall()
        
        cursor.execute("SELECT * FROM classes")
        class_map = {str(c["id"]): c["class_name"] for c in cursor.fetchall()}
        
        cursor.execute("SELECT * FROM sections")
        section_map = {str(s["id"]): s["section_name"] for s in cursor.fetchall()}
        
        cursor.execute("SELECT * FROM students")
        student_map = {str(s["id"]): s for s in cursor.fetchall()}

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

    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM classes")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT * FROM sections")
        sections = cursor.fetchall()

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
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM classes")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT * FROM sections")
        sections = cursor.fetchall()

    if request.method == "POST":
        report_type = request.form.get("report_type")
        date = request.form.get("date", "")
        date_from = request.form.get("date_from", "")
        date_to = request.form.get("date_to", "")
        class_id = request.form.get("class_id", "")
        section_id = request.form.get("section_id", "")

        query = "SELECT * FROM attendance WHERE 1=1"
        params = []
        
        if date:
            query += " AND date = %s"
            params.append(date)
        elif date_from and date_to:
            query += " AND date BETWEEN %s AND %s"
            params.extend([date_from, date_to])

        if class_id and class_id != "all":
            query += " AND class_id = %s"
            params.append(class_id)
        if section_id and section_id != "all":
            query += " AND section_id = %s"
            params.append(section_id)

        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(query, params)
            records = cursor.fetchall()
            
            cursor.execute("SELECT * FROM classes")
            class_map = {str(c["id"]): c["class_name"] for c in cursor.fetchall()}
            
            cursor.execute("SELECT * FROM sections")
            section_map = {str(s["id"]): s["section_name"] for s in cursor.fetchall()}
            
            cursor.execute("SELECT * FROM students")
            student_map = {str(s["id"]): s for s in cursor.fetchall()}

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
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM students")
        students_list = cursor.fetchall()
        
        cursor.execute("SELECT * FROM classes")
        classes = {str(c["id"]): c["class_name"] for c in cursor.fetchall()}
        
        cursor.execute("SELECT * FROM sections")
        sections = {str(s["id"]): s["section_name"] for s in cursor.fetchall()}
    
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

    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("""
            INSERT INTO students (name, class_id, section_id, roll_no)
            VALUES (%s, %s, %s, %s)
        """, (name, class_id, section_id, roll_no))
        db.commit()

    flash("Student added successfully.", "success")
    return redirect(url_for("students"))


@app.route("/students/edit/<id>", methods=["POST"])
@login_required
def edit_student(id):
    name = request.form.get("name").strip()
    class_id = request.form.get("class_id")
    section_id = request.form.get("section_id")
    roll_no = request.form.get("roll_no")

    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("""
            UPDATE students 
            SET name = %s, class_id = %s, section_id = %s, roll_no = %s
            WHERE id = %s
        """, (name, class_id, section_id, roll_no, id))
        db.commit()
    
    flash("Student updated successfully.", "success")
    return redirect(url_for("students"))


@app.route("/students/delete/<id>", methods=["POST"])
@login_required
def delete_student(id):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("DELETE FROM students WHERE id = %s", (id,))
        cursor.execute("DELETE FROM attendance WHERE student_id = %s", (id,))
        db.commit()
    
    flash("Student deleted successfully.", "success")
    return redirect(url_for("students"))


# ---------- Manage Classes & Sections (CRUD) ----------

@app.route("/classes-sections")
@login_required
def classes_sections():
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM classes")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT * FROM sections")
        sections = cursor.fetchall()
    
    return render_template(
        "classes_sections.html",
        classes=classes,
        sections=sections
    )


@app.route("/classes/add", methods=["POST"])
@login_required
def add_class():
    class_name = request.form.get("class_name").strip()
    
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("INSERT INTO classes (class_name) VALUES (%s)", (class_name,))
        db.commit()
    
    flash("Class added successfully.", "success")
    return redirect(url_for("classes_sections"))


@app.route("/classes/edit/<id>", methods=["POST"])
@login_required
def edit_class(id):
    class_name = request.form.get("class_name").strip()
    
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("""
            UPDATE classes 
            SET class_name = %s
            WHERE id = %s
        """, (class_name, id))
        db.commit()
    
    flash("Class updated successfully.", "success")
    return redirect(url_for("classes_sections"))


@app.route("/classes/delete/<id>", methods=["POST"])
@login_required
def delete_class(id):
    db = get_db()
    with db.cursor() as cursor:
        # Check if class has linked students or sections
        cursor.execute("SELECT COUNT(*) as count FROM students WHERE class_id = %s", (id,))
        linked_students = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM sections WHERE class_id = %s", (id,))
        linked_sections = cursor.fetchone()['count']
        
        if linked_students > 0 or linked_sections > 0:
            flash("Cannot delete class. It is linked to students/sections.", "danger")
            return redirect(url_for("classes_sections"))

        cursor.execute("DELETE FROM classes WHERE id = %s", (id,))
        db.commit()
    
    flash("Class deleted successfully.", "success")
    return redirect(url_for("classes_sections"))


@app.route("/sections/add", methods=["POST"])
@login_required
def add_section():
    section_name = request.form.get("section_name").strip()
    class_id = request.form.get("class_id")
    
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("""
            INSERT INTO sections (section_name, class_id)
            VALUES (%s, %s)
        """, (section_name, class_id))
        db.commit()
    
    flash("Section added successfully.", "success")
    return redirect(url_for("classes_sections"))


@app.route("/sections/edit/<id>", methods=["POST"])
@login_required
def edit_section(id):
    section_name = request.form.get("section_name").strip()
    class_id = request.form.get("class_id")
    
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("""
            UPDATE sections 
            SET section_name = %s, class_id = %s
            WHERE id = %s
        """, (section_name, class_id, id))
        db.commit()
    
    flash("Section updated successfully.", "success")
    return redirect(url_for("classes_sections"))


@app.route("/sections/delete/<id>", methods=["POST"])
@login_required
def delete_section(id):
    db = get_db()
    with db.cursor() as cursor:
        # Check if section has linked students
        cursor.execute("SELECT COUNT(*) as count FROM students WHERE section_id = %s", (id,))
        linked_students = cursor.fetchone()['count']
        
        if linked_students > 0:
            flash("Cannot delete section. It is linked to students.", "danger")
            return redirect(url_for("classes_sections"))

        cursor.execute("DELETE FROM sections WHERE id = %s", (id,))
        db.commit()
    
    flash("Section deleted successfully.", "success")
    return redirect(url_for("classes_sections"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
