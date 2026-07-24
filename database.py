import sqlite3

DB_NAME = "citizen_complaints.db"

# Pure 40 features ko support karne wala final schema query string
final_schema_query = """
PRAGMA foreign_keys = ON;

-- ═══════════════════════════════════════════════════════════
-- TABLE 1: DEPARTMENTS (Admin Feature 14)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS departments (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    name          TEXT     NOT NULL UNIQUE, 
    code          TEXT     NOT NULL UNIQUE, 
    contact_email TEXT,
    default_sla_days INTEGER DEFAULT 3,      
    description   TEXT,                      
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══════════════════════════════════════════════════════════
-- TABLE 2: USERS / CITIZENS (Citizen Feature 01)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER  PRIMARY KEY AUTOINCREMENT,
    full_name           TEXT     NOT NULL,
    email               TEXT     NOT NULL UNIQUE,
    phone               TEXT,
    password_hash       TEXT     NOT NULL, 
    city                TEXT     DEFAULT 'Nashik',
    is_active           INTEGER  DEFAULT 1,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══════════════════════════════════════════════════════════
-- TABLE 3: STAFF / ADMINS / OFFICERS (Admin Feature 12 & 13)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS staff (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT     NOT NULL,
    email         TEXT     NOT NULL UNIQUE,
    password_hash TEXT     NOT NULL,
    role          TEXT     NOT NULL CHECK(role IN ('SUPER_ADMIN', 'DEPT_HEAD', 'OFFICER')), 
    department_id INTEGER, 
    is_active     INTEGER  DEFAULT 1,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
);

-- ═══════════════════════════════════════════════════════════
-- TABLE 4: COMPLAINTS (Core Engine for AI & Operations)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS complaints (
    id                  INTEGER  PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER  NOT NULL,
    title               TEXT     NOT NULL,
    description         TEXT     NOT NULL, 
    original_language   TEXT     DEFAULT 'en', 
    translated_text     TEXT,                  
    address             TEXT,
    
    -- AI Predictions (Citizen Features 05, 06, 15, 19)
    ai_category         TEXT,    
    ai_confidence       REAL,    
    ai_urgency          TEXT     CHECK(ai_urgency IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    ai_sentiment        TEXT,    
    
    -- Management & Operations (Admin Features 01, 07, 11)
    status              TEXT     DEFAULT 'Submitted' CHECK(status IN ('Submitted', 'Under Review', 'In Progress', 'Resolved', 'Rejected', 'Escalated', 'Withdrawn')),
    tracking_token      TEXT     NOT NULL UNIQUE, 
    assigned_officer_id INTEGER, 
    
    -- SLA Configuration (Your Manual Custom SLA Requirement)
    custom_sla_hours    INTEGER  DEFAULT NULL, 
    resolution_note     TEXT,                  
    
    -- Duplicate & Merge System (Citizen Feature 04 / Admin Feature 04)
    is_duplicate        INTEGER  DEFAULT 0,
    parent_id           INTEGER, 
    
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_officer_id) REFERENCES staff(id) ON DELETE SET NULL,
    FOREIGN KEY (parent_id) REFERENCES complaints(id) ON DELETE SET NULL
);

-- ═══════════════════════════════════════════════════════════
-- TABLE 5: STATUS_HISTORY_TRAIL (Citizen Feature 20 / Admin Feature 20)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS complaint_history (
    id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    complaint_id    INTEGER  NOT NULL,
    old_status      TEXT,
    new_status      TEXT     NOT NULL,
    changed_by_staff_id INTEGER, 
    note            TEXT,        
    changed_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
    FOREIGN KEY (changed_by_staff_id) REFERENCES staff(id) ON DELETE SET NULL
);

-- ═══════════════════════════════════════════════════════════
-- TABLE 6: FEEDBACK & RATINGS (Citizen Feature 14 / Admin Feature 16)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS feedback (
    id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    complaint_id    INTEGER  NOT NULL UNIQUE,
    star_rating     INTEGER  NOT NULL CHECK(star_rating BETWEEN 1 AND 5),
    comment         TEXT,
    submitted_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- ═══════════════════════════════════════════════════════════
-- TABLE 7: FULL AUDIT LOG (Admin Feature 19 - Security and Control)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    staff_id        INTEGER, 
    action_type     TEXT     NOT NULL, 
    target_id       INTEGER,           
    old_value       TEXT,
    new_value       TEXT,
    details         TEXT,
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE SET NULL
);

-- ═══════════════════════════════════════════════════════════
-- INITIAL SEED DATA FOR DEPARTMENTS
-- ═══════════════════════════════════════════════════════════
INSERT OR IGNORE INTO departments (name, code, default_sla_days, description) VALUES
('Roads & Infrastructure', 'ROADS', 3, 'Handles potholes, street paving, footpaths, and dividers.'),
('Water Supply', 'WATER', 2, 'Manages pipeline bursts, water leakages, low pressure, and muddy water.'),
('Electricity', 'ELEC', 1, 'Resolves streetlights, broken wires, transformer sparks, and power failures.'),
('Sanitation & Garbage', 'SANIT', 2, 'Handles garbage clearing, cleaning gutters, and public toilet issues.'),
('Illegal Construction & Encroachment', 'ENCR', 3, 'Handles unauthorized buildings, illegal extensions, footpath blocking, and unapproved structures.');

-- ═══════════════════════════════════════════════════════════
-- SEED DATA — UPDATED MASTER ADMIN (Devidas Tambe)
-- ═══════════════════════════════════════════════════════════
INSERT OR IGNORE INTO staff (full_name, email, password_hash, role, department_id) VALUES 
('Devidas Tambe', 'devidas@gmail.com', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', 'SUPER_ADMIN', NULL);
"""

def build_database():
    try:
        print(f"🔄 Creating SQLite database system '{DB_NAME}'...")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Is script se saare tables aur seed data ek sath create ho jayenge
        cursor.executescript(final_schema_query)
        conn.commit()
        
        print("✅ Success: Sabhi tables aur 'Devidas Tambe' Admin seed data initialize ho chuka hai!")
    except sqlite3.Error as e:
        print(f"❌ Error occurred during database execution: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    build_database()