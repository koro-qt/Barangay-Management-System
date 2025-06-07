from bcrypt import hashpw, gensalt
from flask import Blueprint, render_template, url_for, redirect, session, request, flash
from helpers import database as db, get_all_resident_info, get_current_user_info, get_all_requests, get_all_reports, get_all_sanctions
from psycopg2.extras import RealDictCursor
from datetime import datetime

secretary = Blueprint('secretary', __name__)

# =================================== MIDDLEWARE ===================================
@secretary.before_request
def restrict_to_secretary():
    """Middleware to ensure only secretary can access these routes"""
    if session.get('role') != 'secretary':
        return redirect(url_for('auth.login'))

# =================================== ROUTES ===================================
@secretary.route('/dashboard')
def dashboard():
    """Render secretary dashboard with resident info and requests"""
    try:
        secretary = get_current_user_info()
        residents = get_all_resident_info()
        requests = get_all_requests()
        return render_template('secretary/dashboard.html', 
                             secretary=secretary, 
                             residents=residents, 
                             requests=requests)
    except Exception as e:
        flash('Error loading dashboard', 'danger')
        print(f"Dashboard error: {e}")
        return redirect(url_for('auth.login'))

@secretary.route('/requests')
def requests_sec():
    """Render requests page with optional filtering"""
    try:
        filter = request.args.get('filter', 'Default')
        released_by = get_all_released_by()
        requests = get_all_requests(filter)
        return render_template('secretary/requests.html', 
                             requests=requests, 
                             flask_request=request, 
                             released_by=released_by)
    except Exception as e:
        flash('Error loading requests', 'danger')
        print(f"Requests error: {e}")
        return redirect(url_for('secretary.dashboard'))

@secretary.route('/residents')
def residents_sec():
    """Render residents page with optional filtering"""
    try:
        filter = request.args.get('filter', 'Default')
        sanctions = get_all_sanctions()
        residents = get_all_resident_info(filter)
        return render_template('secretary/residents.html', 
                            residents=residents, 
                            sanctions=sanctions)
    except Exception as e:
        flash('Error loading residents', 'danger')
        print(f"Residents error: {e}")
        return redirect(url_for('secretary.dashboard'))

@secretary.route('/reports')
def reports_sec():
    """Render community reports page"""
    flash('Error loading reports', 'danger')
    try:
        reports = get_all_reports(category='default')
        return render_template('secretary/reports.html', reports=reports)
    except Exception as e:
        flash('Error loading reports', 'danger')
        print(f"Reports error: {e}")
        return redirect(url_for('secretary.dashboard'))

@secretary.route('/updates')
def updates_sec():
    """Render community updates page"""
    try:
        my_updates = get_my_updates()
        residents = get_all_resident_info()
        return render_template('secretary/updates.html', 
                             my_updates=my_updates, 
                             residents=residents)
    except Exception as e:
        flash('Error loading updates', 'danger')
        print(f"Updates error: {e}")
        return redirect(url_for('secretary.dashboard'))

@secretary.route('/account')
def account_sec():
    """Render secretary account page"""
    try:
        current_user = get_current_user_info()
        return render_template('secretary/account.html', current_user=current_user)
    except Exception as e:
        flash('Error loading account', 'danger')
        print(f"Account error: {e}")
        return redirect(url_for('secretary.dashboard'))

# =================================== FORM SUBMISSIONS ===================================
@secretary.route('/update-request', methods=['POST'])
def update_request():
    """Handle document request status updates"""
    if request.method != 'POST':
        return redirect(url_for('secretary.requests_sec'))

    request_id = request.form.get('id')
    status = request.form.get('status')
    filter = request.form.get('filter')

    if not all([request_id, status]):
        flash('Invalid request parameters', 'danger')
        return redirect(url_for('secretary.requests_sec'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Update request status
        cursor.execute("""
            UPDATE request_document 
            SET status = %s, reviewed_by = %s, reviewed_at = NOW() 
            WHERE id = %s
        """, (status, session.get('id'), request_id))

        # Handle receipt creation based on status
        if status == 'To Pick Up':
            cursor.execute("""
                INSERT INTO receipt(request_id, payment_status, paid_at) 
                VALUES(%s, 'Paid', NOW())
            """, (request_id,))
        else:
            cursor.execute("""
                INSERT INTO receipt(request_id) 
                VALUES(%s)
            """, (request_id,))

        conn.commit()
        flash('Request status updated successfully', 'success')
    except Exception as e:
        flash('Error updating request status', 'danger')
        print(f"Request update error: {e}")
    finally:
        if conn:
            db.putconn(conn)

    return redirect(url_for('secretary.requests_sec', filter=filter))

@secretary.route('/add_update', methods=['POST'])
def add_update():
    """Handle adding new community updates"""
    if request.method != 'POST':
        return redirect(url_for('secretary.updates_sec'))

    title = request.form.get('title')
    content = request.form.get('content')

    if not all([title, content]):
        flash('Title and content are required', 'danger')
        return redirect(url_for('secretary.updates_sec'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            INSERT INTO community_update(title, content, created_by) 
            VALUES (%s, %s, %s)
        """, (title.title(), content.capitalize(), session.get('id')))
        conn.commit()
        flash('Update added successfully', 'success')
    except Exception as e:
        flash('Error adding update', 'danger')
        print(f"Add update error: {e}")
    finally:
        if conn:
            db.putconn(conn)

    return redirect(url_for('secretary.updates_sec'))

@secretary.route('/add_sanction', methods=['POST'])
def add_sanction():
    """Handle adding new sanctions to residents"""
    if request.method != 'POST':
        return redirect(url_for('secretary.residents_sec'))

    resident_id = request.form.get('resident_id')
    issued_at = request.form.get('issued_at')
    expires_at = request.form.get('expires_at')
    reason = request.form.get('reason')

    if not all([resident_id, issued_at, expires_at, reason]):
        flash('All sanction fields are required', 'danger')
        return redirect(url_for('secretary.residents_sec'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Add sanction
        cursor.execute("""
            INSERT INTO sanctions (resident_id, issued_by, issued_at, expires_at, reason) 
            VALUES (%s, %s, %s, %s, %s)
        """, (resident_id, session.get('id'), issued_at, expires_at, reason.capitalize()))
        
        # Deactivate resident
        cursor.execute("""
            UPDATE resident 
            SET is_active = FALSE 
            WHERE id = %s
        """, (resident_id,))
        
        conn.commit()
        flash('Sanction added successfully', 'success')
    except Exception as e:
        flash('Error adding sanction', 'danger')
        print(f"Add sanction error: {e}")
    finally:
        if conn:
            db.putconn(conn)

    return redirect(url_for('secretary.residents_sec'))

@secretary.route('/remove_sanction', methods=['POST'])
def remove_sanction():
    """Handle removing sanctions from residents"""
    if request.method != 'POST':
        return redirect(url_for('secretary.residents_sec'))

    resident_id = request.form.get('resident_id')
    if not resident_id:
        flash('Invalid resident ID', 'danger')
        return redirect(url_for('secretary.residents_sec'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Remove sanction
        cursor.execute("""
            DELETE FROM sanctions 
            WHERE resident_id = %s
        """, (resident_id,))
        
        # Reactivate resident
        cursor.execute("""
            UPDATE resident 
            SET is_active = TRUE 
            WHERE id = %s
        """, (resident_id,))
        
        conn.commit()
        flash('Sanction removed successfully', 'success')
    except Exception as e:
        flash('Error removing sanction', 'danger')
        print(f"Remove sanction error: {e}")
    finally:
        if conn:
            db.putconn(conn)

    return redirect(url_for('secretary.residents_sec'))

@secretary.route('/resolve_report', methods=['POST'])
def resolve_report():
    """Handle resolving community reports"""
    if request.method != 'POST':
        return redirect(url_for('secretary.reports_sec'))

    report_id = request.form.get('report-id')
    if not report_id:
        flash('Invalid report ID', 'danger')
        return redirect(url_for('secretary.reports_sec'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            UPDATE community_report 
            SET status = 'Resolved', reviewed_by = %s 
            WHERE id = %s
        """, (session.get('id'), report_id))
        conn.commit()
        flash('Report resolved successfully', 'success')
    except Exception as e:
        flash('Error resolving report', 'danger')
        print(f"Resolve report error: {e}")
    finally:
        if conn:
            db.putconn(conn)

    return redirect(url_for('secretary.reports_sec'))

# =================================== HELPER FUNCTIONS ===================================
def get_my_updates():
    """Get updates created by current secretary"""
    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT * FROM community_update 
            WHERE created_by = %s 
            ORDER BY created_at DESC
        """, (session.get('id'),))
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching updates: {e}")
        return []
    finally:
        if conn:
            db.putconn(conn)

def get_all_released_by():
    """Get information about who released each request"""
    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT 
                rd.id as request_id,
                rd.status,
                CASE 
                    WHEN rd.status = 'Released' THEN t.username
                    WHEN rd.status = 'To Pay' THEN 'Pending Payment'
                    WHEN rd.status = 'Rejected' THEN 'Rejected'
                    ELSE 'Pending Review'
                END as released_by
            FROM request_document rd
            LEFT JOIN receipt r ON rd.id = r.request_id
            LEFT JOIN treasurer t ON r.issued_by = t.id
            ORDER BY rd.id DESC
        """)
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching released by info: {e}")
        return []
    finally:
        if conn:
            db.putconn(conn)

# =================================== ADMIN FUNCTIONS ===================================
def add():
    """Admin function to add new secretary accounts"""
    username = input("Enter username: ")
    email = input("Enter email: ")
    password = input("Enter password: ")

    if not all([username, email, password]):
        print("All fields are required")
        return

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        password_hash = hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')

        # Check for existing users
        roles = ['secretary', 'resident', 'treasurer']
        for role in roles:
            cursor.execute(f"SELECT * FROM {role} WHERE email = %s", (email,))
            if cursor.fetchone():
                print(f"User with email {email} already exists in {role} role")
                return

        # Add new secretary
        cursor.execute("""
            INSERT INTO secretary(email, password, username) 
            VALUES (%s, %s, %s)
        """, (email, password_hash, username))
        conn.commit()
        print("Secretary account created successfully")
    except Exception as e:
        print(f"Error creating secretary account: {e}")
    finally:
        if conn:
            db.putconn(conn)