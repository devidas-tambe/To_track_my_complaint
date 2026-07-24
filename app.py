from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
import sqlite3
import hashlib
import secrets              # 💥 NEW: Unique token generator ke liye
from transformers import pipeline  # 💥 NEW: Zero-Shot AI Core ke liye
import csv
from io import StringIO



app = Flask(__name__)
app.secret_key = "nashik_secret_key" # Flash messages dikhane ke liye zaroori hai
DB_NAME = "citizen_complaints.db"

# Password ko secure (SHA-256) banane ka function
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# 🌐 1. Home Page Route
# 🌐 1. Home Page Route connected with separate index.html
@app.route('/')
def home():
    if 'user_id' in session:
        # User login hai toh details template ko pass karo
        return render_template('index.html', logged_in=True, user_name=session['user_name'])
    
    # User login nahi hai toh normal default state
    return render_template('index.html', logged_in=False)

# 🌐 2. Register Route (GET yani page dikhana, POST yani form submit hona)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Form se data nikalna
        full_name = request.form['full_name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        city = request.form.get('city', 'Nashik')
        
        # Password ko secure hash mein badalna
        p_hash = hash_password(password)
        
        # Direct Database mein data insert karna
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (full_name, email, phone, password_hash, city)
                VALUES (?, ?, ?, ?, ?);
            """, (full_name, email, phone, p_hash, city))
            conn.commit()
            flash("Registration safal raha! Aap account ban chuka hai.", "success")
            return redirect(url_for('login')) # Sahi hone par login page par bhej dega
        except sqlite3.IntegrityError:
            # Agar email pehle se database mein hoga toh yeh error aayega
            flash("Yeh Email ID pehle se registered hai!", "danger")
        finally:
            conn.close()
            
    return render_template('register.html')

# 🌐 3. Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        p_hash = hash_password(password)
        
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row  # Isse columns ko naam se access kar sakte hain
        cursor = conn.cursor()
        
        # User ko email aur password_hash se dhoondhna
        user = cursor.execute("""
            SELECT * FROM users WHERE email = ? AND password_hash = ? AND is_active = 1;
        """, (email, p_hash)).fetchone()
        conn.close()
        
        if user:
            # Session mein data save karna
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['role'] = 'CITIZEN'
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for('public_insights'))
        else:
            flash("Galat Email ya Password! Kripya dubara koshish karein.", "danger")
            
    return render_template('login.html')

# # 🌐 4. Citizen Dashboard Route
# @app.route('/citizen/dashboard')
# def citizen_dashboard():
#     # Suraksha check: Agar user logged in nahi hai toh login par bhej do
#     if 'user_id' not in session or session.get('role') != 'CITIZEN':
#         flash("Kripya pehle login karein.", "warning")
#         return redirect(url_for('login'))
        
#     return f"""
#     <div style='font-family: sans-serif; margin: 50px;'>
#         <h1>Hello, {session['user_name']}!</h1>
#         <h3>Yeh aapka Citizen Dashboard hai (Feature 01 Complete)</h3>
#         <hr>
#         <p><a href='/logout' style='color: red; font-weight: bold;'>Logout</a></p>
#     </div>
#     """

# 🌐 5. Logout Route
@app.route('/logout')
def logout():
    session.clear()  # Session ka saara data saaf
    flash("Aap safely logout ho gaye hain.", "info")
    return redirect(url_for('login'))

# ═══════════════════════════════════════════════════════════
# 🤖 ZERO-SHOT AI ENGINE INITIALIZATION
# ═══════════════════════════════════════════════════════════
print("🤖 Loading Zero-Shot AI Model into memory... Please wait...")
# Yeh model load hone mein pehli baar thoda time lega (Internet zaroori hai)
ai_classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
print("✅ AI Engine loaded successfully!")

# AI Categories Jo Hamare Database Ke Departments Se Match Karti Hain
DEPARTMENTS = [
    'Roads & Infrastructure', 
    'Water Supply', 
    'Electricity', 
    'Sanitation & Garbage', 
    'Illegal Construction & Encroachment'
]

# AI Urgency Levels (Feature 06)
URGENCIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']


# ═══════════════════════════════════════════════════════════
# 💥 NEW COMPLAINT ROUTE WITH ZERO-SHOT AI & DUPLICATE CHECK
# ═══════════════════════════════════════════════════════════
@app.route('/citizen/file_complaint', methods=['GET', 'POST'])
def file_complaint():
    # Security Check: Citizen logged in hona chahiye
    if 'user_id' not in session or session.get('role') != 'CITIZEN':
        flash("Kripya pehle login karein.", "warning")
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        force_submit = request.form.get('force_submit', '0') # Duplicate override marker
        
        # ---------------------------------------------------
        # 🔍 FEATURE 04: Duplicate Complaint Alert Logic
        # ---------------------------------------------------
        if force_submit == '0':
            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # User ki purani active complaints check karna
            active_tickets = cursor.execute("""
                SELECT tracking_token, title, status FROM complaints 
                WHERE user_id = ? AND status NOT IN ('Resolved', 'Rejected', 'Withdrawn');
            """, (session['user_id'],)).fetchall()
            conn.close()
            
            # Simple keyword matching loop
            input_words = set(title.lower().split())
            for ticket in active_tickets:
                existing_words = set(ticket['title'].lower().split())
                matches = input_words.intersection(existing_words)
                
                # Agar 50% se zyada words match hote hain, toh duplicate alert alert box trigger hoga
                if len(matches) >= max(1, len(input_words) * 0.5):
                    return render_template('file_ticket.html', 
                                           duplicate=True, 
                                           old_token=ticket['tracking_token'],
                                           old_status=ticket['status'],
                                           form_data={'title': title, 'description': description})

        # ---------------------------------------------------
        # 🤖 FEATURE 05: Pass 1 - AI Auto-Categorisation
        # ---------------------------------------------------
        category_res = ai_classifier(description, candidate_labels=DEPARTMENTS)
        detected_dept = category_res['labels'][0]
        confidence_score = round(category_res['scores'][0] * 100, 2) # e.g. 94.25%

        # ---------------------------------------------------
        # ⚡ FEATURE 06: Pass 2 - AI Priority/Urgency Detection
        # ---------------------------------------------------
        urgency_res = ai_classifier(description, candidate_labels=URGENCIES)
        detected_urgency = urgency_res['labels'][0]

        # ---------------------------------------------------
        # 🎟️ SAVE TO DATABASE WITH UNIQUE TRACKING TOKEN
        # ---------------------------------------------------
        token = f"NMC-{secrets.token_hex(3).upper()}" # e.g., NMC-D4F1B8
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO complaints (
                    user_id, title, description, ai_category, ai_confidence, 
                    ai_urgency, status, tracking_token
                ) VALUES (?, ?, ?, ?, ?, ?, 'Submitted', ?);
            """, (session['user_id'], title, description, detected_dept, confidence_score, detected_urgency, token))
            
            complaint_id = cursor.lastrowid
            
            # History Trail log automatically add karna (Feature 20)
            cursor.execute("""
                INSERT INTO complaint_history (complaint_id, old_status, new_status, note)
                VALUES (?, NULL, 'Submitted', 'Complaint auto-routed by Zero-Shot NLP Engine.');
            """, (complaint_id,))
            
            conn.commit()
            flash(f"🎉 Shikayat Darj Ho Gayi! Category: {detected_dept} ({confidence_score}%), Urgency: {detected_urgency}. Token: {token}", "success")
            return redirect(url_for('citizen_dashboard'))
        except sqlite3.Error as e:
            flash(f"Database error: {e}", "danger")
        finally:
            conn.close()

    return render_template('file_ticket.html', duplicate=False)

# 🌐 4. UPDATED: Citizen Dashboard (Feature 07 & 09: View, Search & Filter)
@app.route('/citizen/dashboard')
def citizen_dashboard():
    if 'user_id' not in session or session.get('role') != 'CITIZEN':
        flash("Kripya pehle login karein.", "warning")
        return redirect(url_for('login'))
        
    # Search aur Filter parameters lena
    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Base Query construction
    query = "SELECT * FROM complaints WHERE user_id = ?"
    params = [session['user_id']]
    
    # Feature 09: Status Filter Logic
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
        
    # Feature 09: Keyword Search Logic (Title ya Description mein)
    if search_query:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.append(f"%{search_query}%")
        params.append(f"%{search_query}%")
        
    query += " ORDER BY id DESC"
    complaints = cursor.execute(query, params).fetchall()
    conn.close()
    
    return render_template('track.html', complaints=complaints, search=search_query, current_status=status_filter, view_mode='list')


# 🌐 5. 💥 NEW: Complaint Detail & Timeline History (Feature 08)
@app.route('/citizen/complaint/<int:complaint_id>')
def complaint_detail(complaint_id):
    if 'user_id' not in session or session.get('role') != 'CITIZEN':
        flash("Please log in to continue.", "warning")
        return redirect(url_for('login'))
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Main complaint aur audit insight details nikalna
    complaint = cursor.execute("SELECT * FROM complaints WHERE id = ? AND user_id = ?", (complaint_id, session['user_id'])).fetchone()
    
    if not complaint:
        conn.close()
        flash("Complaint not found, or you do not have permission to access it.", "danger")
        return redirect(url_for('citizen_dashboard'))
        
    # Feature 08: Timeline Logs nikalna history table se
    history = cursor.execute("""
        SELECT ch.*, s.full_name as officer_name 
        FROM complaint_history ch
        LEFT JOIN staff s ON ch.changed_by_staff_id = s.id
        WHERE ch.complaint_id = ? ORDER BY ch.changed_at ASC
    """, (complaint_id,)).fetchall()
    
    conn.close()
    return render_template('track.html', complaint=complaint, history=history, view_mode='detail')


# 🌐 6. 💥 NEW: Edit Complaint Logic (Feature 10)
@app.route('/citizen/complaint/edit/<int:complaint_id>', methods=['GET', 'POST'])
def edit_complaint(complaint_id):
    if 'user_id' not in session or session.get('role') != 'CITIZEN':
        flash("Kripya pehle login karein.", "warning")
        return redirect(url_for('login'))
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    complaint = cursor.execute("SELECT * FROM complaints WHERE id = ? AND user_id = ?", (complaint_id, session['user_id'])).fetchone()
    
    if not complaint:
        conn.close()
        flash("Complaint not found.", "danger")
        return redirect(url_for('citizen_dashboard'))
        
    # 🛡️ Feature 10: Status check locking framework
    if complaint['status'] != 'Submitted':
        conn.close()
        flash("This complaint has been locked because an admin/officer has already taken action on it.!", "danger")
        return redirect(url_for('complaint_detail', complaint_id=complaint_id))
        
    if request.method == 'POST':
        new_title = request.form['title']
        new_description = request.form['description']
        
        # Update details dynamically in DB
        cursor.execute("""
            UPDATE complaints 
            SET title = ?, description = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (new_title, new_description, complaint_id))
        
        # History note generator for audit
        cursor.execute("""
            INSERT INTO complaint_history (complaint_id, old_status, new_status, note)
            VALUES (?, 'Submitted', 'Submitted', 'Citizen updated/expanded complaint content.');
        """, (complaint_id,))
        
        conn.commit()
        conn.close()
        flash("Shikayat kamyabi se update ho gayi!", "success")
        return redirect(url_for('complaint_detail', complaint_id=complaint_id))
        
    conn.close()
    return render_template('track.html', complaint=complaint, view_mode='edit')

# 🌐 7. 💥 NEW: Withdraw Complaint Logic (Feature 11)
@app.route('/citizen/complaint/withdraw/<int:complaint_id>', methods=['GET', 'POST'])
def withdraw_complaint(complaint_id):
    if 'user_id' not in session or session.get('role') != 'CITIZEN':
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        reason = request.form['reason']
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Status change to Withdrawn
        cursor.execute("UPDATE complaints SET status = 'Withdrawn', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?", (complaint_id, session['user_id']))
        
        # History log insert
        cursor.execute("""
            INSERT INTO complaint_history (complaint_id, old_status, new_status, note)
            VALUES (?, 'Submitted', 'Withdrawn', ?);
        """, (complaint_id, f"The citizen withdrew the ticket. Reason: {reason}"))
        
        conn.commit()
        conn.close()
        flash("Complaint safely withdrawn (cancelled).", "info")
        return redirect(url_for('complaint_detail', complaint_id=complaint_id))
        
    return render_template('complaint_lifecycle.html', action='withdraw', complaint_id=complaint_id)


# 🌐 8. 💥 NEW: Escalate Complaint Logic (Feature 12)
@app.route('/citizen/complaint/escalate/<int:complaint_id>', methods=['POST'])
def escalate_complaint(complaint_id):
    if 'user_id' not in session or session.get('role') != 'CITIZEN':
        return redirect(url_for('login'))
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Check if complaint belongs to user
    complaint = cursor.execute("SELECT status FROM complaints WHERE id = ? AND user_id = ?", (complaint_id, session['user_id'])).fetchone()
    
    if complaint:
        cursor.execute("UPDATE complaints SET status = 'Escalated', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (complaint_id,))
        cursor.execute("""
            INSERT INTO complaint_history (complaint_id, old_status, new_status, note)
            VALUES (?, 'In Progress', 'Escalated', 'Citizen triggered manual SLA breach escalation.');
        """, (complaint_id,))
        conn.commit()
        flash("TTicket Successfully Escalated! Higher authorities have been notified.", "danger")
    
    conn.close()
    return redirect(url_for('complaint_detail', complaint_id=complaint_id))


# 🌐 9. 💥 NEW: Reopen Resolved Ticket Logic (Feature 13)
@app.route('/citizen/complaint/reopen/<int:complaint_id>', methods=['GET', 'POST'])
def reopen_complaint(complaint_id):
    if 'user_id' not in session or session.get('role') != 'CITIZEN':
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        reason = request.form['reason']
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE complaints SET status = 'Submitted', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?", (complaint_id, session['user_id']))
        cursor.execute("""
            INSERT INTO complaint_history (complaint_id, old_status, new_status, note)
            VALUES (?, 'Resolved', 'Submitted', ?);
        """, (complaint_id, f"Citizen re-opened ticket. Issue persistent. Note: {reason}"))
        
        conn.commit()
        conn.close()
        flash("Complaint successfully Re-opened! Yeh wapas admin queue mein chali gayi hai.", "warning")
        return redirect(url_for('complaint_detail', complaint_id=complaint_id))
        
    return render_template('complaint_lifecycle.html', action='reopen', complaint_id=complaint_id)


# 🌐 10. 💥 NEW: Rate Resolution Logic (Feature 14)
@app.route('/citizen/complaint/rate/<int:complaint_id>', methods=['POST'])
def rate_complaint(complaint_id):
    if 'user_id' not in session or session.get('role') != 'CITIZEN':
        return redirect(url_for('login'))
        
    star_rating = request.form['star_rating']
    comment = request.form['comment']
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO feedback (complaint_id, star_rating, comment)
            VALUES (?, ?, ?);
        """, (complaint_id, star_rating, comment))
        conn.commit()
        flash("Thank you! Feedback and rating saved successfully.", "success")
    except sqlite3.IntegrityError:
        flash("You have already submitted feedback for this ticket.", "warning")
    finally:
        conn.close()
        
    return redirect(url_for('complaint_detail', complaint_id=complaint_id))

# 🌐 11. UPDATED: Personal Insights Dashboard (Sirf logged-in user ka data)
@app.route('/public/insights')
def public_insights():
    # Security Check: Agar login nahi hai, toh pehle login par bhej do
    if 'user_id' not in session:
        flash("Please log in first to view your personal insights.", "warning")
        return redirect(url_for('login'))
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 📊 Sirf is logged-in user ke stats nikalna
    stats = {}
    stats['total'] = cursor.execute("SELECT COUNT(*) FROM complaints WHERE user_id = ?", (session['user_id'],)).fetchone()[0]
    stats['resolved'] = cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'Resolved' AND user_id = ?", (session['user_id'],)).fetchone()[0]
    stats['pending'] = cursor.execute("SELECT COUNT(*) FROM complaints WHERE status IN ('Submitted', 'Under Review', 'In Progress') AND user_id = ?", (session['user_id'],)).fetchone()[0]
    
    # User ka personal Resolution Rate
    if stats['total'] > 0:
        stats['rate'] = round((stats['resolved'] / stats['total']) * 100, 2)
    else:
        stats['rate'] = 0.00
        
    # User ki apni complaints ka category breakdown
    my_categories = cursor.execute("""
        SELECT ai_category, COUNT(*) as count 
        FROM complaints 
        WHERE user_id = ?
        GROUP BY ai_category 
        ORDER BY count DESC
    """, (session['user_id'],)).fetchall()
    
    # Core Departments directory (SLA reference ke liye)
    departments_list = cursor.execute("SELECT * FROM departments ORDER BY name ASC").fetchall()
    
    conn.close()
    
    return render_template('information.html', stats=stats, top_categories=my_categories, departments=departments_list)


# # ═══════════════════════════════════════════════════════════
# 👑 CLEAN SUPER ADMIN AUTHENTICATION MODULE (Option B)
# ═══════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════
# 👑 FRESH SLATE: SUPER ADMIN CORE MATRIX
# ═══════════════════════════════════════════════════════════

# 🌐 1. Super Admin Login Center
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Password String hashing to match database securely
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        admin_user = cursor.execute("""
            SELECT * FROM staff 
            WHERE email = ? AND password_hash = ? AND role = 'SUPER_ADMIN';
        """, (email, password_hash)).fetchone()
        conn.close()
        
        if admin_user:
            # Isolated session tokens assignment
            session['admin_logged_in'] = True
            session['admin_id'] = admin_user['id']
            session['admin_user'] = admin_user['full_name']
            session['admin_role'] = admin_user['role']
            
            flash(f"🔑 Authorization Granted. Welcome {admin_user['full_name']}!", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("❌ Access Denied: Invalid Credentials.", "danger")
            
    return render_template('admin_login.html')


# 🌐 2. Clean connected Super Admin Dashboard
# 🌐 2. Updated Admin Dashboard (Table mein View Detail Button ke liye)
# 🌐 2. UPDATED: Super Admin Dashboard (Sirf Submitted tickets dikhane ke liye)
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in') or session.get('admin_role') != 'SUPER_ADMIN':
        return redirect(url_for('admin_login'))
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Overview Counters Metrics
    stats = {}
    stats['total'] = cursor.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    stats['pending'] = cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'Submitted'").fetchone()[0]
    stats['progress'] = cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'In Progress'").fetchone()[0]
    stats['resolved'] = cursor.execute("SELECT COUNT(*) FROM complaints WHERE status = 'Resolved'").fetchone()[0]
    
    # 🔥 CHANGE: Ab query mein WHERE status = 'Submitted' laga diya hai taaki extra tickets na dikhein
    submitted_complaints = cursor.execute("""
        SELECT c.*, u.full_name as citizen_name 
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        WHERE c.status = 'Submitted'
        ORDER BY c.id DESC
    """).fetchall()
    
    conn.close()
    return render_template('admin_dashboard.html', stats=stats, complaints=submitted_complaints)


# 🌐 3. UPDATED: Dedicated View Screen (Sirf In Progress aur Rejected options ke liye)
# ═══════════════════════════════════════════════════════════
# 👁️ UPDATED: DEDICATED COMPLAINT DETAIL & TELETEMRY VIEW
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# 👁️ DATABASE SYNCED: COMPLAINT DETAIL & CITIZEN FEEDBACK VIEW
# ═══════════════════════════════════════════════════════════

@app.route('/admin/complaint/view/<int:complaint_id>')
def admin_view_complaint(complaint_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 🔥 FIX: LEFT JOIN laga kar feedback table se star_rating aur comment select kiya hai
    complaint = cursor.execute("""
        SELECT c.*, u.full_name as citizen_name, u.email as citizen_email,
               f.star_rating, f.comment as citizen_comment
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        LEFT JOIN feedback f ON c.id = f.complaint_id
        WHERE c.id = ?
    """, (complaint_id,)).fetchone()
    
    # Fetch only those officers whose department matches the complaint's AI category
    if complaint:
        officers = cursor.execute("""
            SELECT id, full_name FROM staff 
            WHERE role = 'OFFICER' 
              AND department_id = (SELECT id FROM departments WHERE name = ?);
        """, (complaint['ai_category'],)).fetchall()
    else:
        officers = []
        
    conn.close()
    
    if not complaint:
        flash("❌ Ticket reference not found.", "danger")
        return redirect(url_for('admin_dashboard'))
        
    return render_template('view_complain.html', item=complaint, officers=officers)

# 🌐 4. NEW: Secure Process & Action Terminal for Single Ticket
@app.route('/admin/complaint/process/<int:complaint_id>', methods=['POST'])
def admin_process_single(complaint_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
        
    status = request.form.get('status')
    officer_id = request.form.get('officer_id')
    justification = request.form.get('justification')
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Get current status for history log entry
    current_state = cursor.execute("SELECT status FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    old_status = current_state[0] if current_state else 'Submitted'
    
    # Formulate connection values
    assigned_id = int(officer_id) if officer_id else None
    
    # Live lifecycle updates execution
    cursor.execute("""
        UPDATE complaints 
        SET status = ?, assigned_officer_id = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (status, assigned_id, complaint_id))
    
    # Save Action parameters into Historical Audit Trail Logs
    cursor.execute("""
        INSERT INTO complaint_history (complaint_id, old_status, new_status, note, changed_by_staff_id)
        VALUES (?, ?, ?, ?, ?);
    """, (complaint_id, old_status, status, f"Admin updated ticket parameters. Note: {justification}", session['admin_id']))
    
    conn.commit()
    conn.close()
    
    flash(f"✅ Ticket NMC-{complaint_id} updated successfully!", "success")
    return redirect(url_for('admin_dashboard'))


# 🌐 3. Admin Secure Exit (Logout)
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_id', None)
    session.pop('admin_user', None)
    session.pop('admin_role', None)
    flash("Admin Session disconnected.", "info")
    return redirect(url_for('admin_login'))

# ═══════════════════════════════════════════════════════════
# 📜 COMPLAINT HISTORY TELEMETRY & FILTER ENGINE
# ═══════════════════════════════════════════════════════════

@app.route('/admin/complaint-history')
def admin_complaint_history():
    if not session.get('admin_logged_in') or session.get('admin_role') != 'SUPER_ADMIN':
        return redirect(url_for('admin_login'))
        
    # URL query string parameters read karna dropdown shorting ke liye
    selected_status = request.args.get('status_filter', '').strip()
    selected_dept = request.args.get('dept_filter', '').strip()
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Base query string build: Submitted ko filter out karna core condition hai
    query = """
        SELECT c.*, u.full_name as citizen_name 
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        WHERE c.status IN ('In Progress', 'Resolved', 'Rejected')
    """
    params = []
    
    # 🎛️ Dynamic parameter shorting engine integration
    if selected_status:
        query += " AND c.status = ?"
        params.append(selected_status)
        
    if selected_dept:
        query += " AND c.ai_category = ?"
        params.append(selected_dept)
        
    # Latest updated base standard sorting schema (Descending Order)
    query += " ORDER BY c.updated_at DESC"
    
    history_complaints = cursor.execute(query, params).fetchall()
    
    # Unique departments extraction list filter boxes dropdown ke liye
    all_departments = cursor.execute("SELECT DISTINCT ai_category FROM complaints WHERE ai_category IS NOT NULL").fetchall()
    
    conn.close()
    return render_template('complaint_history.html', 
                           complaints=history_complaints, 
                           depts=all_departments,
                           current_status=selected_status,
                           current_dept=selected_dept)

import io
import base64
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-GUI terminal backend lock taaki threads clash na ho
import matplotlib.pyplot as plt
import seaborn as sns
from flask import Response
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ═══════════════════════════════════════════════════════════
# 📊 python ADVANCED ANALYTICS & DIAGRAM VISUALIZATION ENGINE
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# 📊 DYNAMIC DEPARTMENT-DRIVEN DATA ANALYTICS ENGINE
# ═══════════════════════════════════════════════════════════

@app.route('/admin/analytics', methods=['GET', 'POST'])
# ═══════════════════════════════════════════════════════════
# 📊 UPDATED: DYNAMIC DEPARTMENT-DRIVEN DATA ANALYTICS ENGINE
# ═══════════════════════════════════════════════════════════

@app.route('/admin/analytics', methods=['GET', 'POST'])
def admin_analytics():
    if not session.get('admin_logged_in') or session.get('admin_role') != 'SUPER_ADMIN':
        return redirect(url_for('admin_login'))
        
    conn = sqlite3.connect(DB_NAME)
    # Pandas DataFrame clean intake data pipeline injection
    df = pd.read_sql_query("SELECT id, ai_category, status FROM complaints", conn)
    conn.close()
    
    # Defaults setting agar database starting phase mein khali ho
    if df.empty:
        df = pd.DataFrame(columns=['id', 'ai_category', 'status'])
        
    # UI styling parameters setup for advanced plotting
    sns.set_theme(style="whitegrid")
    plt.rcParams.update({'font.size': 10, 'axes.labelsize': 11, 'axes.titlesize': 12})
    
    # 🗂️ Unique Departments Master List extract karna dropdown menu fill karne ke liye
    available_depts = df['ai_category'].dropna().unique().tolist()
    
    # URL request query parameter filter value read karna (Default: Pehla available dept pick karna)
    selected_dept = request.args.get('target_dept_filter', '').strip()
    if not selected_dept and available_depts:
        selected_dept = available_depts[0]

    # 🍕 1. PIE CHART: Department-wise Load Distribution Percentage Matrix
    # Sizing ko bada aur balanced rakha hai (6.5 x 5.5) taaki details side se crop na hon
    fig_pie, ax_pie = plt.subplots(figsize=(6.5, 5.5))
    pie_data = df['ai_category'].value_counts()
    
    if not pie_data.empty:
        # labels=None locked taaki text clash na ho, dynamic percent aur colors internal display honge
        wedges, texts, autotexts = ax_pie.pie(
            pie_data, 
            labels=None, 
            autopct='%1.1f%%', 
            colors=sns.color_palette('pastel')[0:len(pie_data)], 
            startangle=140,
            pctdistance=0.75,
            textprops={'fontweight': 'bold', 'fontsize': 10}
        )
        
        # Right side mein clean layout configuration color registry index scale (Legend Box)
        ax_pie.legend(
            wedges, 
            pie_data.index,
            title="Departments Scale Registry",
            loc="center left",
            bbox_to_anchor=(1, 0, 0.5, 1),
            fontsize=9,
            title_fontsize=10
        )
    else:
        ax_pie.text(0.5, 0.5, "No Department Data Present", ha='center')
        
    ax_pie.set_title("Municipal Grievance Load Distribution (%)", fontweight='bold', pad=15)
    plt.tight_layout()
    
    img_pie = io.BytesIO()
    # bbox_inches='tight' optimization overrides ensure details do not crop at borders
    plt.savefig(img_pie, format='png', dpi=130, bbox_inches='tight')
    img_pie.seek(0)
    plot_pie_chart = base64.b64encode(img_pie.getvalue()).decode('utf-8')
    plt.close()

    # 📊 2. DYNAMIC BAR GRAPH: Selected Department Status Distribution Ratio (Scale 0 to 10 Lock)
    # Target filtered department sub-dataframe calculation
    dept_df = df[df['ai_category'] == selected_dept]
    
    # Calculate dynamic breakdown parameter statistics counts
    count_total = len(dept_df)
    count_pending = len(dept_df[dept_df['status'] == 'Submitted'])
    count_progress = len(dept_df[dept_df['status'] == 'In Progress'])
    count_resolved = len(dept_df[dept_df['status'] == 'Resolved'])
    count_rejected = len(dept_df[dept_df['status'] == 'Rejected'])
    
    # Structuring matrix array data points for plotting layout
    status_metrics = pd.DataFrame({
        'Metric Status States': ['Total Intake', 'In Progress', 'Resolved', 'Rejected'],
        'Tickets Count': [count_total, count_progress, count_resolved, count_rejected]
    })
    
    fig_bar, ax_bar = plt.subplots(figsize=(6.5, 4))
    sns.barplot(data=status_metrics, x='Metric Status States', y='Tickets Count', palette='muted', ax=ax_bar)
    
    ax_bar.set_title(f"Operational Load Ratio Matrix: {selected_dept}", fontweight='bold', pad=12)
    ax_bar.set_xlabel("Grievance States Profile")
    ax_bar.set_ylabel("Complaints Axis Metric Scale")
    
    # 🔒 COORDINATE BOUNDARY LOCK: X aur Y axis limits strictly 0 se 10 scale par lock
    ax_bar.set_ylim(0, 10)
    
    plt.tight_layout()
    
    img_bar = io.BytesIO()
    plt.savefig(img_bar, format='png', dpi=130, bbox_inches='tight')
    img_bar.seek(0)
    plot_bar_graph = base64.b64encode(img_bar.getvalue()).decode('utf-8')
    plt.close()

    # 📑 3. BOTTOM DIAGNOSTIC SUMMARY GRID: Pack numbers into dictionary mapping for UI text cards
    dept_stats_summary = {
        'total': count_total,
        'pending': count_pending,
        'progress': count_progress,
        'resolved': count_resolved,
        'rejected': count_rejected
    }

    return render_template('data_analytics.html', 
                           chart_pie=plot_pie_chart, 
                           chart_bar=plot_bar_graph,
                           depts_list=available_depts,
                           current_active_dept=selected_dept,
                           numerical_stats=dept_stats_summary)

# ═══════════════════════════════════════════════════════════
# 🏢 MUNICIPAL CORE DEPARTMENTS & OFFICERS DIRECTORY MODULE
# ═══════════════════════════════════════════════════════════

@app.route('/admin/departments-directory')
def admin_departments_directory():
    if not session.get('admin_logged_in') or session.get('admin_role') != 'SUPER_ADMIN':
        return redirect(url_for('admin_login'))
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch all departments with their specific custom SLA, structural details, and live total workloads
    departments_data = cursor.execute("""
        SELECT d.id, d.name, d.default_sla_days,
        (SELECT COUNT(*) FROM complaints WHERE ai_category = d.name) as total_traffic,
        (SELECT COUNT(*) FROM complaints WHERE ai_category = d.name AND status = 'Resolved') as total_resolved
        FROM departments d
        ORDER BY d.name ASC;
    """).fetchall()
    
    # Fetch all staff members/officers mapped with their structural jurisdiction
    officers_list = cursor.execute("""
        SELECT s.id, s.full_name, s.email, d.name as department_name,
        (SELECT COUNT(*) FROM complaints WHERE assigned_officer_id = s.id AND status NOT IN ('Resolved', 'Rejected')) as active_load
        FROM staff s
        LEFT JOIN departments d ON s.department_id = d.id
        WHERE s.role = 'OFFICER'
        ORDER BY d.name ASC, s.full_name ASC;
    """).fetchall()
    
    conn.close()
    return render_template('department.html', departments=departments_data, officers=officers_list)

# ═══════════════════════════════════════════════════════════
# 👥 DEDICATED OFFICER MANAGEMENT SYSTEM (CRUD ROUTES)
# ═══════════════════════════════════════════════════════════

# 1. VIEW ALL OFFICERS PAGE
@app.route('/admin/officers')
def admin_view_officers():
    if not session.get('admin_logged_in') or session.get('admin_role') != 'SUPER_ADMIN':
        return redirect(url_for('admin_login'))
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Mapped department infrastructure name ke sath officers data extract karna
    officers_list = cursor.execute("""
        SELECT s.id, s.full_name, s.email, s.contact, d.name as department_name 
        FROM staff s
        LEFT JOIN departments d ON s.department_id = d.id
        WHERE s.role = 'OFFICER'
        ORDER BY s.id DESC
    """).fetchall()
    
    conn.close()
    return render_template('view_officer.html', officers=officers_list)


# 2. ADD OFFICER PAGE (GET: Form Dikhao, POST: Save Karo)
@app.route('/admin/officer/add', methods=['GET', 'POST'])
def admin_add_officer():
    if not session.get('admin_logged_in') or session.get('admin_role') != 'SUPER_ADMIN':
        return redirect(url_for('admin_login'))
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if request.method == 'POST':
        name = request.form['full_name']
        email = request.form['email']
        contact = request.form['contact']
        dept_id = request.form.get('department_id')
        
        default_hash = hashlib.sha256("Officer@123".encode()).hexdigest()
        
        try:
            cursor.execute("""
                INSERT INTO staff (full_name, email, password_hash, role, department_id, contact)
                VALUES (?, ?, ?, 'OFFICER', ?, ?);
            """, (name, email, default_hash, int(dept_id) if dept_id else None, contact))
            conn.commit()
            flash(f"🎉 Success: Officer {name} added successfully!", "success")
        except sqlite3.IntegrityError:
            flash("❌ Error: Email address already exists inside system directory.", "danger")
        finally:
            conn.close()
        return redirect(url_for('admin_view_officers'))
        
    # GET request par departments fetch karna dropdown ke liye
    departments = cursor.execute("SELECT id, name FROM departments ORDER BY name ASC").fetchall()
    conn.close()
    return render_template('add_officer.html', departments=departments)


# 3. UPDATE OFFICER PAGE (GET: Old Data Ke Sath Form, POST: Save Changes)
@app.route('/admin/officer/update/<int:officer_id>', methods=['GET', 'POST'])
def admin_update_officer(officer_id):
    if not session.get('admin_logged_in') or session.get('admin_role') != 'SUPER_ADMIN':
        return redirect(url_for('admin_login'))
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if request.method == 'POST':
        name = request.form['full_name']
        email = request.form['email']
        contact = request.form['contact']
        dept_id = request.form.get('department_id')
        
        cursor.execute("""
            UPDATE staff 
            SET full_name = ?, email = ?, contact = ?, department_id = ?
            WHERE id = ? AND role = 'OFFICER';
        """, (name, email, contact, int(dept_id) if dept_id else None, officer_id))
        conn.commit()
        conn.close()
        flash("📝 Officer details updated successfully.", "success")
        return redirect(url_for('admin_view_officers'))
        
    # GET request: Existing details aur departments direct populate karna
    officer = cursor.execute("SELECT * FROM staff WHERE id = ? AND role = 'OFFICER'", (officer_id,)).fetchone()
    departments = cursor.execute("SELECT id, name FROM departments ORDER BY name ASC").fetchall()
    conn.close()
    
    if not officer:
        flash("❌ Officer not found.", "danger")
        return redirect(url_for('admin_view_officers'))
        
    return render_template('update.html', officer=officer, departments=departments)


# 4. DELETE OFFICER ACTION
@app.route('/admin/officer/delete/<int:officer_id>', methods=['POST'])
def admin_delete_officer(officer_id):
    if not session.get('admin_logged_in') or session.get('admin_role') != 'SUPER_ADMIN':
        return redirect(url_for('admin_login'))
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # References clean safely unlink karna tickets repository se
    cursor.execute("UPDATE complaints SET assigned_officer_id = NULL WHERE assigned_officer_id = ?;", (officer_id,))
    cursor.execute("DELETE FROM staff WHERE id = ? AND role = 'OFFICER';", (officer_id,))
    
    conn.commit()
    conn.close()
    flash("🗑️ Officer removed from system database context successfully.", "info")
    return redirect(url_for('admin_view_officers'))

if __name__ == '__main__':
    app.run(debug=True, port=1000)  # Debug mode on, port 1000 par chal raha hai