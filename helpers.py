from flask import session
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import schedule
import time
import threading
from datetime import datetime

try:
    database = pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        host='localhost',
        user='postgres', 
        password='unoserrato05',
        database='barangaydb',
        port=5432
    )

    if database:
        print("Connection pool created successfully.")

except Exception as e:
    print("Error creating connection pool:", e)

def get_current_user_info():
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(f"SELECT * FROM {session['role']} WHERE id = %s", (session['id'],))
    user = cursor.fetchone()
    database.putconn(conn)  
    return user

def get_all_resident_info(filter='Default'):
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if filter == 'Default':
        cursor.execute("SELECT *, CONCAT(first_name, ' ', last_name) as name FROM resident ORDER BY id")
    elif filter == 'Online':
        cursor.execute("SELECT *, CONCAT(first_name, ' ', last_name) as name FROM resident WHERE is_active = true ORDER BY id")
    elif filter == 'Offline':
        cursor.execute("SELECT *, CONCAT(first_name, ' ', last_name) as name FROM resident WHERE is_active = false ORDER BY id")
    resident = cursor.fetchall()
    database.putconn(conn)

    return resident

def get_active_admins():
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT 'secretary' as role, id, username, is_active 
        FROM secretary 
        WHERE is_active = true
        UNION ALL
        SELECT 'treasurer' as role, id, username, is_active 
        FROM treasurer 
        WHERE is_active = true
    """)
    admins = cursor.fetchall()
    database.putconn(conn)

    return admins

def get_current_user_reports():
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT community_report.*, secretary.username FROM community_report LEFT JOIN secretary ON community_report.reviewed_by = secretary.id WHERE resident_id = %s ORDER BY posted_at DESC", (session['id'],))
    reports = cursor.fetchall()
    database.putconn(conn)
    return reports

def get_all_reports(category='default'):
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    if category == 'default':
        cursor.execute("""
            SELECT 
                community_report.*,
                resident.first_name, resident.last_name,
            CONCAT(resident.first_name, ' ', resident.last_name) as name 
        FROM community_report 
        LEFT JOIN resident ON community_report.resident_id = resident.id 
        ORDER BY posted_at DESC
        """)
    reports = cursor.fetchall()
    database.putconn(conn)
    return reports

def get_all_requests(filter='Default'):
    """
    Fetch all document requests with resident information.
    Returns a list of requests with resident details.
    """
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Join request_document with resident table to get resident information
        if filter == 'Default':
            query = """
                SELECT 
                    rd.id,
                rd.document_type,
                rd.price,
                rd.requirements,
                rd.created_at,
                rd.status,
                rd.reviewed_by,
                CONCAT(r.first_name, ' ', r.last_name) as name
            FROM request_document rd
            JOIN resident r ON rd.resident_id = r.id
            ORDER BY rd.created_at DESC
            """
            cursor.execute(query)
        else:
            query = """
                SELECT 
                    rd.id,
                rd.document_type,
                rd.price,
                rd.requirements,
                rd.created_at,
                rd.status,
                rd.reviewed_by,
                CONCAT(r.first_name, ' ', r.last_name) as name
            FROM request_document rd
            JOIN resident r ON rd.resident_id = r.id
            WHERE rd.status = %s
            ORDER BY rd.created_at DESC
            """
            cursor.execute(query, (filter,))
        requests = cursor.fetchall()
        return requests
    except Exception as e:
        print(f"Error fetching requests: {e}")
        return []
    finally:
        database.putconn(conn)

def set_inactive_last_login():
    try:
        conn = database.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(f"UPDATE {session['role']} SET is_active = false WHERE id = %s", (session['id'],))
        conn.commit()
        database.putconn(conn)  
    except Exception as e:
        print("Error logging out last login:", e)

def set_active_last_login():
    try:
        conn = database.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(f"UPDATE {session['role']} SET is_active = true WHERE id = %s", (session['id'],))
        conn.commit()
        database.putconn(conn)
    except Exception as e:
        print("Error logging out last login:", e)

def get_all_updates():
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT 
            community_update.*, 
            secretary.username,
            (SELECT COUNT(*) FROM comments WHERE post_id = community_update.id) as comment_count 
        FROM community_update 
        JOIN secretary ON community_update.created_by = secretary.id 
        ORDER BY created_at DESC
    """)
    updates = cursor.fetchall()
    database.putconn(conn)
    return updates


def get_update_by_id(update_id):
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # get update by id
    cursor.execute("SELECT community_update.*, secretary.username FROM community_update JOIN secretary ON community_update.created_by = secretary.id WHERE community_update.id = %s ORDER BY created_at DESC ", (update_id,))
    update = cursor.fetchone()

    # get comments by update id
    cursor.execute("SELECT comments.*, (SELECT CONCAT(first_name, ' ', last_name) FROM resident WHERE id=comments.created_by) as name FROM comments JOIN resident ON resident.id=comments.created_by WHERE post_id = %s ORDER BY created_at DESC", (update_id,))
    comments = cursor.fetchall()
    database.putconn(conn)
    return update, comments

def get_all_comments():
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM comments")
    comments = cursor.fetchall()
    database.putconn(conn)
    return comments

def get_all_sanctions():
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM sanctions")
    sanctions = cursor.fetchall()
    database.putconn(conn)
    return sanctions

def constant_updates():
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("DELETE FROM sanctions WHERE expires_at < NOW()")
    conn.commit()
    database.putconn(conn)

def update_sanctions():
    """Update expired sanctions and resident status"""
    conn = database.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    print(f"[{datetime.now()}] Sanctions scheduler thread started")
    try:
        # Delete expired sanctions
        cursor.execute("""
            DELETE FROM sanctions 
            WHERE expires_at < NOW()
        """)
        
        conn.commit()
    except Exception as e:
        print(f"Error updating sanctions: {e}")
    finally:
        database.putconn(conn)

def run_scheduler():
    """Run the scheduler in a separate thread"""
    schedule.every(5).seconds.do(update_sanctions)
    while True:
        schedule.run_pending()
        time.sleep(1)

# Start the scheduler in a background thread when the module is imported
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()