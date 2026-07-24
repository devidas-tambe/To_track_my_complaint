import sqlite3

DB_NAME = "citizen_complaints.db"

try:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # staff table mein contact column add karne ka SQL query
    cursor.execute("ALTER TABLE staff ADD COLUMN contact TEXT;")
    
    conn.commit()
    print("✅ Contact column successfully added to staff table!")
except sqlite3.OperationalError as e:
    print(f"ℹ️ Info: {e} (Shayad column pehle se hi add karne ki koshish ki gayi thi)")
finally:
    conn.close()