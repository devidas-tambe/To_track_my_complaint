from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
import sqlite3 
import hashlib
import secrets              # 💥 NEW: Unique token generator ke liye
from transformers import pipeline  # 💥 NEW: Zero-Shot AI Core ke liye
import csv
from io import StringIO
 
# d@gmail.com
# @123
 
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
            flash("Registration successful! You have been registered.", "success")
            return redirect(url_for('login')) # Sahi hone par login page par bhej dega
        except sqlite3.IntegrityError:
            # Agar email pehle se database mein hoga toh yeh error aayega
            flash("This email is already registered!", "danger")
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
            flash("Invalid Email or Password! Please try again.", "danger")
            
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



if __name__ == '__main__':
    app.run(debug=True, port=1000)  # Debug mode on, port 1000 par chal raha hai
