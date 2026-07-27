from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
import sqlite3
import hashlib
import secrets              # 💥 NEW: Unique token generator ke liye
from transformers import pipeline  # 💥 NEW: Zero-Shot AI Core ke liye
import csv
from io import StringIO
import io
import base64
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-GUI terminal backend lock taaki threads clash na ho
import matplotlib.pyplot as plt
import seaborn as sns
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

app = Flask(__name__)
app.secret_key = "nashik_secret_key" # Flash messages dikhane ke liye zaroori hai
DB_NAME = "citizen_complaints.db"

# ═══════════════════════════════════════════════════════════
# 🚀 AUTOMATIC ENTRY GATEKEEPER (Fix: Separated Base URL Route)
# ═══════════════════════════════════════════════════════════
@app.route('/')
def index():
    # Jaise hi aap http://127.0.0.1:1000/ run karoge, 
    # yeh route auto-trigger ho kar aapko seedhe admin login page par dispatch kar dega.
    return redirect(url_for('admin_login'))

# ═══════════════════════════════════════════════════════════
# 👑 CLEAN SUPER ADMIN AUTHENTICATION MODULE
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


# 🌐 3. DATABASE SYNCED: COMPLAINT DETAIL & CITIZEN FEEDBACK VIEW
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


# 🌐 4. Secure Process & Action Terminal for Single Ticket
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


# 🌐 5. Admin Secure Exit (Logout)
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


# ═══════════════════════════════════════════════════════════
# 📊 UPDATED: DYNAMIC DEPARTMENT-DRIVEN DATA ANALYTICS ENGINE
# ═══════════════════════════════════════════════════════════
@app.route('/admin/analytics', methods=['GET', 'POST'])
def admin_analytics():
    if not session.get('admin_logged_in') or session.get('admin_role') != 'SUPER_ADMIN':
        return redirect(url_for('admin_login'))
        
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT id, ai_category, status FROM complaints", conn)
    conn.close()
    
    if df.empty:
        df = pd.DataFrame(columns=['id', 'ai_category', 'status'])
        
    sns.set_theme(style="whitegrid")
    plt.rcParams.update({'font.size': 10, 'axes.labelsize': 11, 'axes.titlesize': 12})
    
    available_depts = df['ai_category'].dropna().unique().tolist()
    
    selected_dept = request.args.get('target_dept_filter', '').strip()
    if not selected_dept and available_depts:
        selected_dept = available_depts[0]

    # 🍕 1. PIE CHART: Department-wise Load Distribution Percentage Matrix
    fig_pie, ax_pie = plt.subplots(figsize=(6.5, 5.5))
    pie_data = df['ai_category'].value_counts()
    
    if not pie_data.empty:
        wedges, texts, autotexts = ax_pie.pie(
            pie_data, 
            labels=None, 
            autopct='%1.1f%%', 
            colors=sns.color_palette('pastel')[0:len(pie_data)], 
            startangle=140,
            pctdistance=0.75,
            textprops={'fontweight': 'bold', 'fontsize': 10}
        )
        
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
    plt.savefig(img_pie, format='png', dpi=130, bbox_inches='tight')
    img_pie.seek(0)
    plot_pie_chart = base64.b64encode(img_pie.getvalue()).decode('utf-8')
    plt.close()

    # 📊 2. DYNAMIC BAR GRAPH: Selected Department Status
    dept_df = df[df['ai_category'] == selected_dept]
    
    count_total = len(dept_df)
    count_pending = len(dept_df[dept_df['status'] == 'Submitted'])
    count_progress = len(dept_df[dept_df['status'] == 'In Progress'])
    count_resolved = len(dept_df[dept_df['status'] == 'Resolved'])
    count_rejected = len(dept_df[dept_df['status'] == 'Rejected'])
    
    status_metrics = pd.DataFrame({
        'Metric Status States': ['Total Intake', 'In Progress', 'Resolved', 'Rejected'],
        'Tickets Count': [count_total, count_progress, count_resolved, count_rejected]
    })
    
    fig_bar, ax_bar = plt.subplots(figsize=(6.5, 4))
    sns.barplot(data=status_metrics, x='Metric Status States', y='Tickets Count', palette='muted', ax=ax_bar)
    
    ax_bar.set_title(f"Operational Load Ratio Matrix: {selected_dept}", fontweight='bold', pad=12)
    ax_bar.set_xlabel("Grievance States Profile")
    ax_bar.set_ylabel("Complaints Axis Metric Scale")
    ax_bar.set_ylim(0, 10)
    
    plt.tight_layout()
    
    img_bar = io.BytesIO()
    plt.savefig(img_bar, format='png', dpi=130, bbox_inches='tight')
    img_bar.seek(0)
    plot_bar_graph = base64.b64encode(img_bar.getvalue()).decode('utf-8')
    plt.close()

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


# 📄 6. DOWNLOAD COMPLAINTS REGISTRY LEDGER TO PDF
@app.route('/admin/analytics/download-pdf')
def admin_download_pdf():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    resolved_tickets = cursor.execute("""
        SELECT c.id, u.full_name as citizen, c.title, c.ai_category, c.updated_at
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        WHERE c.status = 'Resolved'
        ORDER BY c.updated_at DESC
    """).fetchall()
    conn.close()
    
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor('#11141a'), alignment=1, spaceAfter=6)
    meta_style = ParagraphStyle('DocMeta', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.gray, alignment=1, spaceAfter=20)
    cell_style = ParagraphStyle('CellText', parent=styles['Normal'], fontSize=9, leading=12)
    header_style = ParagraphStyle('HeaderCell', parent=styles['Normal'], fontSize=9, leading=12, fontName='Helvetica-Bold', textColor=colors.white)
    
    story.append(Paragraph("NASHIK MUNICIPAL CORPORATION", title_style))
    story.append(Paragraph("Official Performance Report — Resolved Complaints Registry Ledger", meta_style))
    story.append(Spacer(1, 10))
    
    table_data = [[
        Paragraph("Token ID", header_style), 
        Paragraph("Citizen Name", header_style), 
        Paragraph("Complaint Title", header_style), 
        Paragraph("Department Node", header_style), 
        Paragraph("Closure Timestamp", header_style)
    ]]
    
    for row in resolved_tickets:
        table_data.append([
            Paragraph(f"NMC-{row['id']}", cell_style),
            Paragraph(row['citizen'], cell_style),
            Paragraph(row['title'], cell_style),
            Paragraph(row['ai_category'] if row['ai_category'] else 'N/A', cell_style),
            Paragraph(row['updated_at'], cell_style)
        ])
        
    complaint_table = Table(table_data, colWidths=[65, 95, 175, 105, 100])
    complaint_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#11141a')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
    ]))
    
    story.append(complaint_table)
    doc.build(story)
    pdf_buffer.seek(0)
    return Response(pdf_buffer.getvalue(), mimetype='application/pdf',
                    headers={'Content-Disposition': 'attachment; filename=NMC_Resolved_Complaints_Report.pdf'})


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
    
    departments_data = cursor.execute("""
        SELECT d.id, d.name, d.default_sla_days,
        (SELECT COUNT(*) FROM complaints WHERE ai_category = d.name) as total_traffic,
        (SELECT COUNT(*) FROM complaints WHERE ai_category = d.name AND status = 'Resolved') as total_resolved
        FROM departments d
        ORDER BY d.name ASC;
    """).fetchall()
    
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
    
    cursor.execute("UPDATE complaints SET assigned_officer_id = NULL WHERE assigned_officer_id = ?;", (officer_id,))
    cursor.execute("DELETE FROM staff WHERE id = ? AND role = 'OFFICER';", (officer_id,))
    
    conn.commit()
    conn.close()
    flash("🗑️ Officer removed from system database context successfully.", "info")
    return redirect(url_for('admin_view_officers'))


if __name__ == '__main__':
    app.run(debug=True, port=2000)